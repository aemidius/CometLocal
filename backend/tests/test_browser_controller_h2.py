import json
from pathlib import Path

import pytest

from backend.executor.browser_controller import BrowserController, ExecutorTypedException
from backend.shared.executor_contracts_v1 import DomSnapshotV1, TargetKindV1, TargetV1


def _can_start_playwright() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _can_start_playwright(), reason="playwright.sync_api not available")
def test_browser_controller_locate_and_capture_observation_offline(tmp_path: Path):
    html = """
    <html>
      <head><title>Test</title></head>
      <body>
        <a id="a1" href="/x">Link Uno</a>
        <label for="u">Usuario</label>
        <input id="u" name="username" type="text" />
        <button data-testid="btn-send">Enviar</button>
        <div id="framewrap">
          <iframe id="f1" srcdoc="<button data-testid='inside'>Inside</button>"></iframe>
        </div>
      </body>
    </html>
    """

    file_path = tmp_path / "page.html"
    file_path.write_text(html, encoding="utf-8")
    url = file_path.as_uri()

    ctrl = BrowserController()
    try:
        ctrl.start(headless=True)
    except Exception as e:
        pytest.skip(f"Playwright cannot start in this environment: {e}")

    try:
        ctrl.navigate(url, timeout_ms=5000)

        # locate: testid
        loc = ctrl.locate_unique(TargetV1(type=TargetKindV1.testid, testid="btn-send"))
        assert loc is not None

        # locate: label
        loc2 = ctrl.locate_unique(TargetV1(type=TargetKindV1.label, text="Usuario", exact=True))
        assert loc2 is not None

        # locate: frame + inner_target
        loc3 = ctrl.locate_unique(
            TargetV1(
                type=TargetKindV1.frame,
                selector="#f1",
                inner_target=TargetV1(type=TargetKindV1.testid, testid="inside"),
            )
        )
        assert loc3 is not None

        evidence_dir = tmp_path / "runs" / "r_test" / "evidence"
        dom, sig, items = ctrl.capture_observation(step_id="step_000", evidence_dir=evidence_dir)

        assert dom.url.startswith("file:")
        assert dom.title == "Test"
        assert sig.screenshot_hash.startswith("sha256:")
        assert items

        # dom snapshot file should validate
        dom_path = evidence_dir / "dom" / "step_000_before.json"
        DomSnapshotV1.model_validate(json.loads(dom_path.read_text(encoding="utf-8")))

    finally:
        ctrl.close()


@pytest.mark.skipif(not _can_start_playwright(), reason="playwright.sync_api not available")
def test_locate_unique_raises_typed_error_on_missing(tmp_path: Path):
    file_path = tmp_path / "empty.html"
    file_path.write_text("<html><body><div>nope</div></body></html>", encoding="utf-8")
    url = file_path.as_uri()

    ctrl = BrowserController()
    try:
        ctrl.start(headless=True)
    except Exception as e:
        pytest.skip(f"Playwright cannot start in this environment: {e}")

    try:
        ctrl.navigate(url, timeout_ms=5000)
        with pytest.raises(ExecutorTypedException) as ei:
            ctrl.locate_unique(TargetV1(type=TargetKindV1.testid, testid="missing"), timeout_ms=1000)
        assert ei.value.error.error_code in {"TARGET_NOT_FOUND", "TARGET_NOT_UNIQUE"}
    finally:
        ctrl.close()













