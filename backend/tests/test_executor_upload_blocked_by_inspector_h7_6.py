from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.executor.runtime_h4 import ExecutorRuntimeH4
from backend.repository.document_repository_v1 import DocumentRepositoryV1
from backend.shared.executor_contracts_v1 import (
    ActionCriticalityV1,
    ActionKindV1,
    ActionSpecV1,
    ConditionKindV1,
    ConditionV1,
    ErrorSeverityV1,
    TargetKindV1,
    TargetV1,
    TraceEventTypeV1,
    TraceEventV1,
)


def _can_start_playwright() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except Exception:
        return False


def _make_pdf_with_text(tmp_path: Path, *, lines: list[str]) -> Path:
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)  # noqa: SLF001
    resources = page.get("/Resources") or DictionaryObject()
    fonts = resources.get("/Font") or DictionaryObject()
    fonts[NameObject("/F1")] = font_ref
    resources[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = resources

    content_lines = ["BT", "/F1 12 Tf", "72 740 Td"]
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


def _parse_trace(run_dir: Path) -> list[TraceEventV1]:
    events: list[TraceEventV1] = []
    trace_path = run_dir / "trace.jsonl"
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events.append(TraceEventV1.model_validate_json(line))
    return events


@pytest.mark.skipif(not _can_start_playwright(), reason="playwright.sync_api not available")
def test_upload_blocked_when_inspection_fails(tmp_path: Path):
    # HTML local con input type=file
    html = "<html><head><title>U</title></head><body><input id='f' type='file'/></body></html>"
    page_path = tmp_path / "u.html"
    page_path.write_text(html, encoding="utf-8")

    # PDF caducado
    today = date.today()
    issue = (today - timedelta(days=400)).isoformat()
    valid = (today - timedelta(days=1)).isoformat()
    pdf = _make_pdf_with_text(tmp_path, lines=[f"Fecha de expedición: {issue}", f"Caduca: {valid}"])

    repo = DocumentRepositoryV1(project_root=tmp_path, data_root="data")
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

    actions = [
        ActionSpecV1(
            action_id="nav",
            kind=ActionKindV1.navigate,
            target=TargetV1(type=TargetKindV1.url, url=page_path.as_uri()),
            preconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": ".*"}, severity=ErrorSeverityV1.warning)],
            postconditions=[ConditionV1(kind=ConditionKindV1.title_contains, args={"text": "U"}, severity=ErrorSeverityV1.critical)],
        ),
        ActionSpecV1(
            action_id="upload",
            kind=ActionKindV1.upload,
            target=TargetV1(type=TargetKindV1.css, selector="#f"),
            input={"file_ref": file_ref},
            preconditions=[
                ConditionV1(kind=ConditionKindV1.element_count_equals, args={"target": {"type": "css", "selector": "#f"}, "count": 1}, severity=ErrorSeverityV1.critical),
                ConditionV1(kind=ConditionKindV1.element_visible, args={"target": {"type": "css", "selector": "#f"}}, severity=ErrorSeverityV1.error),
            ],
            # U5: acción crítica requiere postcondición fuerte; usamos url_matches (aunque el upload será bloqueado).
            postconditions=[ConditionV1(kind=ConditionKindV1.url_matches, args={"pattern": "u\\.html"}, severity=ErrorSeverityV1.critical)],
            criticality=ActionCriticalityV1.critical,
        ),
    ]

    rt = ExecutorRuntimeH4(runs_root=tmp_path / "runs", project_root=tmp_path, data_root="data", document_repository=repo)
    run_dir = rt.run_actions(url=page_path.as_uri(), actions=actions, headless=True)

    events = _parse_trace(run_dir)
    types = [e.event_type for e in events]
    assert TraceEventTypeV1.inspection_started in types
    assert TraceEventTypeV1.inspection_finished in types
    assert TraceEventTypeV1.error_raised in types
    # Se aborta el run con failed
    assert any((e.error and e.error.error_code == "DOC_CRITERIA_FAILED") for e in events if e.event_type == TraceEventTypeV1.error_raised)


