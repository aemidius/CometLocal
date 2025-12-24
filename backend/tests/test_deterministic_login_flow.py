"""
H8.C — Test deterministic login flow (no policy engine, no POLICY_HALT)
"""
import json
from pathlib import Path

import pytest

# No requiere fastapi, solo runtime


def test_deterministic_mode_never_halts(monkeypatch, tmp_path: Path):
    """
    Offline (sin Playwright):
    - Flow determinista con execution_mode="deterministic"
    - Verificar que status nunca es "halted", solo "success" o "failed"
    """
    from backend.executor import runtime_h4 as rtmod
    from backend.executor.action_compiler_v1 import ConditionEvaluation
    from backend.shared.executor_contracts_v1 import (
        ActionKindV1,
        ActionSpecV1,
        ConditionKindV1,
        ConditionV1,
        ErrorSeverityV1,
        EvidenceItemV1,
        EvidenceKindV1,
        StateSignatureV1,
        TargetKindV1,
        TargetV1,
        TraceEventTypeV1,
    )

    class DummyCtrl:
        def __init__(self, *args, **kwargs):
            self.page = None

        def start(self, headless: bool = True):
            return None

        def navigate(self, url: str, timeout_ms: int = 0):
            return None

        def close(self):
            return None

        def capture_observation(self, step_id: str, evidence_dir, phase: str = "before", redactor=None):
            sig = StateSignatureV1(
                url_hash="u" * 64,
                title_hash="h" * 64,
                key_elements_hash="k" * 64,
                visible_text_hash="t" * 64,
                screenshot_hash="s" * 64,
            )
            item = EvidenceItemV1(
                kind=EvidenceKindV1.dom_snapshot_partial,
                step_id=step_id,
                relative_path=f"evidence/dom/{step_id}.json",
                sha256="0" * 64,
                size_bytes=0,
            )
            return ({}, sig, [item])

        def capture_html_full(self, *args, **kwargs):
            raise RuntimeError("not needed")

        def capture_screenshot_file(self, *args, **kwargs):
            raise RuntimeError("not needed")

    monkeypatch.setattr(rtmod, "BrowserController", DummyCtrl, raising=True)

    # evaluate_conditions: todo ok
    def fake_eval(conditions, controller, profile, policy, timeout_ms=None):
        return [ConditionEvaluation(c, True, {}) for c in conditions]

    monkeypatch.setattr(rtmod, "evaluate_conditions", fake_eval, raising=True)

    # execute_action_only: success
    def fake_exec(action, controller, profile, policy, **kwargs):
        return {"ok": True, "metadata": {}}

    monkeypatch.setattr(rtmod, "execute_action_only", fake_exec, raising=True)
    monkeypatch.setattr(rtmod, "validate_runtime", lambda *a, **k: None, raising=True)

    runtime = rtmod.ExecutorRuntimeH4(runs_root=tmp_path / "runs", project_root=".", data_root="data")

    actions = [
        ActionSpecV1(
            action_id="nav",
            kind=ActionKindV1.navigate,
            target=TargetV1(type=TargetKindV1.url, url="https://example.invalid"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.critical)],
            timeout_ms=10,
        ),
        ActionSpecV1(
            action_id="wait",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.css, selector="body"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": {"type": "css", "selector": "body"}}, severity=ErrorSeverityV1.critical)],
            timeout_ms=10,
        ),
    ]

    run_dir = runtime.run_actions(url="https://example.invalid", actions=actions, headless=True, execution_mode="deterministic")
    trace_path = Path(run_dir) / "trace.jsonl"
    lines = [json.loads(x) for x in trace_path.read_text(encoding="utf-8").splitlines() if x.strip()]

    # Verificar que nunca se emite POLICY_HALT
    policy_halts = [ev for ev in lines if ev.get("event_type") == TraceEventTypeV1.policy_halt.value]
    assert len(policy_halts) == 0, f"deterministic mode should never emit POLICY_HALT, got: {policy_halts}"

    # Verificar status final: success o failed, nunca halted
    finished = [ev for ev in lines if ev.get("event_type") == TraceEventTypeV1.run_finished.value]
    assert finished, "missing run_finished"
    status = finished[-1]["metadata"]["status"]
    assert status in {"success", "failed"}, f"deterministic mode should only return success or failed, got: {status}"
    assert status != "halted", "deterministic mode should never return halted"

    # Verificar metadata en run_started
    started = [ev for ev in lines if ev.get("event_type") == TraceEventTypeV1.run_started.value]
    assert started, "missing run_started"
    assert started[0]["metadata"].get("runtime_execution_mode") == "deterministic"


