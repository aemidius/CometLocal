"""
H4 — Runtime Step Loop + Trace completo + Policies anti-loop + Recovery determinista

Decisión conservadora (v1):
- Cuando se activa un policy_halt, el run termina con status="halted".

Este runtime:
- NO usa LLM ni planner.
- Integra BrowserController + action_compiler_v1 (evaluate_conditions / execute_action_only).
- Emite trace.jsonl completo por step según docs/trace_contract_v1.md (subset requerido en H4).
- Mantiene evidence_manifest.json con hashes y rutas relativas.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.executor.action_compiler_v1 import (
    PolicyStateV1,
    evaluate_conditions,
    execute_action_only,
    validate_runtime,
)
from backend.executor.browser_controller import BrowserController, ExecutionProfileV1, ExecutorTypedException
from backend.shared.executor_contracts_v1 import (
    ActionKindV1,
    ActionSpecV1,
    EvidenceItemV1,
    EvidenceKindV1,
    EvidenceManifestV1,
    EvidencePolicyV1,
    EvidenceRefV1,
    ExecutorErrorV1,
    ErrorStageV1,
    ErrorSeverityV1,
    RedactionPolicyV1,
    StateSignatureV1,
    TraceEventTypeV1,
    TraceEventV1,
    TargetKindV1,
    TargetV1,
)


@dataclass(frozen=True)
class RuntimePolicyDefaultsV1:
    retries_per_action: int = 2
    recovery_max: int = 3
    same_state_revisits: int = 2
    hard_cap_steps: int = 60
    backoff_ms: Tuple[int, int, int] = (300, 1000, 2000)
    allow_reload_once: bool = True
    overlay_close_selectors: Tuple[str, ...] = ('button[aria-label="Close"]',)
    overlay_close_texts: Tuple[str, ...] = ("Cerrar", "Close")


def _item_to_ref(item: EvidenceItemV1) -> EvidenceRefV1:
    return EvidenceRefV1(
        kind=item.kind,
        uri=item.relative_path,
        sha256=item.sha256,
        mime_type=item.mime_type,
        redacted=item.redacted,
        size_bytes=item.size_bytes,
        metadata=item.metadata,
    )


def _state_key(sig: StateSignatureV1) -> str:
    return f"{sig.key_elements_hash}:{sig.visible_text_hash}:{sig.screenshot_hash}"


class ExecutorRuntimeH4:
    def __init__(
        self,
        *,
        runs_root: str | Path = "runs",
        execution_mode: str = "live",
        domain_allowlist: Optional[List[str]] = None,
        profile: Optional[ExecutionProfileV1] = None,
        policy: Optional[RuntimePolicyDefaultsV1] = None,
    ):
        self.runs_root = Path(runs_root)
        self.execution_mode = execution_mode
        self.domain_allowlist = domain_allowlist or []
        self.profile = profile or ExecutionProfileV1()
        self.policy = policy or RuntimePolicyDefaultsV1()

    def run_actions(self, *, url: str, actions: List[ActionSpecV1], headless: bool = True) -> Path:
        run_id = f"r_{uuid.uuid4().hex}"
        run_dir = self.runs_root / run_id
        evidence_dir = run_dir / "evidence"
        (evidence_dir / "dom").mkdir(parents=True, exist_ok=True)
        (evidence_dir / "shots").mkdir(parents=True, exist_ok=True)
        (evidence_dir / "html").mkdir(parents=True, exist_ok=True)

        trace_path = run_dir / "trace.jsonl"
        manifest_path = run_dir / "evidence_manifest.json"

        seq = 0
        manifest_items: List[EvidenceItemV1] = []

        policy_state = PolicyStateV1()
        seen_states: Dict[str, int] = {}  # state_key -> count
        last_state_keys: List[str] = []  # ventana corta para "coincide con uno reciente"
        reload_used = False

        def emit(ev: TraceEventV1) -> None:
            nonlocal seq
            seq += 1
            ev.seq = seq
            with open(trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(ev.model_dump(), ensure_ascii=False) + "\n")

        def add_evidence(step_id: str, state_before: Optional[StateSignatureV1], state_after: Optional[StateSignatureV1], items: List[EvidenceItemV1]) -> None:
            if not items:
                return
            manifest_items.extend(items)
            emit(
                TraceEventV1(
                    run_id=run_id,
                    seq=0,
                    event_type=TraceEventTypeV1.evidence_captured,
                    step_id=step_id,
                    state_signature_before=state_before,
                    state_signature_after=state_after,
                    evidence_refs=[_item_to_ref(i) for i in items],
                    metadata={"manifest_uri": "evidence_manifest.json"},
                )
            )

        def write_manifest() -> None:
            manifest = EvidenceManifestV1(
                run_id=run_id,
                policy=EvidencePolicyV1(
                    always=[EvidenceKindV1.dom_snapshot_partial],
                    on_failure_or_critical=[EvidenceKindV1.html_full, EvidenceKindV1.screenshot],
                ),
                redaction=RedactionPolicyV1(enabled=False, rules=[]),
                items=manifest_items or [
                    EvidenceItemV1(
                        kind=EvidenceKindV1.dom_snapshot_partial,
                        step_id="none",
                        relative_path="evidence/dom/none.json",
                        sha256="0" * 64,
                        size_bytes=0,
                    )
                ],
                metadata={"execution_mode": self.execution_mode},
            )
            manifest_path.write_text(json.dumps(manifest.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

        def emit_policy_halt(step_id: str, state_before: Optional[StateSignatureV1], reason: str, details: Dict[str, Any]) -> None:
            err = ExecutorErrorV1(
                error_code="POLICY_HALT",
                stage=ErrorStageV1.policy,
                severity=ErrorSeverityV1.critical,
                message=f"policy halt: {reason}",
                retryable=False,
                details={"policy_reason": reason, **details},
            )
            emit(
                TraceEventV1(
                    run_id=run_id,
                    seq=0,
                    event_type=TraceEventTypeV1.policy_halt,
                    step_id=step_id,
                    state_signature_before=state_before,
                    state_signature_after=None,
                    error=err,
                    metadata={"policy": details},
                )
            )
            emit(
                TraceEventV1(
                    run_id=run_id,
                    seq=0,
                    event_type=TraceEventTypeV1.run_finished,
                    step_id=None,
                    state_signature_before=None,
                    state_signature_after=state_before,
                    metadata={"status": "halted"},
                )
            )
            write_manifest()

        emit(
            TraceEventV1(
                run_id=run_id,
                seq=0,
                event_type=TraceEventTypeV1.run_started,
                step_id=None,
                state_signature_before=None,
                state_signature_after=None,
                metadata={
                    "execution_mode": self.execution_mode,
                    "domain_allowlist": self.domain_allowlist,
                    "policy": asdict(self.policy),
                },
            )
        )

        ctrl = BrowserController(profile=self.profile)
        try:
            ctrl.start(headless=headless)
            ctrl.navigate(url, timeout_ms=self.profile.navigation_timeout_ms)

            # initial observation (step_init)
            dom0, s0, items0 = ctrl.capture_observation(step_id="step_init", evidence_dir=evidence_dir, phase="before")
            state_key0 = _state_key(s0)
            seen_states[state_key0] = 1
            emit(
                TraceEventV1(
                    run_id=run_id,
                    seq=0,
                    event_type=TraceEventTypeV1.observation_captured,
                    step_id="step_init",
                    state_signature_before=s0,
                    state_signature_after=None,
                    metadata={
                        "policy": {
                            "steps_taken": 0,
                            "hard_cap_steps": self.policy.hard_cap_steps,
                            "same_state_revisit_count": 1,
                            "same_state_revisit_threshold": self.policy.same_state_revisits,
                        },
                        "phase": "before",
                    },
                )
            )
            add_evidence("step_init", s0, None, items0)

            current_sig: StateSignatureV1 = s0
            last_state_keys = [_state_key(s0)]

            # Step loop
            for i, action in enumerate(actions):
                if i >= self.policy.hard_cap_steps:
                    emit_policy_halt(f"step_{i:03d}", current_sig, "hard_cap_steps", {"hard_cap_steps": self.policy.hard_cap_steps})
                    return run_dir

                step_id = f"step_{i:03d}"

                # action_compiled
                emit(
                    TraceEventV1(
                        run_id=run_id,
                        seq=0,
                        event_type=TraceEventTypeV1.action_compiled,
                        step_id=step_id,
                        state_signature_before=current_sig,
                        state_signature_after=None,
                        action_spec=action,
                        metadata={},
                    )
                )

                # observation_captured before
                dom_b, sig_b, items_b = ctrl.capture_observation(step_id=step_id, evidence_dir=evidence_dir, phase="before")
                current_sig = sig_b
                before_key = _state_key(sig_b)
                # registrar sin incrementar conteo por "before"; el conteo relevante es por after (progreso/no progreso)
                seen_states.setdefault(before_key, 0)
                emit(
                    TraceEventV1(
                        run_id=run_id,
                        seq=0,
                        event_type=TraceEventTypeV1.observation_captured,
                        step_id=step_id,
                        state_signature_before=sig_b,
                        state_signature_after=None,
                        metadata={
                            "policy": {
                                "steps_taken": i,
                                "hard_cap_steps": self.policy.hard_cap_steps,
                                "same_state_revisit_count": seen_states.get(before_key, 0) or 1,
                                "same_state_revisit_threshold": self.policy.same_state_revisits,
                            },
                            "phase": "before",
                        },
                    )
                )
                add_evidence(step_id, sig_b, None, items_b)

                # Acciones críticas: capturar screenshot REAL before (policy)
                if action.criticality == "critical":
                    try:
                        add_evidence(step_id, sig_b, None, [ctrl.capture_screenshot_file(step_id=step_id, evidence_dir=evidence_dir, phase="before")])
                    except Exception:
                        pass

                # validate_runtime (U5 etc)
                try:
                    validate_runtime(action, ctrl, self.profile)
                except ExecutorTypedException as te:
                    emit(
                        TraceEventV1(
                            run_id=run_id,
                            seq=0,
                            event_type=TraceEventTypeV1.error_raised,
                            step_id=step_id,
                            state_signature_before=sig_b,
                            state_signature_after=None,
                            error=te.error,
                            metadata={"phase": "validate_runtime"},
                        )
                    )
                    # evidence extra on failure/critical
                    extra: List[EvidenceItemV1] = []
                    try:
                        extra.append(ctrl.capture_html_full(step_id=step_id, evidence_dir=evidence_dir, phase="after"))
                        extra.append(ctrl.capture_screenshot_file(step_id=step_id, evidence_dir=evidence_dir, phase="after"))
                    except Exception:
                        pass
                    add_evidence(step_id, sig_b, None, extra)
                    emit(
                        TraceEventV1(
                            run_id=run_id,
                            seq=0,
                            event_type=TraceEventTypeV1.run_finished,
                            step_id=None,
                            state_signature_before=None,
                            state_signature_after=sig_b,
                            metadata={"status": "failed"},
                        )
                    )
                    write_manifest()
                    return run_dir

                # Preconditions checked
                pre_evals = evaluate_conditions(action.preconditions, ctrl, self.profile, policy_state, timeout_ms=action.timeout_ms)
                pre_ok = all(ev.ok or ev.condition.severity == ErrorSeverityV1.warning for ev in pre_evals)
                emit(
                    TraceEventV1(
                        run_id=run_id,
                        seq=0,
                        event_type=TraceEventTypeV1.preconditions_checked,
                        step_id=step_id,
                        state_signature_before=sig_b,
                        state_signature_after=None,
                        metadata={
                            "ok": pre_ok,
                            "evaluations": [
                                {"kind": ev.condition.kind.value, "ok": ev.ok, "details": ev.details, "severity": ev.condition.severity.value}
                                for ev in pre_evals
                            ],
                        },
                    )
                )

                def classify_precondition_error() -> ExecutorErrorV1:
                    # U1 mapping: element_count_equals==1 -> target errors
                    for ev in pre_evals:
                        if ev.condition.kind == ConditionKindV1.element_count_equals and int(ev.details.get("expected", ev.condition.args.get("count", -1))) == 1:
                            actual = ev.details.get("actual")
                            if actual == 0:
                                code = "TARGET_NOT_FOUND"
                            else:
                                code = "TARGET_NOT_UNIQUE"
                            return ExecutorErrorV1(
                                error_code=code,
                                stage=ErrorStageV1.precondition,
                                severity=ErrorSeverityV1.error,
                                message="target count constraint failed",
                                retryable=False,
                                details={"expected": 1, "actual": actual},
                            )
                    # overlay blocking mapping
                    for ev in pre_evals:
                        if ev.condition.kind == ConditionKindV1.no_blocking_overlay and not ev.ok:
                            return ExecutorErrorV1(
                                error_code="OVERLAY_BLOCKING",
                                stage=ErrorStageV1.precondition,
                                severity=ErrorSeverityV1.error,
                                message="blocking overlay detected",
                                retryable=True,
                                details=ev.details,
                            )
                    return ExecutorErrorV1(
                        error_code="PRECONDITION_FAILED",
                        stage=ErrorStageV1.precondition,
                        severity=ErrorSeverityV1.error,
                        message="precondition failed",
                        retryable=False,
                        details={"failed": [ev.condition.kind.value for ev in pre_evals if not ev.ok]},
                    )

                # Retry/recovery loop per action
                attempt = 0
                action_error: Optional[ExecutorErrorV1] = None
                state_after: Optional[StateSignatureV1] = None

                while True:
                    if not pre_ok:
                        action_error = classify_precondition_error()
                    else:
                        # action_started
                        emit(
                            TraceEventV1(
                                run_id=run_id,
                                seq=0,
                                event_type=TraceEventTypeV1.action_started,
                                step_id=step_id,
                                state_signature_before=sig_b,
                                state_signature_after=None,
                                metadata={"attempt": attempt},
                            )
                        )

                        try:
                            dur_ms = execute_action_only(action, ctrl, self.profile, policy_state)
                            emit(
                                TraceEventV1(
                                    run_id=run_id,
                                    seq=0,
                                    event_type=TraceEventTypeV1.action_executed,
                                    step_id=step_id,
                                    state_signature_before=sig_b,
                                    state_signature_after=None,
                                    metadata={"duration_ms": dur_ms, "attempt": attempt},
                                )
                            )
                            action_error = None
                        except ExecutorTypedException as te:
                            action_error = te.error

                    # capture after + postconditions/asserts
                    dom_a, sig_a, items_a = ctrl.capture_observation(step_id=step_id, evidence_dir=evidence_dir, phase="after")
                    state_after = sig_a
                    add_evidence(step_id, sig_b, sig_a, items_a)
                    emit(
                        TraceEventV1(
                            run_id=run_id,
                            seq=0,
                            event_type=TraceEventTypeV1.observation_captured,
                            step_id=step_id,
                            state_signature_before=sig_a,
                            state_signature_after=None,
                            metadata={
                                "policy": {
                                    "steps_taken": i + 1,
                                    "hard_cap_steps": self.policy.hard_cap_steps,
                                "same_state_revisit_count": seen_states.get(_state_key(sig_a), 0) or 1,
                                    "same_state_revisit_threshold": self.policy.same_state_revisits,
                                },
                                "phase": "after",
                            },
                        )
                    )

                    # Acciones críticas: capturar html_full + screenshot REAL after (policy)
                    if action.criticality == "critical":
                        extra_crit: List[EvidenceItemV1] = []
                        try:
                            extra_crit.append(ctrl.capture_html_full(step_id=step_id, evidence_dir=evidence_dir, phase="after"))
                            extra_crit.append(ctrl.capture_screenshot_file(step_id=step_id, evidence_dir=evidence_dir, phase="after"))
                        except Exception:
                            pass
                        add_evidence(step_id, sig_b, sig_a, extra_crit)

                    if action_error is None:
                        post_evals = evaluate_conditions(action.postconditions, ctrl, self.profile, policy_state, timeout_ms=action.timeout_ms)
                        post_ok = all(ev.ok or ev.condition.severity == ErrorSeverityV1.warning for ev in post_evals)
                        emit(
                            TraceEventV1(
                                run_id=run_id,
                                seq=0,
                                event_type=TraceEventTypeV1.postconditions_checked,
                                step_id=step_id,
                                state_signature_before=sig_b,
                                state_signature_after=sig_a,
                                metadata={
                                    "ok": post_ok,
                                    "evaluations": [
                                        {"kind": ev.condition.kind.value, "ok": ev.ok, "details": ev.details, "severity": ev.condition.severity.value}
                                        for ev in post_evals
                                    ],
                                },
                            )
                        )
                        if action.kind == ActionKindV1.assert_:
                            ass_evals = evaluate_conditions(action.assertions or action.postconditions, ctrl, self.profile, policy_state, timeout_ms=action.timeout_ms)
                            ass_ok = all(ev.ok or ev.condition.severity == ErrorSeverityV1.warning for ev in ass_evals)
                            emit(
                                TraceEventV1(
                                    run_id=run_id,
                                    seq=0,
                                    event_type=TraceEventTypeV1.assert_checked,
                                    step_id=step_id,
                                    state_signature_before=sig_b,
                                    state_signature_after=sig_a,
                                    metadata={
                                        "ok": ass_ok,
                                        "evaluations": [
                                            {"kind": ev.condition.kind.value, "ok": ev.ok, "details": ev.details, "severity": ev.condition.severity.value}
                                            for ev in ass_evals
                                        ],
                                    },
                                )
                            )
                            post_ok = post_ok and ass_ok
                        if post_ok:
                            current_sig = sig_a
                            break
                        action_error = ExecutorErrorV1(
                            error_code="POSTCONDITION_FAILED",
                            stage=ErrorStageV1.postcondition,
                            severity=ErrorSeverityV1.error,
                            message="postcondition failed",
                            retryable=True,
                            details={"failed": [ev.condition.kind.value for ev in post_evals if not ev.ok]},
                        )

                    # error path: emit error_raised
                    emit(
                        TraceEventV1(
                            run_id=run_id,
                            seq=0,
                            event_type=TraceEventTypeV1.error_raised,
                            step_id=step_id,
                            state_signature_before=sig_b,
                            state_signature_after=state_after,
                            error=action_error,
                            metadata={"attempt": attempt},
                        )
                    )

                    # evidence extra on failure or critical
                    extra: List[EvidenceItemV1] = []
                    if action.criticality == "critical" or action_error.stage in (ErrorStageV1.execution, ErrorStageV1.postcondition) or action_error.error_code in {"TARGET_NOT_FOUND", "TARGET_NOT_UNIQUE", "OVERLAY_BLOCKING"}:
                        try:
                            # en fallo: intentamos capturar html_full + screenshots before/after
                            extra.append(ctrl.capture_html_full(step_id=step_id, evidence_dir=evidence_dir, phase="after"))
                            extra.append(ctrl.capture_screenshot_file(step_id=step_id, evidence_dir=evidence_dir, phase="before"))
                            extra.append(ctrl.capture_screenshot_file(step_id=step_id, evidence_dir=evidence_dir, phase="after"))
                        except Exception:
                            pass
                        add_evidence(step_id, sig_b, state_after, extra)

                    # policy thresholds
                    if attempt >= self.policy.retries_per_action:
                        # try recovery if available
                        if policy_state.recovery_used >= self.policy.recovery_max:
                            emit_policy_halt(step_id, sig_b, "recovery_limit", {"recovery_used": policy_state.recovery_used, "recovery_max": self.policy.recovery_max})
                            return run_dir

                        # recovery chain v1 (determinista)
                        rec_done = False
                        # 1) dismiss_overlay
                        emit(
                            TraceEventV1(
                                run_id=run_id,
                                seq=0,
                                event_type=TraceEventTypeV1.recovery_started,
                                step_id=step_id,
                                state_signature_before=sig_b,
                                state_signature_after=state_after,
                                metadata={"kind": "dismiss_overlay"},
                            )
                        )
                        dismissed = self._dismiss_overlay(ctrl)
                        emit(
                            TraceEventV1(
                                run_id=run_id,
                                seq=0,
                                event_type=TraceEventTypeV1.recovery_finished,
                                step_id=step_id,
                                state_signature_before=sig_b,
                                state_signature_after=state_after,
                                metadata={"kind": "dismiss_overlay", "ok": dismissed},
                            )
                        )
                        policy_state.recovery_used += 1
                        if dismissed:
                            attempt = 0
                            rec_done = True

                        # 2) reload (once per run)
                        if not rec_done and self.policy.allow_reload_once and not reload_used:
                            emit(
                                TraceEventV1(
                                    run_id=run_id,
                                    seq=0,
                                    event_type=TraceEventTypeV1.recovery_started,
                                    step_id=step_id,
                                    state_signature_before=sig_b,
                                    state_signature_after=state_after,
                                    metadata={"kind": "reload"},
                                )
                            )
                            try:
                                ctrl.page.reload(timeout=self.profile.navigation_timeout_ms, wait_until="networkidle")
                                reload_used = True
                                ok_reload = True
                            except Exception:
                                ok_reload = False
                            emit(
                                TraceEventV1(
                                    run_id=run_id,
                                    seq=0,
                                    event_type=TraceEventTypeV1.recovery_finished,
                                    step_id=step_id,
                                    state_signature_before=sig_b,
                                    state_signature_after=state_after,
                                    metadata={"kind": "reload", "ok": ok_reload},
                                )
                            )
                            policy_state.recovery_used += 1
                            if ok_reload:
                                attempt = 0
                                rec_done = True

                        # 3) reselect_target (si hay alternativos)
                        if not rec_done:
                            alt = (action.metadata or {}).get("alternative_targets")
                            if isinstance(alt, list) and alt:
                                emit(
                                    TraceEventV1(
                                        run_id=run_id,
                                        seq=0,
                                        event_type=TraceEventTypeV1.recovery_started,
                                        step_id=step_id,
                                        state_signature_before=sig_b,
                                        state_signature_after=state_after,
                                        metadata={"kind": "reselect_target"},
                                    )
                                )
                                try:
                                    next_t = TargetV1.model_validate(alt[0])
                                    action.target = next_t
                                    ok_sel = True
                                except Exception:
                                    ok_sel = False
                                emit(
                                    TraceEventV1(
                                        run_id=run_id,
                                        seq=0,
                                        event_type=TraceEventTypeV1.recovery_finished,
                                        step_id=step_id,
                                        state_signature_before=sig_b,
                                        state_signature_after=state_after,
                                        metadata={"kind": "reselect_target", "ok": ok_sel},
                                    )
                                )
                                policy_state.recovery_used += 1
                                if ok_sel:
                                    attempt = 0
                                    rec_done = True

                        if not rec_done:
                            emit_policy_halt(step_id, sig_b, "recovery_exhausted", {"attempt": attempt})
                            return run_dir

                        # after recovery, re-check preconditions
                        pre_evals = evaluate_conditions(action.preconditions, ctrl, self.profile, policy_state, timeout_ms=action.timeout_ms)
                        pre_ok = all(ev.ok or ev.condition.severity == ErrorSeverityV1.warning for ev in pre_evals)
                        emit(
                            TraceEventV1(
                                run_id=run_id,
                                seq=0,
                                event_type=TraceEventTypeV1.preconditions_checked,
                                step_id=step_id,
                                state_signature_before=sig_b,
                                state_signature_after=None,
                                metadata={"ok": pre_ok, "evaluations": [{"kind": ev.condition.kind.value, "ok": ev.ok} for ev in pre_evals], "after_recovery": True},
                            )
                        )
                        continue

                    # retry path
                    attempt += 1
                    backoff = self.policy.backoff_ms[min(attempt - 1, len(self.policy.backoff_ms) - 1)]
                    emit(
                        TraceEventV1(
                            run_id=run_id,
                            seq=0,
                            event_type=TraceEventTypeV1.retry_scheduled,
                            step_id=step_id,
                            state_signature_before=sig_b,
                            state_signature_after=state_after,
                            metadata={"attempt": attempt, "max_retries": self.policy.retries_per_action},
                        )
                    )
                    emit(
                        TraceEventV1(
                            run_id=run_id,
                            seq=0,
                            event_type=TraceEventTypeV1.backoff_applied,
                            step_id=step_id,
                            state_signature_before=sig_b,
                            state_signature_after=state_after,
                            metadata={"backoff_ms": backoff},
                        )
                    )
                    time.sleep(backoff / 1000.0)
                    # re-evaluate preconditions for next attempt
                    pre_evals = evaluate_conditions(action.preconditions, ctrl, self.profile, policy_state, timeout_ms=action.timeout_ms)
                    pre_ok = all(ev.ok or ev.condition.severity == ErrorSeverityV1.warning for ev in pre_evals)
                    emit(
                        TraceEventV1(
                            run_id=run_id,
                            seq=0,
                            event_type=TraceEventTypeV1.preconditions_checked,
                            step_id=step_id,
                            state_signature_before=sig_b,
                            state_signature_after=None,
                            metadata={"ok": pre_ok, "evaluations": [{"kind": ev.condition.kind.value, "ok": ev.ok} for ev in pre_evals], "retry_attempt": attempt},
                        )
                    )
                    continue

                # update same-state revisit after action
                after_key = _state_key(current_sig)
                # criterio v1: se incrementa si after==before o coincide con uno reciente
                revisit = (after_key == before_key) or (after_key in last_state_keys)
                if revisit:
                    seen_states[after_key] = seen_states.get(after_key, 0) + 1
                else:
                    seen_states[after_key] = 1

                # ventana de estados recientes
                last_state_keys.append(after_key)
                if len(last_state_keys) > 5:
                    last_state_keys = last_state_keys[-5:]

                if seen_states[after_key] > self.policy.same_state_revisits:
                    emit_policy_halt(step_id, current_sig, "same_state_revisit", {"count": seen_states[after_key], "threshold": self.policy.same_state_revisits, "state_key": after_key})
                    return run_dir

            # finished
            emit(
                TraceEventV1(
                    run_id=run_id,
                    seq=0,
                    event_type=TraceEventTypeV1.run_finished,
                    step_id=None,
                    state_signature_before=None,
                    state_signature_after=current_sig,
                    metadata={"status": "success"},
                )
            )
            write_manifest()
            return run_dir

        finally:
            try:
                ctrl.close()
            except Exception:
                pass

    def _dismiss_overlay(self, ctrl: BrowserController) -> bool:
        """
        Recovery #1 (determinista): intenta cerrar overlay.
        Estrategia: probar selectores primero, luego textos.
        Requiere count==1 para click; si no, no actúa.
        """
        page = ctrl.page
        if not page:
            return False

        # Selectors
        for sel in self.policy.overlay_close_selectors:
            try:
                loc = page.locator(sel)
                if loc.count() == 1:
                    loc.first.click(timeout=self.profile.action_timeout_ms)
                    return True
            except Exception:
                continue

        # Text buttons (determinista; exige unicidad)
        for txt in self.policy.overlay_close_texts:
            try:
                loc = page.get_by_role("button", name=txt, exact=True)
                if loc.count() == 1:
                    loc.first.click(timeout=self.profile.action_timeout_ms)
                    return True
            except Exception:
                continue

        return False


