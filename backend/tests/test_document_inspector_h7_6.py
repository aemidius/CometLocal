from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.inspector.document_inspector_v1 import DocumentInspectorV1
from backend.repository.document_repository_v1 import DocumentRepositoryV1


def _make_pdf_with_text(tmp_path: Path, *, lines: list[str]) -> Path:
    """
    Crea un PDF con texto extraíble usando pypdf (sin librerías extra).
    """
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    # Fuente Helvetica
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)  # noqa: SLF001 (pypdf internal)

    resources = page.get("/Resources") or DictionaryObject()
    fonts = resources.get("/Font") or DictionaryObject()
    fonts[NameObject("/F1")] = font_ref
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources

    # Stream de contenido: imprime cada línea en una nueva línea
    content_lines = []
    content_lines.append("BT")
    content_lines.append("/F1 12 Tf")
    content_lines.append("72 740 Td")
    for idx, ln in enumerate(lines):
        safe = ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if idx > 0:
            content_lines.append("T*")
        content_lines.append(f"({safe}) Tj")
    content_lines.append("ET")
    stream = DecodedStreamObject()
    stream.set_data(("\n".join(content_lines)).encode("utf-8"))
    stream_ref = writer._add_object(stream)  # noqa: SLF001
    page[NameObject("/Contents")] = stream_ref

    out = tmp_path / "doc.pdf"
    with open(out, "wb") as f:
        writer.write(f)
    return out


def test_inspect_ok_and_cache_by_hash(tmp_path: Path):
    repo = DocumentRepositoryV1(project_root=tmp_path, data_root="data")
    inspector = DocumentInspectorV1(repository=repo)

    today = date.today()
    issue = (today - timedelta(days=30)).isoformat()
    valid = (today + timedelta(days=365)).isoformat()

    pdf = _make_pdf_with_text(tmp_path, lines=[f"Fecha de emisión: {issue}", f"Válido hasta: {valid}"])

    file_ref = repo.register(
        path=pdf,
        metadata={
            "company_id": "c1",
            "worker_id": "w1",
            "doc_type": "medical_fit",
            "namespace": "medical",
            "name": "fit_2025",
            "expected_criteria_profile": "medical_fit_v1",
        },
    )

    status1, report1 = inspector.inspect(file_ref=file_ref, expected_criteria_profile=None)
    assert status1 == "ok"
    assert report1.status == "ok"
    assert report1.extracted["issue_date"] == issue
    assert report1.extracted["valid_until"] == valid

    # Cache: debe reutilizar el mismo doc_hash y report en _inspections
    report_path = repo.cfg.documents_dir / "_inspections" / f"{report1.doc_hash}.json"
    assert report_path.exists()
    status2, report2 = inspector.inspect(file_ref=file_ref, expected_criteria_profile=None)
    assert status2 == "ok"
    assert report2.doc_hash == report1.doc_hash

    # documents.json actualizado
    entry = repo.validate(file_ref)
    assert entry.inspection.status == "ok"
    assert entry.inspection.doc_hash == report1.doc_hash
    assert entry.inspection.report_ref is not None


def test_inspect_fail_expired(tmp_path: Path):
    repo = DocumentRepositoryV1(project_root=tmp_path, data_root="data")
    inspector = DocumentInspectorV1(repository=repo)

    today = date.today()
    issue = (today - timedelta(days=400)).isoformat()
    valid = (today - timedelta(days=1)).isoformat()

    pdf = _make_pdf_with_text(tmp_path, lines=[f"Fecha de expedición: {issue}", f"Caduca: {valid}"])
    file_ref = repo.register(
        path=pdf,
        metadata={
            "company_id": "c1",
            "worker_id": "w1",
            "doc_type": "medical_fit",
            "namespace": "medical",
            "name": "fit_expired",
            "expected_criteria_profile": "medical_fit_v1",
        },
    )

    status, report = inspector.inspect(file_ref=file_ref)
    assert status == "failed"
    assert report.status == "failed"
    assert any(c["status"] == "failed" for c in report.checks)


def test_inspect_no_text_returns_document_no_text(tmp_path: Path):
    from pypdf import PdfWriter

    repo = DocumentRepositoryV1(project_root=tmp_path, data_root="data")
    inspector = DocumentInspectorV1(repository=repo)

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    pdf = tmp_path / "blank.pdf"
    with open(pdf, "wb") as f:
        writer.write(f)

    file_ref = repo.register(
        path=pdf,
        metadata={
            "company_id": "c1",
            "worker_id": "w1",
            "doc_type": "prl_training",
            "namespace": "training",
            "name": "no_text",
            "expected_criteria_profile": "prl_training_v1",
        },
    )

    status, report = inspector.inspect(file_ref=file_ref)
    assert status == "failed"
    assert report.status == "failed"
    assert any(e.get("error_code") == "DOCUMENT_NO_TEXT" for e in report.errors)




