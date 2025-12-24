import json
from pathlib import Path

import pytest


def test_fail_fast_last_postcondition_fails_is_failed_not_halted(monkeypatch, tmp_path: Path):
    """
    Offline (sin Playwright):
    - Forzamos que el último step tenga postconditions que fallan (logout no visible)
    - Con fail_fast=True debe terminar status=failed (no halted) y error_code=AUTH_FAILED.
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
            # devolver evidencia mínima para no romper manifest
            item = EvidenceItemV1(
                kind=EvidenceKindV1.dom_snapshot_partial,
                step_id=step_id,
                relative_path=f"evidence/dom/{step_id}.json",
                sha256="0" * 64,
                size_bytes=0,
            )
            return ({}, sig, [item])

        def capture_html_full(self, *args, **kwargs):
            raise RuntimeError("not needed in offline test")

        def capture_screenshot_file(self, *args, **kwargs):
            raise RuntimeError("not needed in offline test")

    monkeypatch.setattr(rtmod, "BrowserController", DummyCtrl, raising=True)

    # evaluate_conditions: ok para todo salvo element_visible sobre selector logout (último step)
    def fake_eval(conditions, controller, profile, policy, timeout_ms=None):
        out = []
        for c in conditions:
            if c.kind == ConditionKindV1.element_visible:
                tgt = (c.args or {}).get("target") or {}
                sel = (tgt.get("selector") or "") if isinstance(tgt, dict) else ""
                if "Logout" in sel or "Desconectar" in sel or "logout" in sel.lower():
                    out.append(ConditionEvaluation(c, False, {"actual": "not visible"}))
                    continue
            out.append(ConditionEvaluation(c, True, {}))
        return out

    monkeypatch.setattr(rtmod, "evaluate_conditions", fake_eval, raising=True)

    # execute_action_only: no-op success
    def fake_exec(action, controller, profile, policy, **kwargs):
        return {"ok": True, "metadata": {}}

    monkeypatch.setattr(rtmod, "execute_action_only", fake_exec, raising=True)

    # validate_runtime: no-op
    monkeypatch.setattr(rtmod, "validate_runtime", lambda *a, **k: None, raising=True)

    runtime = rtmod.ExecutorRuntimeH4(runs_root=tmp_path / "runs", project_root=".", data_root="data")

    logout_target = TargetV1(type=TargetKindV1.css, selector='a[href*="Logout"], a:has-text("Desconectar")')
    actions = [
        ActionSpecV1(
            action_id="ok1",
            kind=ActionKindV1.wait_for,
            target=TargetV1(type=TargetKindV1.css, selector="body"),
            input={},
                preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": {"type": "css", "selector": "body"}}, severity=ErrorSeverityV1.warning)],
            timeout_ms=10,
        ),
        ActionSpecV1(
            action_id="eg_wait_post_login_real",
            kind=ActionKindV1.wait_for,
            target=logout_target,
            input={},
                preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
                postconditions=[
                    ConditionV1(kind=ConditionKindV1.element_visible, args={"target": logout_target.model_dump()}, severity=ErrorSeverityV1.critical),
                    # U5 strong postcondition
                    ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": r"^(?!.*login).*$"}, severity=ErrorSeverityV1.critical),
                ],
            timeout_ms=10,
            criticality="critical",
        ),
    ]

    run_dir = runtime.run_actions(url="https://example.invalid", actions=actions, headless=True, fail_fast=True)
    trace_path = Path(run_dir) / "trace.jsonl"
    lines = [json.loads(x) for x in trace_path.read_text(encoding="utf-8").splitlines() if x.strip()]

    # status final: failed (no halted)
    finished = [ev for ev in lines if ev.get("event_type") == TraceEventTypeV1.run_finished.value]
    assert finished, "missing run_finished"
    assert finished[-1]["metadata"]["status"] == "failed"

    # error_raised: AUTH_FAILED (por selector logout)
    errors = [ev for ev in lines if ev.get("event_type") == TraceEventTypeV1.error_raised.value]
    assert errors, "missing error_raised"
    assert errors[-1]["error"]["error_code"] == "AUTH_FAILED"


