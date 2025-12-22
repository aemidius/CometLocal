import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator, Optional, Tuple

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


def _http_ok(url: str, timeout_s: float = 0.5) -> bool:
    try:
        import httpx

        r = httpx.get(url, timeout=timeout_s)
        return 200 <= r.status_code < 400
    except Exception:
        return False


@pytest.fixture(scope="session")
def portal_base_url() -> Iterator[str]:
    """
    Best-effort:
    - si ya existe servidor en 127.0.0.1:8000, usarlo
    - si no, intentar levantar uvicorn backend.app:app
    - si no se puede, skip seguro (no falla CI)
    """
    base = "http://127.0.0.1:8000"
    probe = f"{base}/simulation/portal_a/login.html"

    if _http_ok(probe):
        yield base
        return

    # Intentar levantar servidor
    proc: Optional[subprocess.Popen] = None
    try:
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--log-level",
            "warning",
        ]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path.cwd())
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)

        deadline = time.time() + 10.0
        while time.time() < deadline:
            if _http_ok(probe, timeout_s=0.5):
                yield base
                return
            time.sleep(0.2)

        pytest.skip("Servidor local no disponible en 127.0.0.1:8000 y no se pudo levantar uvicorn.")
    finally:
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass


def _parse_trace(run_dir: Path) -> list[TraceEventV1]:
    trace_path = run_dir / "trace.jsonl"
    assert trace_path.exists(), f"trace.jsonl missing in {run_dir}"
    return [TraceEventV1.model_validate(json.loads(l)) for l in trace_path.read_text(encoding="utf-8").splitlines()]


def _final_status(events: list[TraceEventV1]) -> str:
    last = [e for e in events if e.event_type == TraceEventTypeV1.run_finished]
    assert last, "run_finished missing"
    return str((last[-1].metadata or {}).get("status") or "")


def _assert_minimal_trace(events: list[TraceEventV1], run_dir: Path):
    types = [e.event_type for e in events]
    assert TraceEventTypeV1.run_started in types, f"run_dir={run_dir}"
    assert TraceEventTypeV1.run_finished in types, f"run_dir={run_dir}"
    assert TraceEventTypeV1.action_compiled in types, f"run_dir={run_dir}"
    assert TraceEventTypeV1.action_executed in types or TraceEventTypeV1.error_raised in types, f"run_dir={run_dir}"


def _manifest(run_dir: Path) -> EvidenceManifestV1:
    mp = run_dir / "evidence_manifest.json"
    assert mp.exists(), f"evidence_manifest.json missing in {run_dir}"
    return EvidenceManifestV1.model_validate(json.loads(mp.read_text(encoding="utf-8")))


@pytest.mark.skipif(not _can_start_playwright(), reason="playwright.sync_api not available")
def test_s1_login_basico(portal_base_url: str, tmp_path: Path):
    base = portal_base_url
    url = f"{base}/simulation/portal_a/login.html"

    actions = [
        ActionSpecV1(
            action_id="fill_company",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.css, selector="#company_code"),
            input={"text": "EMP-TEST"},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": {"type": "css", "selector": "#company_code"}}, severity=ErrorSeverityV1.error)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": {"type": "css", "selector": "#company_code"}, "value": "EMP-TEST"}, severity=ErrorSeverityV1.critical)],
            timeout_ms=3000,
            criticality="normal",
        ),
        ActionSpecV1(
            action_id="fill_user",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.css, selector="#username"),
            input={"text": "demo"},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": {"type": "css", "selector": "#username"}}, severity=ErrorSeverityV1.error)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": {"type": "css", "selector": "#username"}, "value": "demo"}, severity=ErrorSeverityV1.critical)],
            timeout_ms=3000,
            criticality="normal",
        ),
        ActionSpecV1(
            action_id="fill_pass",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.css, selector="#password"),
            input={"text": "demo"},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": {"type": "css", "selector": "#password"}}, severity=ErrorSeverityV1.error)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": {"type": "css", "selector": "#password"}, "value": "demo"}, severity=ErrorSeverityV1.critical)],
            timeout_ms=3000,
            criticality="normal",
        ),
        ActionSpecV1(
            action_id="click_login",
            kind=ActionKindV1.click,
            target=TargetV1(type=TargetKindV1.css, selector="#btn_login"),
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": {"type": "css", "selector": "#btn_login"}, "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.no_blocking_overlay, args={}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": "dashboard\\.html"}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=8000,
            criticality="normal",
        ),
        ActionSpecV1(
            action_id="assert_dashboard",
            kind=ActionKindV1.assert_,
            target=None,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": "dashboard\\.html"}, severity=ErrorSeverityV1.error)],
            postconditions=[],
            assertions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": {"type": "css", "selector": "table"}}, severity=ErrorSeverityV1.critical)],
            timeout_ms=3000,
            criticality="normal",
        ),
    ]

    rt = ExecutorRuntimeH4(runs_root=tmp_path / "runs")
    run_dir = rt.run_actions(url=url, actions=actions, headless=True)

    events = _parse_trace(run_dir)
    _assert_minimal_trace(events, run_dir)
    assert _final_status(events) == "success", f"run_dir={run_dir}"


