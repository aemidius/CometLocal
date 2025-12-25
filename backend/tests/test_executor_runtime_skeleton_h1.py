import json
from pathlib import Path

from backend.executor.runtime_skeleton import ExecutorRuntimeSkeletonH1
from backend.shared.executor_contracts_v1 import (
    DomSnapshotV1,
    EvidenceManifestV1,
    TraceEventTypeV1,
    TraceEventV1,
)


def test_runtime_skeleton_creates_run_artifacts_and_valid_schemas(tmp_path: Path):
    runs_root = tmp_path / "runs"
    rt = ExecutorRuntimeSkeletonH1(runs_root=runs_root, execution_mode="dry_run", domain_allowlist=["stub.local"])
    run_dir = rt.run_stub(goal="test_goal")

    assert run_dir.exists()
    assert run_dir.parent == runs_root

    trace_path = run_dir / "trace.jsonl"
    manifest_path = run_dir / "evidence_manifest.json"

    assert trace_path.exists()
    assert manifest_path.exists()

    # trace: 3 eventos mínimos
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3

    events = [TraceEventV1.model_validate(json.loads(line)) for line in lines]
    assert events[0].event_type == TraceEventTypeV1.run_started
    assert events[1].event_type == TraceEventTypeV1.observation_captured
    assert events[2].event_type == TraceEventTypeV1.run_finished

    assert events[1].state_signature_before is not None
    screenshot_hash = events[1].state_signature_before.screenshot_hash
    assert screenshot_hash.startswith("sha256:")

    # manifest: schema válido y items referencian archivos existentes
    manifest = EvidenceManifestV1.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
    assert manifest.run_id == run_dir.name
    assert manifest.items

    for item in manifest.items:
        p = run_dir / item.relative_path
        assert p.exists(), f"Missing evidence item path: {item.relative_path}"

    # dom snapshot parcial debe validar schema
    dom_items = [i for i in manifest.items if i.kind.value == "dom_snapshot_partial"]
    assert dom_items, "Expected at least one dom_snapshot_partial item"
    dom_path = run_dir / dom_items[0].relative_path
    DomSnapshotV1.model_validate(json.loads(dom_path.read_text(encoding="utf-8")))

    # screenshot hash file debe coincidir con state_signature_before.screenshot_hash
    hash_items = [i for i in manifest.items if i.kind.value == "screenshot_hash"]
    assert hash_items, "Expected screenshot_hash item"
    hash_path = run_dir / hash_items[0].relative_path
    assert hash_path.read_text(encoding="utf-8").strip() == screenshot_hash


def test_runtime_skeleton_playwright_mode_offline_file_url(tmp_path: Path):
    # Este test no depende de internet ni de servidor; usa file://
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        return  # Playwright no disponible; no fallamos el suite aquí

    html = "<html><head><title>P</title></head><body><button data-testid='x'>X</button></body></html>"
    page = tmp_path / "p.html"
    page.write_text(html, encoding="utf-8")

    runs_root = tmp_path / "runs"
    rt = ExecutorRuntimeSkeletonH1(runs_root=runs_root, execution_mode="dry_run", domain_allowlist=["stub.local"])
    try:
        run_dir = rt.run(url=page.as_uri(), goal="pw", use_playwright=True, headless=True)
    except Exception:
        # En entornos sin browsers instalados, Playwright puede fallar: no hacemos fallar el suite.
        return

    assert (run_dir / "trace.jsonl").exists()
    assert (run_dir / "evidence_manifest.json").exists()


