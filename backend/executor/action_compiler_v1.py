"""
H3 — ActionSpecV1 -> Playwright (via BrowserController) + enforcement U1–U5

Alcance H3 (acciones soportadas):
- navigate
- click
- fill (fill_text)
- wait_for (wait_until por Condition.kind)
- assert (assert_checked como acción)
- upload (upload_file directo a input[type=file])

No usa LLM. No escribe trace: devuelve resultados para que el runtime emita eventos.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from backend.executor.browser_controller import BrowserController, ExecutionProfileV1, ExecutorTypedException
from backend.shared.executor_contracts_v1 import (
    ActionKindV1,
    ActionResultV1,
    ActionSpecV1,
    ActionStatusV1,
    ConditionKindV1,
    ConditionV1,
    EvidenceItemV1,
    ExecutorErrorV1,
    ErrorStageV1,
    ErrorSeverityV1,
    StateSignatureV1,
    TargetV1,
)


@dataclass
class PolicyStateV1:
    """
    Policy mínima para H3 (solo runtime-side flags).
    """

    retries_used: int = 0
    recovery_used: int = 0
    same_state_revisit_count: int = 1
    download_started: bool = False
    last_download_url: Optional[str] = None


@dataclass
class ConditionEvaluation:
    condition: ConditionV1
    ok: bool
    details: Dict[str, Any]


@dataclass
class ActionExecutionResult:
    status: ActionStatusV1
    error: Optional[ExecutorErrorV1]
    duration_ms: int

    state_before: Optional[StateSignatureV1]
    state_after: Optional[StateSignatureV1]

    preconditions: List[ConditionEvaluation]
    postconditions: List[ConditionEvaluation]
    assertions: List[ConditionEvaluation]

    evidence_items: List[EvidenceItemV1]
    metadata: Dict[str, Any]


def _is_strong_postcondition(c: ConditionV1) -> bool:
    strong = {
        ConditionKindV1.url_is,
        ConditionKindV1.url_matches,
        ConditionKindV1.download_started,
        ConditionKindV1.upload_completed,
    }
    if c.kind in strong:
        return True
    if c.kind in {ConditionKindV1.toast_contains, ConditionKindV1.element_text_contains} and c.severity == ErrorSeverityV1.critical:
        return True
    return False


def _parse_target_from_condition_args(args: Dict[str, Any]) -> Optional[TargetV1]:
    t = args.get("target")
    if isinstance(t, TargetV1):
        return t
    if isinstance(t, dict):
        return TargetV1.model_validate(t)
    return None


def evaluate_condition(
    condition: ConditionV1,
    controller: BrowserController,
    profile: ExecutionProfileV1,
    policy: PolicyStateV1,
    timeout_ms: Optional[int] = None,
) -> ConditionEvaluation:
    """
    Evalúa una Condition.kind subset v1 de forma determinista.
    """
    page = controller.page
    to_ms = timeout_ms or profile.action_timeout_ms
    details: Dict[str, Any] = {}

    try:
        if condition.kind == ConditionKindV1.url_is:
            expected = str(condition.args.get("value") or "")
            actual = page.url if page else ""
            ok = actual == expected
            details = {"expected": expected, "actual": actual}
            return ConditionEvaluation(condition, ok, details)

        if condition.kind == ConditionKindV1.url_matches:
            pattern = str(condition.args.get("pattern") or "")
            actual = page.url if page else ""
            ok = bool(re.search(pattern, actual))
            details = {"pattern": pattern, "actual": actual}
            return ConditionEvaluation(condition, ok, details)

        if condition.kind == ConditionKindV1.host_in_allowlist:
            allowlist = condition.args.get("allowlist") or condition.args.get("domains") or []
            allow = [str(x) for x in allowlist]
            host = urlparse(page.url).hostname if page else None
            ok = bool(host) and host in allow
            details = {"host": host, "allowlist": allow}
            return ConditionEvaluation(condition, ok, details)

        if condition.kind == ConditionKindV1.title_contains:
            expected = str(condition.args.get("text") or condition.args.get("value") or "")
            actual = page.title() if page else ""
            ok = expected.lower() in (actual or "").lower()
            details = {"expected": expected, "actual": actual}
            return ConditionEvaluation(condition, ok, details)

        if condition.kind == ConditionKindV1.network_idle:
            if not page:
                return ConditionEvaluation(condition, False, {"reason": "no_page"})
            try:
                page.wait_for_load_state("networkidle", timeout=to_ms)
                return ConditionEvaluation(condition, True, {})
            except Exception as e:
                return ConditionEvaluation(condition, False, {"cause": repr(e)})

        if condition.kind == ConditionKindV1.no_blocking_overlay:
            # Default conservador (no heurísticas creativas):
            # verifica ausencia de role=dialog o aria-modal=true visibles.
            if not page:
                return ConditionEvaluation(condition, False, {"reason": "no_page"})
            script = """() => {
              const candidates = Array.from(document.querySelectorAll('[aria-modal="true"], [role="dialog"]'));
              const isVisible = (el) => {
                const style = window.getComputedStyle(el);
                if (!style) return false;
                if (style.visibility === 'hidden' || style.display === 'none') return false;
                const r = el.getClientRects();
                return r && r.length > 0;
              };
              const visible = candidates.filter(isVisible);
              return { count: visible.length, texts: visible.slice(0,3).map(x => (x.innerText||x.textContent||'').toString().trim()) };
            }"""
            res = page.evaluate(script)
            ok = int(res.get("count", 0)) == 0
            return ConditionEvaluation(condition, ok, {"overlay_count": res.get("count"), "overlay_texts": res.get("texts")})

        if condition.kind == ConditionKindV1.toast_contains:
            if not page:
                return ConditionEvaluation(condition, False, {"reason": "no_page"})
            expected = str(condition.args.get("text") or "")
            script = """() => {
              const sels = ['[role="alert"]','[role="status"]','[aria-live]'];
              const els = sels.flatMap(s => Array.from(document.querySelectorAll(s)));
              const isVisible = (el) => {
                const style = window.getComputedStyle(el);
                if (!style) return false;
                if (style.visibility === 'hidden' || style.display === 'none') return false;
                const r = el.getClientRects();
                return r && r.length > 0;
              };
              const texts = [];
              for (const el of els) {
                if (!isVisible(el)) continue;
                const t = (el.innerText || el.textContent || '').toString().replace(/\\s+/g,' ').trim();
                if (t) texts.push(t);
                if (texts.length >= 10) break;
              }
              return texts;
            }"""
            texts = page.evaluate(script) or []
            ok = any(expected.lower() in t.lower() for t in texts)
            return ConditionEvaluation(condition, ok, {"expected": expected, "observed": texts})

        # Element-based conditions
        if condition.kind in {
            ConditionKindV1.element_exists,
            ConditionKindV1.element_visible,
            ConditionKindV1.element_enabled,
            ConditionKindV1.element_clickable,
            ConditionKindV1.element_count_equals,
            ConditionKindV1.element_text_contains,
            ConditionKindV1.element_attr_equals,
            ConditionKindV1.element_value_equals,
        }:
            target = _parse_target_from_condition_args(condition.args)
            if target is None:
                return ConditionEvaluation(condition, False, {"reason": "missing target"})

            loc = controller.locate(target)

            if condition.kind == ConditionKindV1.element_count_equals:
                expected_count = int(condition.args.get("count"))
                try:
                    count = loc.count()
                except Exception as e:
                    return ConditionEvaluation(condition, False, {"cause": repr(e)})
                ok = count == expected_count
                return ConditionEvaluation(condition, ok, {"expected": expected_count, "actual": count})

            # For remaining element checks require determinism -> count==1
            try:
                one = controller.locate_unique(target, timeout_ms=to_ms)
            except ExecutorTypedException as te:
                # target not found/unique is a condition failure at this layer
                return ConditionEvaluation(condition, False, {"error_code": te.error.error_code, "details": te.error.details})

            if condition.kind == ConditionKindV1.element_exists:
                return ConditionEvaluation(condition, True, {})
            if condition.kind == ConditionKindV1.element_visible:
                try:
                    ok = one.is_visible()
                except Exception as e:
                    ok = False
                    details = {"cause": repr(e)}
                return ConditionEvaluation(condition, ok, details)
            if condition.kind == ConditionKindV1.element_enabled:
                try:
                    ok = one.is_enabled()
                except Exception as e:
                    ok = False
                    details = {"cause": repr(e)}
                return ConditionEvaluation(condition, ok, details)
            if condition.kind == ConditionKindV1.element_clickable:
                try:
                    ok = bool(one.is_visible() and one.is_enabled())
                except Exception as e:
                    ok = False
                    details = {"cause": repr(e)}
                return ConditionEvaluation(condition, ok, details)
            if condition.kind == ConditionKindV1.element_text_contains:
                expected = str(condition.args.get("text") or "")
                try:
                    text = one.inner_text(timeout=to_ms)
                except Exception:
                    try:
                        text = one.text_content(timeout=to_ms) or ""
                    except Exception as e:
                        return ConditionEvaluation(condition, False, {"cause": repr(e)})
                ok = expected.lower() in (text or "").lower()
                return ConditionEvaluation(condition, ok, {"expected": expected, "actual": text})
            if condition.kind == ConditionKindV1.element_attr_equals:
                attr = str(condition.args.get("attr") or "")
                expected = str(condition.args.get("value") or "")
                try:
                    actual = one.get_attribute(attr)
                except Exception as e:
                    return ConditionEvaluation(condition, False, {"cause": repr(e)})
                ok = (actual or "") == expected
                return ConditionEvaluation(condition, ok, {"attr": attr, "expected": expected, "actual": actual})
            if condition.kind == ConditionKindV1.element_value_equals:
                expected = str(condition.args.get("value") or "")
                try:
                    actual = one.input_value(timeout=to_ms)
                except Exception as e:
                    return ConditionEvaluation(condition, False, {"cause": repr(e)})
                ok = (actual or "") == expected
                return ConditionEvaluation(condition, ok, {"expected": expected, "actual": actual})

        if condition.kind == ConditionKindV1.download_started:
            ok = bool(policy.download_started)
            return ConditionEvaluation(condition, ok, {"download_started": policy.download_started, "url": policy.last_download_url})

        if condition.kind == ConditionKindV1.upload_completed:
            # v1: si no hay señal explícita -> se espera que venga como DOM/toast change (ej. toast_contains).
            # Default conservador: si args trae target+attr/value, evaluamos; si no, false.
            target = _parse_target_from_condition_args(condition.args)
            if target is None:
                return ConditionEvaluation(condition, False, {"reason": "no explicit upload signal; use toast/dom change"})
            # Permitir comprobar value del input file (si el browser expone algo)
            try:
                one = controller.locate_unique(target, timeout_ms=to_ms)
                val = one.get_attribute("value") or ""
                expected = str(condition.args.get("contains") or condition.args.get("value") or "")
                ok = expected in val if expected else bool(val)
                return ConditionEvaluation(condition, ok, {"expected_contains": expected, "actual_value": val})
            except ExecutorTypedException as te:
                return ConditionEvaluation(condition, False, {"error_code": te.error.error_code})

        return ConditionEvaluation(condition, False, {"reason": "unsupported condition kind"})

    except Exception as e:
        return ConditionEvaluation(condition, False, {"cause": repr(e)})


def evaluate_conditions(
    conditions: List[ConditionV1],
    controller: BrowserController,
    profile: ExecutionProfileV1,
    policy: PolicyStateV1,
    timeout_ms: Optional[int] = None,
) -> List[ConditionEvaluation]:
    return [evaluate_condition(c, controller, profile, policy, timeout_ms=timeout_ms) for c in conditions]


def validate_runtime(action: ActionSpecV1, controller: BrowserController, profile: ExecutionProfileV1) -> None:
    """
    Enforcement runtime (además de schema).
    - U1: click/upload requiere count==1 (se aplicará vía locate_unique en ejecución).
    - U5: critical requiere postcondición fuerte.
    """
    if action.criticality == "critical":
        if not any(_is_strong_postcondition(c) for c in action.postconditions):
            raise ExecutorTypedException(
                ExecutorErrorV1(
                    error_code="INVALID_ACTIONSPEC",
                    stage=ErrorStageV1.proposal_validation,
                    severity=ErrorSeverityV1.error,
                    message="critical action missing strong postcondition (U5)",
                    retryable=False,
                    details={"action_id": action.action_id},
                )
            )


def compile_action(
    action: ActionSpecV1,
    controller: BrowserController,
    profile: ExecutionProfileV1,
    policy: PolicyStateV1,
    *,
    evidence_dir,
) -> ActionExecutionResult:
    """
    Ejecuta ActionSpecV1 contra Playwright (via BrowserController) con:
    - validate_runtime
    - preconditions_checked
    - action execution
    - postconditions_checked
    - asserts (si aplica)

    Nota: el runtime externo emite eventos trace; aquí solo devolvemos resultado.
    """
    t0 = time.perf_counter()
    evidence_items: List[EvidenceItemV1] = []
    pre_evals: List[ConditionEvaluation] = []
    post_evals: List[ConditionEvaluation] = []
    assert_evals: List[ConditionEvaluation] = []

    try:
        validate_runtime(action, controller, profile)
    except ExecutorTypedException as te:
        return ActionExecutionResult(
            status=ActionStatusV1.failed,
            error=te.error,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            state_before=None,
            state_after=None,
            preconditions=[],
            postconditions=[],
            assertions=[],
            evidence_items=[],
            metadata={"phase": "validate_runtime"},
        )

    # Capture before
    dom_before, state_before, items_before = controller.capture_observation(step_id="step_000", evidence_dir=evidence_dir)
    evidence_items.extend(items_before)

    # Preconditions
    pre_evals = evaluate_conditions(action.preconditions, controller, profile, policy, timeout_ms=action.timeout_ms)
    if any(not ev.ok and ev.condition.severity in (ErrorSeverityV1.error, ErrorSeverityV1.critical) for ev in pre_evals):
        err = ExecutorErrorV1(
            error_code="PRECONDITION_FAILED",
            stage=ErrorStageV1.precondition,
            severity=ErrorSeverityV1.error,
            message="precondition failed",
            retryable=False,
            details={"failed_conditions": [ev.condition.model_dump() for ev in pre_evals if not ev.ok]},
        )
        return ActionExecutionResult(
            status=ActionStatusV1.failed,
            error=err,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            state_before=state_before,
            state_after=None,
            preconditions=pre_evals,
            postconditions=[],
            assertions=[],
            evidence_items=evidence_items,
            metadata={"phase": "preconditions"},
        )

    # Execute action
    try:
        if action.kind == ActionKindV1.navigate:
            controller.navigate(str(action.target.url), timeout_ms=action.timeout_ms)

        elif action.kind == ActionKindV1.click:
            # U1 enforcement via locate_unique
            loc = controller.locate_unique(action.target, timeout_ms=action.timeout_ms)
            loc.click(timeout=action.timeout_ms or profile.action_timeout_ms)

        elif action.kind == ActionKindV1.fill:
            loc = controller.locate_unique(action.target, timeout_ms=action.timeout_ms)
            text = action.input.get("text") or action.input.get("value")
            if text is None:
                raise ExecutorTypedException(
                    ExecutorErrorV1(
                        error_code="INVALID_ACTIONSPEC",
                        stage=ErrorStageV1.proposal_validation,
                        severity=ErrorSeverityV1.error,
                        message="fill requires input.text|input.value",
                        retryable=False,
                    )
                )
            loc.click(timeout=action.timeout_ms or profile.action_timeout_ms)
            loc.fill(str(text), timeout=action.timeout_ms or profile.action_timeout_ms)

        elif action.kind == ActionKindV1.wait_for:
            # Wait until all postconditions are true (or until timeout). Determinista.
            deadline = time.perf_counter() + ((action.timeout_ms or profile.action_timeout_ms) / 1000.0)
            ok = False
            last = []
            while time.perf_counter() < deadline:
                last = evaluate_conditions(action.postconditions, controller, profile, policy, timeout_ms=action.timeout_ms)
                if all(ev.ok for ev in last):
                    ok = True
                    post_evals = last
                    break
                time.sleep(0.05)
            if not ok:
                post_evals = last or evaluate_conditions(action.postconditions, controller, profile, policy, timeout_ms=action.timeout_ms)
                raise ExecutorTypedException(
                    ExecutorErrorV1(
                        error_code="POSTCONDITION_FAILED",
                        stage=ErrorStageV1.postcondition,
                        severity=ErrorSeverityV1.error,
                        message="wait_for timeout: postconditions not satisfied",
                        retryable=False,
                        details={"failed_conditions": [ev.condition.model_dump() for ev in post_evals if not ev.ok]},
                    )
                )

        elif action.kind == ActionKindV1.assert_:
            # assert_checked: evaluar assertions (o postconditions si assertions vacío)
            to_check = action.assertions or action.postconditions
            assert_evals = evaluate_conditions(to_check, controller, profile, policy, timeout_ms=action.timeout_ms)
            if any(not ev.ok and ev.condition.severity in (ErrorSeverityV1.error, ErrorSeverityV1.critical) for ev in assert_evals):
                raise ExecutorTypedException(
                    ExecutorErrorV1(
                        error_code="POSTCONDITION_FAILED",
                        stage=ErrorStageV1.postcondition,
                        severity=ErrorSeverityV1.error,
                        message="assert failed",
                        retryable=False,
                        details={"failed_conditions": [ev.condition.model_dump() for ev in assert_evals if not ev.ok]},
                    )
                )

        elif action.kind == ActionKindV1.upload:
            # Direct input[type=file] only
            loc = controller.locate_unique(action.target, timeout_ms=action.timeout_ms)
            try:
                typ = loc.get_attribute("type")
            except Exception:
                typ = None
            if (typ or "").lower() != "file":
                raise ExecutorTypedException(
                    ExecutorErrorV1(
                        error_code="INVALID_ACTIONSPEC",
                        stage=ErrorStageV1.proposal_validation,
                        severity=ErrorSeverityV1.error,
                        message="upload supports only input[type=file] direct targets in H3",
                        retryable=False,
                        details={"type": typ},
                    )
                )
            file_path = action.input.get("file_path")
            if not file_path:
                raise ExecutorTypedException(
                    ExecutorErrorV1(
                        error_code="INVALID_ACTIONSPEC",
                        stage=ErrorStageV1.proposal_validation,
                        severity=ErrorSeverityV1.error,
                        message="upload requires input.file_path in H3",
                        retryable=False,
                    )
                )
            try:
                # Playwright: set_input_files
                loc.set_input_files(str(file_path), timeout=action.timeout_ms or profile.action_timeout_ms)
            except Exception as e:
                raise ExecutorTypedException(
                    ExecutorErrorV1(
                        error_code="UPLOAD_FAILED",
                        stage=ErrorStageV1.execution,
                        severity=ErrorSeverityV1.error,
                        message="upload failed",
                        retryable=False,
                        cause=repr(e),
                        details={"file_path": str(file_path)},
                    )
                )

        else:
            raise ExecutorTypedException(
                ExecutorErrorV1(
                    error_code="PROPOSAL_UNSUPPORTED_ACTION",
                    stage=ErrorStageV1.proposal_validation,
                    severity=ErrorSeverityV1.error,
                    message=f"unsupported action kind in H3: {action.kind}",
                    retryable=False,
                )
            )

    except ExecutorTypedException as te:
        # Capture after (best effort)
        try:
            _, state_after, items_after = controller.capture_observation(step_id="step_000", evidence_dir=evidence_dir)
            evidence_items.extend(items_after)
        except Exception:
            state_after = None
        return ActionExecutionResult(
            status=ActionStatusV1.failed,
            error=te.error,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            state_before=state_before,
            state_after=state_after,
            preconditions=pre_evals,
            postconditions=post_evals,
            assertions=assert_evals,
            evidence_items=evidence_items,
            metadata={"phase": "execution"},
        )

    # Postconditions (if not already computed by wait_for/assert)
    if not post_evals and action.kind not in (ActionKindV1.assert_, ActionKindV1.wait_for):
        post_evals = evaluate_conditions(action.postconditions, controller, profile, policy, timeout_ms=action.timeout_ms)
        if any(not ev.ok and ev.condition.severity in (ErrorSeverityV1.error, ErrorSeverityV1.critical) for ev in post_evals):
            err = ExecutorErrorV1(
                error_code="POSTCONDITION_FAILED",
                stage=ErrorStageV1.postcondition,
                severity=ErrorSeverityV1.error,
                message="postcondition failed",
                retryable=False,
                details={"failed_conditions": [ev.condition.model_dump() for ev in post_evals if not ev.ok]},
            )
            return ActionExecutionResult(
                status=ActionStatusV1.failed,
                error=err,
                duration_ms=int((time.perf_counter() - t0) * 1000),
                state_before=state_before,
                state_after=None,
                preconditions=pre_evals,
                postconditions=post_evals,
                assertions=assert_evals,
                evidence_items=evidence_items,
                metadata={"phase": "postconditions"},
            )

    # Capture after
    _, state_after, items_after = controller.capture_observation(step_id="step_000", evidence_dir=evidence_dir)
    evidence_items.extend(items_after)

    return ActionExecutionResult(
        status=ActionStatusV1.success,
        error=None,
        duration_ms=int((time.perf_counter() - t0) * 1000),
        state_before=state_before,
        state_after=state_after,
        preconditions=pre_evals,
        postconditions=post_evals,
        assertions=assert_evals,
        evidence_items=evidence_items,
        metadata={},
    )


