import json
from pathlib import Path

import pytest

from backend.executor.action_compiler_v1 import PolicyStateV1, compile_action
from backend.executor.browser_controller import BrowserController, ExecutionProfileV1
from backend.shared.executor_contracts_v1 import (
    ActionKindV1,
    ActionSpecV1,
    ActionStatusV1,
    ConditionKindV1,
    ConditionV1,
    ErrorSeverityV1,
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
def test_compile_fill_and_assert_offline_file(tmp_path: Path):
    html = """
    <html>
      <head><title>H3</title></head>
      <body>
        <label for="u">Usuario</label>
        <input id="u" name="username" type="text" />
        <div id="msg"></div>
        <script>
          document.querySelector('#u').addEventListener('input', () => {
            document.querySelector('#msg').textContent = 'ok';
          });
        </script>
      </body>
    </html>
    """
    file_path = tmp_path / "h3.html"
    file_path.write_text(html, encoding="utf-8")

    runs_dir = tmp_path / "runs"
    evidence_dir = runs_dir / "r1" / "evidence"

    ctrl = BrowserController(profile=ExecutionProfileV1(action_timeout_ms=3000, navigation_timeout_ms=5000))
    try:
        try:
            ctrl.start(headless=True)
        except Exception as e:
            pytest.skip(f"Playwright cannot start: {e}")

        # navigate
        nav = ActionSpecV1(
            action_id="a_nav",
            kind=ActionKindV1.navigate,
            target=TargetV1(type=TargetKindV1.url, url=file_path.as_uri()),
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.host_in_allowlist, args={"allowlist": [""]}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.title_contains, args={"text": "H3"}, severity=ErrorSeverityV1.critical)],
            timeout_ms=5000,
            criticality="normal",
        )
        res_nav = compile_action(nav, ctrl, ctrl.profile, PolicyStateV1(), evidence_dir=evidence_dir)
        assert res_nav.status == ActionStatusV1.success

        # fill (label target) + post condition value equals
        fill = ActionSpecV1(
            action_id="a_fill",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.label, text="Usuario", exact=True),
            input={"text": "demo"},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": {"type": "css", "selector": "#u"}}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": {"type": "css", "selector": "#u"}, "value": "demo"}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=3000,
            criticality="normal",
        )
        res_fill = compile_action(fill, ctrl, ctrl.profile, PolicyStateV1(), evidence_dir=evidence_dir)
        assert res_fill.status == ActionStatusV1.success

        # assert: msg contains ok
        ass = ActionSpecV1(
            action_id="a_assert",
            kind=ActionKindV1.assert_,
            target=None,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.title_contains, args={"text": "H3"}, severity=ErrorSeverityV1.error)],
            postconditions=[],
            assertions=[ConditionV1(kind=ConditionKindV1.element_text_contains, args={"target": {"type": "css", "selector": "#msg"}, "text": "ok"}, severity=ErrorSeverityV1.critical)],
            timeout_ms=2000,
            criticality="normal",
        )
        res_ass = compile_action(ass, ctrl, ctrl.profile, PolicyStateV1(), evidence_dir=evidence_dir)
        assert res_ass.status == ActionStatusV1.success

    finally:
        ctrl.close()


@pytest.mark.skipif(not _can_start_playwright(), reason="playwright.sync_api not available")
def test_click_requires_count_equals_1_u1(tmp_path: Path):
    html = "<html><body><button data-testid='b'>B</button><button data-testid='b'>B2</button></body></html>"
    file_path = tmp_path / "dup.html"
    file_path.write_text(html, encoding="utf-8")

    ctrl = BrowserController(profile=ExecutionProfileV1(action_timeout_ms=3000, navigation_timeout_ms=5000))
    try:
        try:
            ctrl.start(headless=True)
        except Exception as e:
            pytest.skip(f"Playwright cannot start: {e}")

        ctrl.navigate(file_path.as_uri(), timeout_ms=5000)

        click = ActionSpecV1(
            action_id="a_click",
            kind=ActionKindV1.click,
            target=TargetV1(type=TargetKindV1.testid, testid="b"),
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": {"type": "testid", "testid": "b"}, "count": 1}, severity=ErrorSeverityV1.critical),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.title_contains, args={"text": ""}, severity=ErrorSeverityV1.warning)],
            timeout_ms=2000,
            criticality="normal",
        )
        res = compile_action(click, ctrl, ctrl.profile, PolicyStateV1(), evidence_dir=tmp_path / "ev")
        assert res.status == ActionStatusV1.failed

    finally:
        ctrl.close()









