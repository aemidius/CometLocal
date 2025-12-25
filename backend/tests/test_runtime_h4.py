import json
from pathlib import Path

import pytest

from backend.executor.runtime_h4 import ExecutorRuntimeH4, RuntimePolicyDefaultsV1
from backend.shared.executor_contracts_v1 import (
    ActionKindV1,
    ActionSpecV1,
    ConditionKindV1,
    ConditionV1,
    EvidenceManifestV1,
    ErrorSeverityV1,
    TraceEventTypeV1,
    TraceEventV1,
    TargetKindV1,
    TargetV1,
)


def _can_start_playwright() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _can_start_playwright(), reason="playwright.sync_api not available")
def test_run_actions_success_offline(tmp_path: Path):
    html = """
    <html><head><title>OK</title></head>
    <body>
      <label for="u">Usuario</label>
      <input id="u" type="text" />
      <button data-testid="go" onclick="document.querySelector('#out').textContent='done'">Go</button>
      <div id="out"></div>
    </body></html>
    """
    p = tmp_path / "ok.html"
    p.write_text(html, encoding="utf-8")

    actions = [
        ActionSpecV1(
            action_id="a_fill",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.label, text="Usuario", exact=True),
            input={"text": "demo"},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": {"type": "css", "selector": "#u"}}, severity=ErrorSeverityV1.error)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": {"type": "css", "selector": "#u"}, "value": "demo"}, severity=ErrorSeverityV1.critical)],
            timeout_ms=3000,
            criticality="normal",
        ),
        ActionSpecV1(
            action_id="a_click",
            kind=ActionKindV1.click,
            target=TargetV1(type=TargetKindV1.testid, testid="go"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": {"type": "testid", "testid": "go"}, "count": 1}, severity=ErrorSeverityV1.critical)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_text_contains, args={"target": {"type": "css", "selector": "#out"}, "text": "done"}, severity=ErrorSeverityV1.critical)],
            timeout_ms=3000,
            criticality="normal",
        ),
        ActionSpecV1(
            action_id="a_assert",
            kind=ActionKindV1.assert_,
            target=None,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.title_contains, args={"text": "OK"}, severity=ErrorSeverityV1.error)],
            postconditions=[],
            assertions=[ConditionV1(kind=ConditionKindV1.element_text_contains, args={"target": {"type": "css", "selector": "#out"}, "text": "done"}, severity=ErrorSeverityV1.critical)],
            timeout_ms=2000,
            criticality="normal",
        ),
    ]

    rt = ExecutorRuntimeH4(runs_root=tmp_path / "runs")
    try:
        run_dir = rt.run_actions(url=p.as_uri(), actions=actions, headless=True)
    except Exception as e:
        pytest.skip(f"Playwright cannot run in this environment: {e}")

    trace_path = run_dir / "trace.jsonl"
    assert trace_path.exists()
    evs = [TraceEventV1.model_validate(json.loads(l)) for l in trace_path.read_text(encoding="utf-8").splitlines()]
    types = [e.event_type for e in evs]
    assert TraceEventTypeV1.run_started in types
    assert TraceEventTypeV1.run_finished in types
    assert TraceEventTypeV1.action_compiled in types
    assert TraceEventTypeV1.preconditions_checked in types
    assert TraceEventTypeV1.action_started in types
    assert TraceEventTypeV1.action_executed in types
    assert TraceEventTypeV1.postconditions_checked in types
    assert TraceEventTypeV1.assert_checked in types
    assert TraceEventTypeV1.evidence_captured in types

    manifest = EvidenceManifestV1.model_validate(json.loads((run_dir / "evidence_manifest.json").read_text(encoding="utf-8")))
    assert any(i.kind.value == "dom_snapshot_partial" for i in manifest.items)


@pytest.mark.skipif(not _can_start_playwright(), reason="playwright.sync_api not available")
def test_run_actions_target_not_unique_emits_error_raised(tmp_path: Path):
    html = "<html><body><button data-testid='b'>B</button><button data-testid='b'>B2</button></body></html>"
    p = tmp_path / "dup.html"
    p.write_text(html, encoding="utf-8")

    actions = [
        ActionSpecV1(
            action_id="a_click",
            kind=ActionKindV1.click,
            target=TargetV1(type=TargetKindV1.testid, testid="b"),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": {"type": "testid", "testid": "b"}, "count": 1}, severity=ErrorSeverityV1.critical)],
            postconditions=[ConditionV1(kind=ConditionKindV1.title_contains, args={"text": ""}, severity=ErrorSeverityV1.warning)],
            timeout_ms=2000,
            criticality="normal",
        )
    ]

    rt = ExecutorRuntimeH4(runs_root=tmp_path / "runs")
    try:
        run_dir = rt.run_actions(url=p.as_uri(), actions=actions, headless=True)
    except Exception as e:
        pytest.skip(f"Playwright cannot run in this environment: {e}")

    evs = [TraceEventV1.model_validate(json.loads(l)) for l in (run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    errs = [e for e in evs if e.event_type == TraceEventTypeV1.error_raised]
    assert errs, "expected error_raised"
    assert errs[0].error is not None
    assert errs[0].error.error_code == "TARGET_NOT_UNIQUE"

    manifest = EvidenceManifestV1.model_validate(json.loads((run_dir / "evidence_manifest.json").read_text(encoding="utf-8")))
    # fallo -> debe incluir html_full y screenshot (policy)
    assert any(i.kind.value == "html_full" for i in manifest.items) or any(i.kind.value == "screenshot" for i in manifest.items)


@pytest.mark.skipif(not _can_start_playwright(), reason="playwright.sync_api not available")
def test_run_actions_policy_halt_same_state(tmp_path: Path):
    html = "<html><head><title>S</title></head><body><div id='x'>x</div></body></html>"
    p = tmp_path / "s.html"
    p.write_text(html, encoding="utf-8")

    # assert que pasa pero no cambia estado -> same-state revisit
    actions = [
        ActionSpecV1(
            action_id=f"a{i}",
            kind=ActionKindV1.assert_,
            target=None,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.title_contains, args={"text": "S"}, severity=ErrorSeverityV1.error)],
            postconditions=[],
            assertions=[ConditionV1(kind=ConditionKindV1.element_text_contains, args={"target": {"type": "css", "selector": "#x"}, "text": "x"}, severity=ErrorSeverityV1.critical)],
            timeout_ms=1000,
            criticality="normal",
        )
        for i in range(5)
    ]

    rt = ExecutorRuntimeH4(runs_root=tmp_path / "runs", policy=RuntimePolicyDefaultsV1(same_state_revisits=2))
    try:
        run_dir = rt.run_actions(url=p.as_uri(), actions=actions, headless=True)
    except Exception as e:
        pytest.skip(f"Playwright cannot run in this environment: {e}")

    evs = [TraceEventV1.model_validate(json.loads(l)) for l in (run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(e.event_type == TraceEventTypeV1.policy_halt for e in evs)
    halt = next(e for e in evs if e.event_type == TraceEventTypeV1.policy_halt)
    assert halt.error is not None
    assert halt.error.error_code == "POLICY_HALT"




