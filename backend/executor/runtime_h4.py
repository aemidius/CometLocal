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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.executor.action_compiler_v1 import (
    PolicyStateV1,
    evaluate_conditions,
    execute_action_only,
    validate_runtime,
)
from backend.executor.browser_controller import BrowserController, ExecutionProfileV1, ExecutorTypedException
from backend.executor.redaction_v1 import RedactorV1
from backend.inspector.document_inspector_v1 import DocumentInspectorV1
from backend.repository.document_repository_v1 import DocumentRepositoryV1
from backend.repository.secrets_store_v1 import SecretsStoreV1
from backend.shared.executor_contracts_v1 import (
    ExecutionModeV1,
    RuntimeExecutionMode,
    ActionKindV1,
    ActionSpecV1,
    ConditionKindV1,
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
        project_root: str | Path = ".",
        data_root: str | Path = "data",
        execution_mode: str | ExecutionModeV1 = ExecutionModeV1.training,
        domain_allowlist: Optional[List[str]] = None,
        profile: Optional[ExecutionProfileV1] = None,
        policy: Optional[RuntimePolicyDefaultsV1] = None,
        redaction_policy: Optional[RedactionPolicyV1] = None,
        document_repository: Optional[DocumentRepositoryV1] = None,
        document_inspector: Optional[DocumentInspectorV1] = None,
        secrets_store: Optional[SecretsStoreV1] = None,
    ):
        self.runs_root = Path(runs_root)
        self.execution_mode = ExecutionModeV1(execution_mode) if not isinstance(execution_mode, ExecutionModeV1) else execution_mode
        self.domain_allowlist = domain_allowlist or []
        self.profile = profile or ExecutionProfileV1()
        self.policy = policy or RuntimePolicyDefaultsV1()
        self.document_repository = document_repository or DocumentRepositoryV1(project_root=project_root, data_root=data_root)
        self.document_inspector = document_inspector or DocumentInspectorV1(repository=self.document_repository)
        self.secrets_store = secrets_store or SecretsStoreV1(base_dir=(Path(project_root).resolve() / data_root))
        # production => redaction always enabled (default conservador)
        if redaction_policy is None:
            enabled = True if self.execution_mode == ExecutionModeV1.production else True
            redaction_policy = RedactionPolicyV1(enabled=enabled, rules=["emails", "phone", "dni", "tokens"], mode=self.execution_mode)
        self.redaction_policy = redaction_policy

    def run_actions(self, *, url: str, actions: List[ActionSpecV1], headless: bool = True, fail_fast: bool = False, execution_mode: RuntimeExecutionMode = "explore") -> Path:
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

        # H8.E2: Status final por defecto es SUCCESS (solo cambia si hay errores explícitos)
        # Nota: No usar anotaciones de tipo aquí para permitir nonlocal en funciones anidadas
        final_status = "success"
        last_error = None
        error_code = None
        
        # Fix: Inicializar contadores y timestamps para run_finished.json
        retry_count = 0
        recovery_count = 0
        same_state_revisits_max: Optional[int] = None
        started_at: Optional[str] = None
        finished_at: Optional[str] = None
        duration_ms: Optional[int] = None
        finished_path = run_dir / "run_finished.json"

        policy_state = PolicyStateV1()
        # H8.C: deterministic mode => sin policy engine, sin retries/recovery, sin POLICY_HALT, stop inmediato en el primer error.
        # H8.B: fail-fast (login flows) => sin retries/recovery, caps estrictos, stop inmediato en el primer error.
        is_deterministic = execution_mode == "deterministic"
        policy_defaults = self.policy
        if is_deterministic or fail_fast:
            policy_defaults = RuntimePolicyDefaultsV1(
                retries_per_action=0,
                recovery_max=0,
                same_state_revisits=1,
                hard_cap_steps=len(actions) + 2,
                backoff_ms=self.policy.backoff_ms,
                allow_reload_once=False,
                overlay_close_selectors=self.policy.overlay_close_selectors,
                overlay_close_texts=self.policy.overlay_close_texts,
            )
        seen_states: Dict[str, int] = {}  # state_key -> count
        last_state_keys: List[str] = []  # ventana corta para "coincide con uno reciente"
        reload_used = False
        inputs_used: List[str] = []
        inspected_hashes: Dict[str, str] = {}  # file_ref -> doc_hash (para evitar repetir en el mismo run)

        redactor = RedactorV1(enabled=bool(self.redaction_policy.enabled), strict=True)

        def emit(ev: TraceEventV1) -> None:
            nonlocal seq
            seq += 1
            ev.seq = seq
            with open(trace_path, "a", encoding="utf-8") as f:
                payload = ev.model_dump(mode="json")
                # redaction en trace payload
                payload = redactor.redact_jsonable(payload)
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")

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
                redaction=RedactionPolicyV1(enabled=bool(self.redaction_policy.enabled), rules=list(self.redaction_policy.rules or []), mode=self.execution_mode),
                items=manifest_items or [
                    EvidenceItemV1(
                        kind=EvidenceKindV1.dom_snapshot_partial,
                        step_id="none",
                        relative_path="evidence/dom/none.json",
                        sha256="0" * 64,
                        size_bytes=0,
                    )
                ],
                redaction_report=dict(redactor.report.counts) if redactor.enabled else None,
                metadata={
                    "execution_mode": self.execution_mode.value,
                    "redaction_enabled": bool(self.redaction_policy.enabled),
                    "inputs_used": sorted(set(inputs_used)),
                },
            )
            manifest_path.write_text(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")

        def _write_run_finished_json(
            path: Path,
            run_id: str,
            status: str,
            started_at_val: Optional[str],
            finished_at_val: Optional[str],
            duration_ms_val: Optional[int],
            error_val: Optional[str],
            error_code_val: Optional[str],
            retry_count_val: int,
            recovery_count_val: int,
            same_state_revisits_max_val: Optional[int],
        ) -> None:
            """Fix: Escribe run_finished.json con metadata completa del run."""
            data = {
                "run_id": run_id,
                "status": status,
                "started_at": started_at_val,
                "finished_at": finished_at_val,
                "duration_ms": duration_ms_val,
                "last_error": error_code_val or error_val,
                "counters": {
                    "retries": retry_count_val,
                    "recoveries": recovery_count_val,
                    "same_state_revisits_max": same_state_revisits_max_val,
                },
            }
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        def emit_run_finished(status: str, reason: Optional[str] = None, error: Optional[str] = None, error_code_val: Optional[str] = None, state_after: Optional[StateSignatureV1] = None) -> None:
            """
            H8.E2: Helper centralizado para emitir run_finished con status final.
            Asegura que siempre se emite y que el status es consistente.
            """
            nonlocal final_status, last_error, error_code, finished_at, duration_ms
            # Actualizar variables globales
            final_status = status
            if error:
                last_error = error
            if error_code_val:
                error_code = error_code_val
            
            # H8.E2: Assert lógico - si no hay error, no puede ser failed
            if status == "failed" and error is None and error_code_val is None:
                # Permitir si hay reason (policy halt, etc.)
                if not reason:
                    raise AssertionError(f"status='failed' but no error/error_code provided (reason={reason})")
            
            finished_at = datetime.now(timezone.utc).isoformat()
            if started_at:
                try:
                    started_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                    finished_dt = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
                    duration_ms = int((finished_dt - started_dt).total_seconds() * 1000)
                except Exception:
                    pass
            
            emit(
                TraceEventV1(
                    run_id=run_id,
                    seq=0,
                    event_type=TraceEventTypeV1.run_finished,
                    step_id=None,
                    state_signature_before=None,
                    state_signature_after=state_after,
                    metadata={
                        "status": status,
                        **({"reason": reason} if reason else {}),
                        **({"error": error} if error else {}),
                        **({"error_code": error_code_val} if error_code_val else {}),
                    },
                )
            )
            
            # Fix: Escribir run_finished.json
            _write_run_finished_json(
                finished_path, run_id, status, started_at, finished_at, duration_ms,
                error, error_code_val, retry_count, recovery_count, same_state_revisits_max
            )

        def emit_policy_halt(step_id: str, state_before: Optional[StateSignatureV1], reason: str, details: Dict[str, Any]) -> None:
            nonlocal final_status, last_error, error_code
            final_status = "halted"
            last_error = "POLICY_HALT"
            error_code = "POLICY_HALT"
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
            emit_run_finished("halted", reason=f"policy_halt:{reason}", error="POLICY_HALT", error_code_val="POLICY_HALT", state_after=state_before)
            write_manifest()

        started_at = datetime.now(timezone.utc).isoformat()
        emit(
            TraceEventV1(
                run_id=run_id,
                seq=0,
                event_type=TraceEventTypeV1.run_started,
                step_id=None,
                state_signature_before=None,
                state_signature_after=None,
                metadata={
                    "execution_mode": self.execution_mode.value,
                    "runtime_execution_mode": execution_mode,
                    "domain_allowlist": self.domain_allowlist,
                    "policy": asdict(policy_defaults),
                    "fail_fast": bool(fail_fast),
                },
            )
        )

        ctrl = BrowserController(profile=self.profile)
        try:
            ctrl.start(headless=headless)
            ctrl.navigate(url, timeout_ms=self.profile.navigation_timeout_ms)

            # initial observation (step_init)
            dom0, s0, items0 = ctrl.capture_observation(step_id="step_init", evidence_dir=evidence_dir, phase="before", redactor=redactor)
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
                            "hard_cap_steps": policy_defaults.hard_cap_steps,
                            "same_state_revisit_count": 1,
                            "same_state_revisit_threshold": policy_defaults.same_state_revisits,
                        },
                        "phase": "before",
                    },
                )
            )
            add_evidence("step_init", s0, None, items0)

            current_sig: StateSignatureV1 = s0
            last_state_keys = [_state_key(s0)]
            
            # Fix: Flag para rastrear si el run ya terminó exitosamente
            run_completed_successfully = False

            # Step loop
            for i, action in enumerate(actions):
                # Fix: Policy guard - no evaluar hard_cap_steps si el run ya terminó exitosamente
                if run_completed_successfully:
                    final_status = "success"
                    emit_run_finished("success", reason="POSTCONDITIONS_OK", state_after=current_sig)
                    write_manifest()
                    return run_dir
                
                if i >= policy_defaults.hard_cap_steps:
                    # H8.C: deterministic mode nunca emite POLICY_HALT, solo FAILED
                    if is_deterministic:
                        emit_run_finished("failed", reason="hard_cap_steps", error="hard_cap_steps", error_code_val="HARD_CAP_STEPS", state_after=current_sig)
                        write_manifest()
                        return run_dir
                    emit_policy_halt(f"step_{i:03d}", current_sig, "hard_cap_steps", {"hard_cap_steps": policy_defaults.hard_cap_steps})
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
                dom_b, sig_b, items_b = ctrl.capture_observation(step_id=step_id, evidence_dir=evidence_dir, phase="before", redactor=redactor)
                current_sig = sig_b
                before_key = _state_key(sig_b)
                # registrar sin incrementar conteo por "before"; el conteo relevante es por after (progreso/no progreso)
                seen_states.setdefault(before_key, 0)
                current_revisit_count = seen_states.get(before_key, 0) or 1
                if isinstance(current_revisit_count, int):
                    same_state_revisits_max = max(same_state_revisits_max or 0, current_revisit_count)
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
                                "hard_cap_steps": policy_defaults.hard_cap_steps,
                                "same_state_revisit_count": current_revisit_count,
                                "same_state_revisit_threshold": policy_defaults.same_state_revisits,
                            },
                            "phase": "before",
                        },
                    )
                )
                add_evidence(step_id, sig_b, None, items_b)

                # Acciones críticas: capturar screenshot REAL before (policy)
                # training: evidencia rica (html_full/screenshot sampling)
                training_html_every = 1
                training_shot_every = 1

                if action.criticality == "critical":
                    try:
                        if self.execution_mode == ExecutionModeV1.training:
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
                        extra.append(ctrl.capture_html_full(step_id=step_id, evidence_dir=evidence_dir, phase="after", redactor=redactor))
                        if self.execution_mode == ExecutionModeV1.training:
                            extra.append(ctrl.capture_screenshot_file(step_id=step_id, evidence_dir=evidence_dir, phase="after"))
                    except Exception:
                        pass
                    add_evidence(step_id, sig_b, None, extra)
                    emit_run_finished("failed", reason="validate_runtime", error=str(te.error.error_code), error_code_val=te.error.error_code, state_after=sig_b)
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
                        # H7.6: inspección determinista antes de uploads
                        if action.kind == ActionKindV1.upload:
                            file_ref = (action.input or {}).get("file_ref")
                            if file_ref:
                                inputs_used.append(str(file_ref))
                                # inspeccionar una vez por file_ref por run (cache global maneja sha256)
                                if str(file_ref) not in inspected_hashes:
                                    emit(
                                        TraceEventV1(
                                            run_id=run_id,
                                            seq=0,
                                            event_type=TraceEventTypeV1.inspection_started,
                                            step_id=step_id,
                                            state_signature_before=sig_b,
                                            state_signature_after=None,
                                            metadata={"file_ref": str(file_ref)},
                                        )
                                    )
                                    try:
                                        status, report = self.document_inspector.inspect(file_ref=str(file_ref))
                                    except Exception as e:
                                        status = "failed"
                                        report = None
                                        emit(
                                            TraceEventV1(
                                                run_id=run_id,
                                                seq=0,
                                                event_type=TraceEventTypeV1.inspection_finished,
                                                step_id=step_id,
                                                state_signature_before=sig_b,
                                                state_signature_after=None,
                                                metadata={"file_ref": str(file_ref), "status": "failed", "cause": repr(e)},
                                            )
                                        )
                                        action_error = ExecutorErrorV1(
                                            error_code="DOCUMENT_PARSE_FAILED",
                                            stage=ErrorStageV1.precondition,
                                            severity=ErrorSeverityV1.error,
                                            message="document inspection failed",
                                            retryable=False,
                                            details={"file_ref": str(file_ref), "cause": repr(e)},
                                        )
                                    else:
                                        report_path = (
                                            self.document_repository.cfg.documents_dir
                                            / "_inspections"
                                            / f"{getattr(report, 'doc_hash', '')}.json"
                                        )
                                        report_ref = None
                                        try:
                                            report_ref = str(report_path.relative_to(self.document_repository.cfg.project_root)).replace("\\", "/")
                                        except Exception:
                                            report_ref = str(report_path).replace("\\", "/")
                                        emit(
                                            TraceEventV1(
                                                run_id=run_id,
                                                seq=0,
                                                event_type=TraceEventTypeV1.inspection_finished,
                                                step_id=step_id,
                                                state_signature_before=sig_b,
                                                state_signature_after=None,
                                                metadata={
                                                    "file_ref": str(file_ref),
                                                    "status": status,
                                                    "doc_hash": getattr(report, "doc_hash", None) if report else None,
                                                    "criteria_profile": getattr(report, "criteria_profile", None) if report else None,
                                                    "report_ref": report_ref if report and getattr(report, "doc_hash", None) else None,
                                                },
                                            )
                                        )
                                        if report and getattr(report, "doc_hash", None):
                                            inspected_hashes[str(file_ref)] = str(report.doc_hash)
                                        if status != "ok":
                                            action_error = ExecutorErrorV1(
                                                error_code="DOC_CRITERIA_FAILED",
                                                stage=ErrorStageV1.precondition,
                                                severity=ErrorSeverityV1.error,
                                                message="document criteria failed",
                                                retryable=False,
                                                details={
                                                    "file_ref": str(file_ref),
                                                    "criteria_profile": getattr(report, "criteria_profile", None) if report else None,
                                                    "report_ref": report_ref,
                                                },
                                            )
                        # Si la inspección falló, no ejecutar acción ni retry: abort determinista.
                        if action_error is not None and action.kind == ActionKindV1.upload:
                            # H8.E2: Actualizar final_status cuando hay error_raised (no necesita nonlocal, está en el mismo scope)
                            final_status = "failed"
                            last_error = str(action_error.message) if action_error else "document criteria failed"
                            error_code = action_error.error_code if action_error else "DOC_CRITERIA_FAILED"
                            
                            emit(
                                TraceEventV1(
                                    run_id=run_id,
                                    seq=0,
                                    event_type=TraceEventTypeV1.error_raised,
                                    step_id=step_id,
                                    state_signature_before=sig_b,
                                    state_signature_after=None,
                                    error=action_error,
                                    metadata={"phase": "inspection"},
                                )
                            )
                            emit_run_finished("failed", reason="document_criteria_failed", error=last_error, error_code_val=error_code, state_after=sig_b)
                            write_manifest()
                            ctrl.close()
                            return run_dir

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
                            dur_ms = execute_action_only(
                                action,
                                ctrl,
                                self.profile,
                                policy_state,
                                document_repository=self.document_repository,
                                secrets_store=self.secrets_store,
                            )
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
                    dom_a, sig_a, items_a = ctrl.capture_observation(step_id=step_id, evidence_dir=evidence_dir, phase="after", redactor=redactor)
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
                            extra_crit.append(ctrl.capture_html_full(step_id=step_id, evidence_dir=evidence_dir, phase="after", redactor=redactor))
                            if self.execution_mode == ExecutionModeV1.training:
                                extra_crit.append(ctrl.capture_screenshot_file(step_id=step_id, evidence_dir=evidence_dir, phase="after"))
                        except Exception:
                            pass
                        add_evidence(step_id, sig_b, sig_a, extra_crit)

                    # training: captura extra cada N steps (default conservador: cada step)
                    if self.execution_mode == ExecutionModeV1.training:
                        extra_train: List[EvidenceItemV1] = []
                        try:
                            if training_html_every and (i % training_html_every == 0):
                                extra_train.append(ctrl.capture_html_full(step_id=step_id, evidence_dir=evidence_dir, phase="after", redactor=redactor))
                            if training_shot_every and (i % training_shot_every == 0):
                                extra_train.append(ctrl.capture_screenshot_file(step_id=step_id, evidence_dir=evidence_dir, phase="after"))
                        except Exception:
                            pass
                        add_evidence(step_id, sig_b, sig_a, extra_train)

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
                            # Fix: Si las postcondiciones se cumplen, actualizar estado y continuar
                            current_sig = sig_a
                            # Si es la última acción, terminar inmediatamente como SUCCESS
                            if i == len(actions) - 1:
                                # Última acción completada exitosamente - terminar inmediatamente
                                final_status = "success"
                                run_completed_successfully = True
                                emit_run_finished("success", reason="POSTCONDITIONS_OK", state_after=current_sig)
                                write_manifest()
                                return run_dir
                            # Si no es la última acción, continuar con la siguiente (break del loop de attempts)
                            break
                        # Heurística determinista para AUTH_FAILED:
                        # - Si falla un url_matches y la URL actual contiene "login", AUTH_FAILED.
                        # - Si falla element_not_visible sobre un input típico de login (ClientName/Username/Password), AUTH_FAILED.
                        # - Si falla element_visible sobre selector de logout/desconectar, AUTH_FAILED.
                        auth_failed = False
                        try:
                            for ev in post_evals:
                                if ev.ok:
                                    continue
                                if ev.condition.kind == ConditionKindV1.url_matches:
                                    actual = str((ev.details or {}).get("actual") or "").lower()
                                    if "login" in actual:
                                        auth_failed = True
                                        break
                                if ev.condition.kind == ConditionKindV1.element_not_visible:
                                    # detecta "seguimos viendo el formulario" por selector del target
                                    tgt = (ev.condition.args or {}).get("target") or {}
                                    sel = (tgt.get("selector") or tgt.get("testid") or tgt.get("text") or "") if isinstance(tgt, dict) else ""
                                    sel_l = str(sel).lower()
                                    if any(x in sel_l for x in ("clientname", "username", "password")):
                                        auth_failed = True
                                        break
                                if ev.condition.kind == ConditionKindV1.element_visible:
                                    tgt = (ev.condition.args or {}).get("target") or {}
                                    sel = (tgt.get("selector") or "") if isinstance(tgt, dict) else ""
                                    sel_l = str(sel).lower()
                                    if any(x in sel_l for x in ("logout", "desconectar")):
                                        auth_failed = True
                                        break
                        except Exception:
                            auth_failed = False

                        action_error = ExecutorErrorV1(
                            error_code="AUTH_FAILED" if auth_failed else "POSTCONDITION_FAILED",
                            stage=ErrorStageV1.postcondition,
                            severity=ErrorSeverityV1.error,
                            message="auth failed" if auth_failed else "postcondition failed",
                            retryable=True,
                            details={"failed": [ev.condition.kind.value for ev in post_evals if not ev.ok], "auth_failed": auth_failed},
                        )

                    # error path: emit error_raised
                    # H8.E2: Actualizar final_status cuando hay error_raised (no necesita nonlocal, está en el mismo scope)
                    final_status = "failed"
                    last_error = str(action_error.message) if action_error else "action failed"
                    error_code = action_error.error_code if action_error else "UNKNOWN_ERROR"
                    
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
                            extra.append(ctrl.capture_html_full(step_id=step_id, evidence_dir=evidence_dir, phase="after", redactor=redactor))
                            if self.execution_mode == ExecutionModeV1.training:
                                extra.append(ctrl.capture_screenshot_file(step_id=step_id, evidence_dir=evidence_dir, phase="before"))
                                extra.append(ctrl.capture_screenshot_file(step_id=step_id, evidence_dir=evidence_dir, phase="after"))
                        except Exception:
                            pass
                        add_evidence(step_id, sig_b, state_after, extra)

                    # H8.C: deterministic mode => primer error termina el run como failed (sin retries/recovery/policy_halt)
                    # H8.B: fail_fast => primer error termina el run como failed (sin retries/recovery/policy_halt)
                    if is_deterministic or fail_fast:
                        err_code = action_error.error_code if action_error else "UNKNOWN_ERROR"
                        err_msg = str(action_error.message) if action_error else "action failed"
                        emit_run_finished("failed", reason="fail_fast_or_deterministic", error=err_msg, error_code_val=err_code, state_after=sig_b)
                        write_manifest()
                        return run_dir

                    # policy thresholds
                    if attempt >= policy_defaults.retries_per_action:
                        # try recovery if available
                        if policy_state.recovery_used >= policy_defaults.recovery_max:
                            # H8.C: deterministic mode nunca emite POLICY_HALT, solo FAILED
                            if is_deterministic:
                                emit_run_finished("failed", reason="recovery_limit", error="recovery_limit", error_code_val="RECOVERY_LIMIT", state_after=sig_b)
                                write_manifest()
                                return run_dir
                            emit_policy_halt(step_id, sig_b, "recovery_limit", {"recovery_used": policy_state.recovery_used, "recovery_max": policy_defaults.recovery_max})
                            return run_dir

                        # recovery chain v1 (determinista)
                        rec_done = False
                        # 1) dismiss_overlay
                        recovery_count += 1  # Fix: Contador para run_finished.json
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
                        if not rec_done and policy_defaults.allow_reload_once and not reload_used:
                            recovery_count += 1  # Fix: Contador para run_finished.json
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
                                recovery_count += 1  # Fix: Contador para run_finished.json
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
                            # H8.C: deterministic mode nunca emite POLICY_HALT, solo FAILED
                            if is_deterministic:
                                emit_run_finished("failed", reason="recovery_exhausted", error="recovery_exhausted", error_code_val="RECOVERY_EXHAUSTED", state_after=sig_b)
                                write_manifest()
                                return run_dir
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
                    retry_count += 1  # Fix: Contador para run_finished.json
                    backoff = policy_defaults.backoff_ms[min(attempt - 1, len(policy_defaults.backoff_ms) - 1)]
                    emit(
                        TraceEventV1(
                            run_id=run_id,
                            seq=0,
                            event_type=TraceEventTypeV1.retry_scheduled,
                            step_id=step_id,
                            state_signature_before=sig_b,
                            state_signature_after=state_after,
                            metadata={"attempt": attempt, "max_retries": policy_defaults.retries_per_action},
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

                # Fix: Policy guard - no evaluar políticas si el run ya terminó exitosamente
                if run_completed_successfully:
                    # Si el run ya completó exitosamente, terminar inmediatamente
                    final_status = "success"
                    emit_run_finished("success", reason="POSTCONDITIONS_OK", state_after=current_sig)
                    write_manifest()
                    return run_dir
                
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

                if seen_states[after_key] > policy_defaults.same_state_revisits:
                    # H8.C: deterministic mode nunca emite POLICY_HALT, solo FAILED
                    if is_deterministic:
                        emit_run_finished("failed", reason="same_state_revisit", error="same_state_revisit", error_code_val="SAME_STATE_REVISIT", state_after=current_sig)
                        write_manifest()
                        return run_dir
                    emit_policy_halt(step_id, current_sig, "same_state_revisit", {"count": seen_states[after_key], "threshold": policy_defaults.same_state_revisits, "state_key": after_key})
                    return run_dir

            # H8.E2: finished - si llegamos aquí sin errores, es SUCCESS
            # Regla definitiva: un run es SUCCESS si:
            # - No hay excepción
            # - No hay error_raised
            # - Todas las acciones terminaron
            # - Las postcondiciones se evaluaron
            # H8.E2: Usar final_status (que por defecto es "success") para asegurar consistencia
            emit_run_finished(final_status, state_after=current_sig)
            write_manifest()
            return run_dir

        except Exception as e:
            # H8.E2: capturar cualquier excepción no esperada y marcar failed
            # Esto asegura que siempre se emite run_finished, incluso si hay errores no tipificados
            try:
                emit_run_finished("failed", reason="unexpected_exception", error=str(e), error_code_val="UNEXPECTED_EXCEPTION", state_after=current_sig if 'current_sig' in locals() else None)
                write_manifest()
            except Exception:
                pass  # Si falla emitir, al menos intentamos
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


