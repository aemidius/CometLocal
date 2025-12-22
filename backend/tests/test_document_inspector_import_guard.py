from pathlib import Path

import pytest

from backend.inspector.document_inspector_v1 import DocumentInspectorV1
from backend.repository.document_repository_v1 import DocumentRepositoryV1


def test_inspector_returns_parse_failed_when_pypdf_missing(monkeypatch, tmp_path: Path):
    # Simular ausencia de dependencia opcional
    import backend.inspector.document_inspector_v1 as mod

    monkeypatch.setattr(mod, "PdfReader", None, raising=True)

    repo = DocumentRepositoryV1(project_root=tmp_path, data_root="data")
    inspector = DocumentInspectorV1(repository=repo)

    dummy = tmp_path / "dummy.pdf"
    dummy.write_bytes(b"%PDF-FAKE\\n")
    file_ref = repo.register(
        path=dummy,
        metadata={
            "company_id": "c1",
            "worker_id": "w1",
            "doc_type": "prl_training",
            "namespace": "training",
            "name": "x",
            "expected_criteria_profile": "prl_training_v1",
        },
    )

    status, report = inspector.inspect(file_ref=file_ref)
    assert status == "failed"
    assert report.status == "failed"
    assert report.errors, "expected DOCUMENT_PARSE_FAILED error"
    assert report.errors[0]["error_code"] == "DOCUMENT_PARSE_FAILED"
    assert report.errors[0]["message"] == "pypdf not installed"


