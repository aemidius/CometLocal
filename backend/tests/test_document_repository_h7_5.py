from pathlib import Path

import pytest

from backend.repository.document_repository_v1 import DocumentRepositoryV1


def test_register_resolve_validate_and_default_inspection(tmp_path: Path):
    project_root = tmp_path
    repo = DocumentRepositoryV1(project_root=project_root, data_root="data")

    src = tmp_path / "dummy.pdf"
    src.write_bytes(b"%PDF-FAKE\nhello\n")

    file_ref = repo.register(
        path=src,
        metadata={
            "company_id": "c1",
            "worker_id": "w1",
            "doc_type": "prl_training",
            "namespace": "training",
            "name": "prl_2024",
        },
    )

    p = repo.resolve(file_ref)
    assert p.exists()
    assert str(p).replace("\\", "/").endswith("/data/documents/companies/c1/workers/w1/training/prl_2024.pdf")

    entry = repo.validate(file_ref)
    assert entry.file_ref == file_ref
    assert entry.inspection.status == "not_inspected"


def test_detect_hash_mismatch(tmp_path: Path):
    repo = DocumentRepositoryV1(project_root=tmp_path, data_root="data")
    src = tmp_path / "dummy.pdf"
    src.write_bytes(b"%PDF-FAKE\nhello\n")

    file_ref = repo.register(
        path=src,
        metadata={
            "company_id": "c1",
            "worker_id": "w1",
            "doc_type": "prl_training",
            "namespace": "training",
            "name": "prl_2024",
        },
    )

    # Corromper el archivo canónico
    canonical = repo.resolve(file_ref)
    canonical.write_bytes(b"%PDF-FAKE\nCHANGED\n")

    with pytest.raises(ValueError, match="sha256 mismatch"):
        repo.validate(file_ref)


def test_copy_to_tmp_is_ephemeral_and_does_not_touch_original(tmp_path: Path):
    repo = DocumentRepositoryV1(project_root=tmp_path, data_root="data")
    src = tmp_path / "dummy.pdf"
    src.write_bytes(b"%PDF-FAKE\nhello\n")

    file_ref = repo.register(
        path=src,
        metadata={
            "company_id": "c1",
            "worker_id": "w1",
            "doc_type": "prl_training",
            "namespace": "training",
            "name": "prl_2024",
        },
    )

    entry_before = repo.validate(file_ref)
    original_path = repo.resolve(file_ref)
    original_bytes = original_path.read_bytes()

    tmp_copy = repo.copy_to_tmp(file_ref)
    assert tmp_copy.exists()
    assert str(tmp_copy).replace("\\", "/").startswith(str((tmp_path / "data" / "tmp" / "uploads").resolve()).replace("\\", "/"))
    assert tmp_copy.read_bytes() == original_bytes

    # Verificar que el original no se tocó
    entry_after = repo.validate(file_ref)
    assert entry_after.sha256 == entry_before.sha256
    assert original_path.read_bytes() == original_bytes


