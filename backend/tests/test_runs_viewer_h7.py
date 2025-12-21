import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.executor.runs_viewer import create_runs_viewer_router, parse_run


def _write_minimal_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    # Trace mínimo con run_started + observation_captured + run_finished
    trace = run_dir / "trace.jsonl"
    trace.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "schema_version": "v1",
                        "run_id": run_dir.name,
                        "seq": 1,
                        "ts_utc": "2025-01-01T00:00:00+00:00",
                        "event_type": "run_started",
                        "step_id": None,
                        "state_signature_before": None,
                        "state_signature_after": None,
                        "metadata": {"execution_mode": "production"},
                    }
                ),
                json.dumps(
                    {
                        "schema_version": "v1",
                        "run_id": run_dir.name,
                        "seq": 2,
                        "ts_utc": "2025-01-01T00:00:01+00:00",
                        "event_type": "observation_captured",
                        "step_id": "step_000",
                        "state_signature_before": None,
                        "state_signature_after": None,
                        "metadata": {"policy": {"same_state_revisit_count": 1}},
                    }
                ),
                json.dumps(
                    {
                        "schema_version": "v1",
                        "run_id": run_dir.name,
                        "seq": 3,
                        "ts_utc": "2025-01-01T00:00:02+00:00",
                        "event_type": "run_finished",
                        "step_id": None,
                        "state_signature_before": None,
                        "state_signature_after": None,
                        "metadata": {"status": "success"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "evidence_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "v1",
                "run_id": run_dir.name,
                "created_at_utc": "2025-01-01T00:00:02+00:00",
                "policy": {"always": ["dom_snapshot_partial"], "on_failure_or_critical": ["html_full", "screenshot"]},
                "redaction": {"enabled": True, "rules": ["emails"], "mode": "production"},
                "items": [
                    {
                        "kind": "dom_snapshot_partial",
                        "relative_path": "evidence/dom/step_000.json",
                        "sha256": "0" * 64,
                        "size_bytes": 10,
                        "step_id": "step_000",
                    }
                ],
                "redaction_report": {"emails": 1},
                "metadata": {"execution_mode": "production"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # Archivo de evidencia apuntado por el manifest
    ev = run_dir / "evidence" / "dom"
    ev.mkdir(parents=True, exist_ok=True)
    (ev / "step_000.json").write_text("{}", encoding="utf-8")


def test_parse_run_minimal(tmp_path: Path):
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "r_test"
    _write_minimal_run(run_dir)

    parsed = parse_run(run_dir)
    assert parsed.run_id == "r_test"
    assert parsed.status == "success"
    assert parsed.mode == "production"
    assert parsed.counters["same_state_revisits_max"] == 1
    assert parsed.redaction_report == {"emails": 1}


def test_file_endpoint_blocks_path_traversal(tmp_path: Path):
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "r_test"
    _write_minimal_run(run_dir)

    app = FastAPI()
    app.include_router(create_runs_viewer_router(runs_root=runs_root))
    client = TestClient(app)

    # Intento de traversal
    resp = client.get("/runs/r_test/file/../secret.txt")
    assert resp.status_code in (400, 403)

    resp2 = client.get("/runs/r_test/file/%2e%2e/secret.txt")
    assert resp2.status_code in (400, 403)

    # Path válido dentro del run
    ok = client.get("/runs/r_test/file/evidence/dom/step_000.json")
    assert ok.status_code == 200


