"""
H8.E2 — Test runtime marks success when no error (default success)
"""
import json
from pathlib import Path

import pytest

# No requiere fastapi, solo runtime


def test_runtime_h4_marks_success_when_no_error(monkeypatch, tmp_path: Path):
    """
    Offline (sin Playwright):
    - Flow determinista completa todas las acciones sin errores
    - Verificar que el run_finished.json contiene status == "success"
    - Verificar que final_status es "success" por defecto
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
            def h(seed: str) -> str:
                s = (seed * 80)[:64]
                return s.replace(" ", "_")

            sig = StateSignatureV1(
                url_hash=h(f"url:{step_id}:{phase}:"),
                title_hash=h(f"title:{step_id}:{phase}:"),
                key_elements_hash=h(f"keys:{step_id}:{phase}:"),
                visible_text_hash=h(f"text:{step_id}:{phase}:"),
                screenshot_hash=h(f"shot:{step_id}:{phase}:"),
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
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": {"type": "css", "selector": "body"}}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": r"^(?!.*login).*$"}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=10,
            criticality="critical",
        ),
    ]

    run_dir = runtime.run_actions(url="https://example.invalid", actions=actions, headless=True, execution_mode="deterministic")
    trace_path = Path(run_dir) / "trace.jsonl"
    lines = [json.loads(x) for x in trace_path.read_text(encoding="utf-8").splitlines() if x.strip()]

    # Verificar que NO hay error_raised
    errors = [ev for ev in lines if ev.get("event_type") == TraceEventTypeV1.error_raised.value]
    assert len(errors) == 0, f"flow should complete without errors, got: {errors}"

    # Verificar status final: success (no failed)
    finished = [ev for ev in lines if ev.get("event_type") == TraceEventTypeV1.run_finished.value]
    assert finished, "missing run_finished"
    finished_event = finished[-1]
    status = finished_event["metadata"]["status"]
    
    # H8.E2: Assert que status es "success" (default cuando no hay errores)
    assert status == "success", f"flow should mark success when no errors, got: {status}"
    assert status != "failed", "flow should not mark failed when no errors"
    
    # H8.E2: Verificar que no hay error/error_code en metadata cuando es success
    assert "error" not in finished_event["metadata"] or finished_event["metadata"].get("error") is None, "success should not have error in metadata"
    assert "error_code" not in finished_event["metadata"] or finished_event["metadata"].get("error_code") is None, "success should not have error_code in metadata"