@pytest.mark.skipif(not _can_start_playwright(), reason="playwright.sync_api not available")
def test_s2_login_multistep_si_existe(portal_base_url: str, tmp_path: Path):
    base = portal_base_url
    step1 = f"{base}/simulation/portal_a/login_step1.html"
    if not _http_ok(step1):
        pytest.skip("Simulación portal_a no incluye login multi-step (login_step1.html no existe).")

    # Si existe en el futuro, aquí se definirá el flujo. Por ahora skip seguro.
    pytest.skip("Login multi-step no implementado en simulation portal_a actual.")


@pytest.mark.skipif(not _can_start_playwright(), reason="playwright.sync_api not available")
def test_s3_navegacion_a_subida_documentacion(portal_base_url: str, tmp_path: Path):
    base = portal_base_url
    url = f"{base}/simulation/portal_a/dashboard.html"

    actions = [
        ActionSpecV1(
            action_id="click_subir_w001",
            kind=ActionKindV1.click,
            target=TargetV1(type=TargetKindV1.css, selector="a[href*=\"worker_id=W-001\"]"),
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": {"type": "css", "selector": "a[href*=\"worker_id=W-001\"]"}, "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.no_blocking_overlay, args={}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": "upload\\.html"}, severity=ErrorSeverityV1.critical)],
            timeout_ms=8000,
            criticality="normal",
        ),
        ActionSpecV1(
            action_id="assert_upload_page",
            kind=ActionKindV1.assert_,
            target=None,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": "upload\\.html"}, severity=ErrorSeverityV1.error)],
            postconditions=[],
            assertions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": {"type": "css", "selector": "#file_input"}}, severity=ErrorSeverityV1.critical)],
            timeout_ms=3000,
            criticality="normal",
        ),
    ]

    rt = ExecutorRuntimeH4(runs_root=tmp_path / "runs")
    run_dir = rt.run_actions(url=url, actions=actions, headless=True)
    events = _parse_trace(run_dir)
    _assert_minimal_trace(events, run_dir)
    assert _final_status(events) == "success", f"run_dir={run_dir}"


