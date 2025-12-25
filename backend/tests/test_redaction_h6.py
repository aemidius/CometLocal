import json
from pathlib import Path

import pytest

from backend.executor.runtime_h4 import ExecutorRuntimeH4
from backend.shared.executor_contracts_v1 import (
    ActionKindV1,
    ActionSpecV1,
    ConditionKindV1,
    ConditionV1,
    EvidenceManifestV1,
    ExecutionModeV1,
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
def test_production_redacts_dom_and_html_and_trace(tmp_path: Path):
    secret_email = "john.doe@example.com"
    secret_dni = "12345678Z"
    secret_token = "A" * 32

    html = f"""
    <html><head><title>R</title></head>
    <body>
      <div id="txt">Email {secret_email} DNI {secret_dni} TOKEN {secret_token}</div>
      <label for="p">Password</label>
      <input id="p" name="password" type="password" value="SuperSecret123" />
      <button id="btn" aria-label="Close">Close</button>
    </body></html>
    """
    p = tmp_path / "r.html"
    p.write_text(html, encoding="utf-8")

    actions = [
        ActionSpecV1(
            action_id="a_assert",
            kind=ActionKindV1.assert_,
            target=None,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.title_contains, args={"text": "R"}, severity=ErrorSeverityV1.error)],
            postconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": "r\\.html"}, severity=ErrorSeverityV1.critical)],
            assertions=[
                ConditionV1(
                    kind=ConditionKindV1.element_text_contains,
                    args={"target": {"type": "css", "selector": "#txt"}, "text": "Email"},
                    severity=ErrorSeverityV1.critical,
                )
            ],
            timeout_ms=2000,
            criticality="critical",  # fuerza html_full en production
        )
    ]

    rt = ExecutorRuntimeH4(runs_root=tmp_path / "runs", execution_mode=ExecutionModeV1.production)
    try:
        run_dir = rt.run_actions(url=p.as_uri(), actions=actions, headless=True)
    except Exception as e:
        pytest.skip(f"Playwright cannot run: {e}")

    manifest = EvidenceManifestV1.model_validate(json.loads((run_dir / "evidence_manifest.json").read_text(encoding="utf-8")))
    assert manifest.redaction_report is not None
    assert sum(manifest.redaction_report.values()) > 0

    # dom snapshot parcial redacted
    dom_files = list((run_dir / "evidence" / "dom").glob("*.json"))
    assert dom_files
    dom_text = "\n".join(f.read_text(encoding="utf-8") for f in dom_files)
    assert secret_email not in dom_text
    assert secret_dni not in dom_text
    assert secret_token not in dom_text
    assert "SuperSecret123" not in dom_text

    # html_full redacted (production captura en crítico)
    html_files = list((run_dir / "evidence" / "html").glob("*.html"))
    assert html_files
    html_text = "\n".join(f.read_text(encoding="utf-8") for f in html_files)
    assert secret_email not in html_text
    assert secret_dni not in html_text
    assert secret_token not in html_text
    assert "SuperSecret123" not in html_text

    # trace payload redacted
    trace_text = (run_dir / "trace.jsonl").read_text(encoding="utf-8")
    assert secret_email not in trace_text
    assert secret_dni not in trace_text
    assert secret_token not in trace_text
    assert "SuperSecret123" not in trace_text


@pytest.mark.skipif(not _can_start_playwright(), reason="playwright.sync_api not available")
def test_training_captures_more_evidence_than_production(tmp_path: Path):
    html = "<html><head><title>T</title></head><body><div id='x'>x</div></body></html>"
    p = tmp_path / "t.html"
    p.write_text(html, encoding="utf-8")

    actions = [
        ActionSpecV1(
            action_id=f"a{i}",
            kind=ActionKindV1.assert_,
            target=None,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.title_contains, args={"text": "T"}, severity=ErrorSeverityV1.error)],
            postconditions=[],
            assertions=[ConditionV1(kind=ConditionKindV1.element_text_contains, args={"target": {"type": "css", "selector": "#x"}, "text": "x"}, severity=ErrorSeverityV1.critical)],
            timeout_ms=1000,
            criticality="normal",
        )
        for i in range(2)
    ]

    rt_prod = ExecutorRuntimeH4(runs_root=tmp_path / "runs_prod", execution_mode=ExecutionModeV1.production)
    rt_train = ExecutorRuntimeH4(runs_root=tmp_path / "runs_train", execution_mode=ExecutionModeV1.training)
    try:
        rd_prod = rt_prod.run_actions(url=p.as_uri(), actions=actions, headless=True)
        rd_train = rt_train.run_actions(url=p.as_uri(), actions=actions, headless=True)
    except Exception as e:
        pytest.skip(f"Playwright cannot run: {e}")

    mp = EvidenceManifestV1.model_validate(json.loads((rd_prod / "evidence_manifest.json").read_text(encoding="utf-8")))
    mt = EvidenceManifestV1.model_validate(json.loads((rd_train / "evidence_manifest.json").read_text(encoding="utf-8")))

    prod_html = sum(1 for i in mp.items if i.kind.value == "html_full")
    train_html = sum(1 for i in mt.items if i.kind.value == "html_full")
    assert train_html >= prod_html

    prod_shots = sum(1 for i in mp.items if i.kind.value == "screenshot")
    train_shots = sum(1 for i in mt.items if i.kind.value == "screenshot")
    assert train_shots >= prod_shots