def test_deterministic_mode_fails_on_error(monkeypatch, tmp_path: Path):
    """
    Offline: deterministic mode debe fallar inmediatamente en el primer error.
    """
    from backend.executor import runtime_h4 as rtmod
    from backend.executor.action_compiler_v1 import ConditionEvaluation
    from backend.shared.executor_contracts_v1 import (
        ActionKindV1,
        ActionSpecV1,
        ConditionKindV1,
        ConditionV1,
        ErrorSeverityV1,
        EvidenceItemV1,
        EvidenceKindV1,
        StateSignatureV1,
        TargetKindV1,
        TargetV1,
        TraceEventTypeV1,
    )

    class DummyCtrl:
        def __init__(self, *args, **kwargs):
            self.page = None

        def start(self, headless: bool = True):
            return None

        def navigate(self, url: str, timeout_ms: int = 0):
            return None

        def close(self):
            return None

        def capture_observation(self, step_id: str, evidence_dir, phase: str = "before", redactor=None):
            sig = StateSignatureV1(
                url_hash="u" * 64,
                title_hash="h" * 64,
                key_elements_hash="k" * 64,
                visible_text_hash="t" * 64,
                screenshot_hash="s" * 64,
            )
            item = EvidenceItemV1(
                kind=EvidenceKindV1.dom_snapshot_partial,
                step_id=step_id,
                relative_path=f"evidence/dom/{step_id}.json",
                sha256="0" * 64,
                size_bytes=0,
            )
            return ({}, sig, [item])

        def capture_html_full(self, *args, **kwargs):
            raise RuntimeError("not needed")

        def capture_screenshot_file(self, *args, **kwargs):
            raise RuntimeError("not needed")

    monkeypatch.setattr(rtmod, "BrowserController", DummyCtrl, raising=True)

    # evaluate_conditions: segundo step falla
    call_count = [0]

    def fake_eval(conditions, controller, profile, policy, timeout_ms=None):
        call_count[0] += 1
        if call_count[0] >= 3:  # después de nav + wait preconditions, el wait postcondition falla
            return [ConditionEvaluation(c, False, {"reason": "test failure"}) for c in conditions]
        return [ConditionEvaluation(c, True, {}) for c in conditions]

    monkeypatch.setattr(rtmod, "evaluate_conditions", fake_eval, raising=True)
    monkeypatch.setattr(rtmod, "execute_action_only", lambda *a, **k: {"ok": True, "metadata": {}}, raising=True)
    monkeypatch.setattr(rtmod, "validate_runtime", lambda *a, **k: None, raising=True)

    runtime = rtmod.ExecutorRuntimeH4(runs_root=tmp_path / "runs", project_root=".", data_root="data")

    actions = [
        ActionSpecV1(
            action_id="nav",
            kind=ActionKindV1.navigate,
            target=TargetV1(type=TargetKindV1.url, url="https://example.invalid"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.network_idle, args={}, severity=ErrorSeverityV1.critical)],
            timeout_ms=10,
        ),
        ActionSpecV1(
            action_id="wait_fail",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.css, selector="body"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": {"type": "css", "selector": "body"}}, severity=ErrorSeverityV1.critical)],
            timeout_ms=10,
        ),
    ]

    run_dir = runtime.run_actions(url="https://example.invalid", actions=actions, headless=True, execution_mode="deterministic")
    trace_path = Path(run_dir) / "trace.jsonl"
    lines = [json.loads(x) for x in trace_path.read_text(encoding="utf-8").splitlines() if x.strip()]

    finished = [ev for ev in lines if ev.get("event_type") == TraceEventTypeV1.run_finished.value]
    assert finished, "missing run_finished"
    status = finished[-1]["metadata"]["status"]
    assert status == "failed", f"deterministic mode should fail on error, got: {status}"
    assert status != "halted", "deterministic mode should never return halted"