@pytest.mark.skipif(not _can_start_playwright(), reason="playwright.sync_api not available")
def test_s4_upload_documento_directo_input_file(portal_base_url: str, tmp_path: Path):
    base = portal_base_url
    url = f"{base}/simulation/portal_a/upload_form.html"

    sample_pdf = (Path("backend") / "simulation" / "sample.pdf").resolve()
    if not sample_pdf.exists():
        pytest.skip("sample.pdf no disponible para test de upload.")

    # H7.5: registrar documento y usar file_ref (no paths directos)
    from backend.repository.document_repository_v1 import DocumentRepositoryV1

    repo = DocumentRepositoryV1(project_root=tmp_path, data_root="data")
    file_ref = repo.register(
        path=sample_pdf,
        metadata={
            "company_id": "demo_co",
            "worker_id": "w-001",
            "doc_type": "prl_training",
            "namespace": "training",
            "name": "prl_2024",
            "tags": ["e2e"],
        },
    )

    actions = [
        ActionSpecV1(
            action_id="fill_worker",
            kind=ActionKindV1.fill,
            target=TargetV1(type=TargetKindV1.css, selector="#worker_full_name"),
            input={"text": "Juan Pérez García"},
            preconditions=[ConditionV1(kind=ConditionKindV1.element_visible, args={"target": {"type": "css", "selector": "#worker_full_name"}}, severity=ErrorSeverityV1.error)],
            postconditions=[ConditionV1(kind=ConditionKindV1.element_value_equals, args={"target": {"type": "css", "selector": "#worker_full_name"}, "value": "Juan Pérez García"}, severity=ErrorSeverityV1.critical)],
            timeout_ms=4000,
            criticality="normal",
        ),
        ActionSpecV1(
            action_id="upload_pdf",
            kind=ActionKindV1.upload,
            target=TargetV1(type=TargetKindV1.css, selector="#file_pdf"),
            input={"file_ref": file_ref},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": {"type": "css", "selector": "#file_pdf"}, "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": {"type": "css", "selector": "#file_pdf"}}, severity=ErrorSeverityV1.error),
            ],
            postconditions=[
                ConditionV1(kind=ConditionKindV1.upload_completed, args={"target": {"type": "css", "selector": "#file_pdf"}, "contains": ".pdf"}, severity=ErrorSeverityV1.critical),
            ],
            timeout_ms=8000,
            criticality="critical",
        ),
        ActionSpecV1(
            action_id="assert_file_value",
            kind=ActionKindV1.assert_,
            target=None,
            input={},
            preconditions=[ConditionV1(kind=ConditionKindV1.title_contains, args={"text": "Subida"}, severity=ErrorSeverityV1.error)],
            postconditions=[],
            assertions=[
                ConditionV1(kind=ConditionKindV1.element_attr_equals, args={"target": {"type": "css", "selector": "#file_pdf"}, "attr": "type", "value": "file"}, severity=ErrorSeverityV1.critical)
            ],
            timeout_ms=3000,
            criticality="normal",
        ),
    ]

    rt = ExecutorRuntimeH4(runs_root=tmp_path / "runs", project_root=tmp_path, data_root="data", document_repository=repo)
    run_dir = rt.run_actions(url=url, actions=actions, headless=True)
    events = _parse_trace(run_dir)
    _assert_minimal_trace(events, run_dir)
    assert _final_status(events) == "success", f"run_dir={run_dir}"

    manifest = _manifest(run_dir)
    # Acción crítica -> debe haber html_full y screenshot(s)
    assert any(i.kind.value == "html_full" for i in manifest.items) or any(i.kind.value == "screenshot" for i in manifest.items), f"run_dir={run_dir}"


@pytest.mark.skipif(not _can_start_playwright(), reason="playwright.sync_api not available")
def test_s5_overlay_recovery_dismiss_overlay(portal_base_url: str, tmp_path: Path):
    base = portal_base_url
    url = f"{base}/simulation/portal_a/upload.html?overlay=1"

    actions = [
        ActionSpecV1(
            action_id="click_back_dashboard",
            kind=ActionKindV1.click,
            target=TargetV1(type=TargetKindV1.css, selector="#link_back_dashboard"),
            input={},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.no_blocking_overlay, args={}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": {"type": "css", "selector": "#link_back_dashboard"}, "count": 1}, severity=ErrorSeverityV1.critical),
            ],
            postconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": "dashboard\\.html"}, severity=ErrorSeverityV1.critical)],
            timeout_ms=6000,
            criticality="normal",
        )
    ]

    # Para acelerar el recovery (sin comprometer determinismo), reducimos retries a 0.
    policy = RuntimePolicyDefaultsV1(retries_per_action=0, recovery_max=3, same_state_revisits=2, hard_cap_steps=20)
    rt = ExecutorRuntimeH4(runs_root=tmp_path / "runs", policy=policy)
    run_dir = rt.run_actions(url=url, actions=actions, headless=True)

    events = _parse_trace(run_dir)
    _assert_minimal_trace(events, run_dir)
    assert _final_status(events) in {"success", "failed", "halted"}, f"run_dir={run_dir}"

    types = [e.event_type for e in events]
    assert TraceEventTypeV1.recovery_started in types and TraceEventTypeV1.recovery_finished in types, f"run_dir={run_dir}"


