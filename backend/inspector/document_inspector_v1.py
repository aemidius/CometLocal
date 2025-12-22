"""
H7.6 — DocumentInspector v1 (determinista, sin OCR ni LLM)

Características:
- Extrae texto de PDF (pypdf) y limita tamaño.
- Detecta fechas básicas (issue_date / valid_until) de forma determinista.
- Aplica criterios declarativos (criteria_profiles_v1).
- Cachea por sha256 en data/documents/_inspections/<sha256>.json
- Actualiza documents.json (inspection.*) a través de DocumentRepositoryV1.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field
from pypdf import PdfReader

from backend.inspector.criteria_profiles_v1 import CriterionResultV1, get_profile
from backend.repository.document_repository_v1 import DocumentRepositoryV1, DocumentIndexEntryV1
from backend.shared.executor_contracts_v1 import _sha256_bytes


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocumentInspectionError(Exception):
    def __init__(self, error_code: str, message: str, *, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


class InspectionReportV1(BaseModel):
    file_ref: str
    doc_hash: str
    doc_type: str
    criteria_profile: Optional[str] = None
    status: str  # ok | failed

    checks: List[Dict[str, Any]] = Field(default_factory=list)
    extracted: Dict[str, Any] = Field(default_factory=dict)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)


@dataclass(frozen=True)
class InspectorConfigV1:
    max_text_bytes: int = 5 * 1024 * 1024  # 5MB


DATE_PATTERNS: List[Tuple[str, re.Pattern]] = [
    # Nota: usamos (?!\\d) en vez de \\b al final para soportar PDFs donde el extractor
    # concatena texto sin separadores (p.ej. "...2025-01-01Válido...").
    ("yyyy-mm-dd", re.compile(r"(20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])(?!\d)")),
    ("dd/mm/yyyy", re.compile(r"(0[1-9]|[12]\d|3[01])/(0[1-9]|1[0-2])/(20\d{2})(?!\d)")),
    ("dd-mm-yyyy", re.compile(r"(0[1-9]|[12]\d|3[01])-(0[1-9]|1[0-2])-(20\d{2})(?!\d)")),
]

ISSUE_KEYWORDS = [
    "fecha de emisión",
    "fecha de emision",
    "fecha de expedición",
    "fecha de expedicion",
    "expedición",
    "expedicion",
    "emitido el",
]

VALID_UNTIL_KEYWORDS = [
    "válido hasta",
    "valido hasta",
    "caduca",
    "fecha de caducidad",
    "vigente hasta",
]

def _normalize_for_match(s: str) -> str:
    """
    Normalización determinista para matching keyword/line:
    - NFKD + remove diacritics
    - lower
    - colapsa whitespace
    - elimina el replacement char (�) que aparece en algunos PDFs
    """
    s = (s or "").replace("�", " ")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _to_iso_date(match_kind: str, m: re.Match) -> Optional[str]:
    try:
        if match_kind == "yyyy-mm-dd":
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        elif match_kind in ("dd/mm/yyyy", "dd-mm-yyyy"):
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            return None
        return date(y, mo, d).isoformat()
    except Exception:
        return None


def _find_date_in_line(line: str) -> Optional[Tuple[str, str]]:
    for kind, pat in DATE_PATTERNS:
        m = pat.search(line)
        if m:
            iso = _to_iso_date(kind, m)
            if iso:
                return iso, f"matched {kind} in line"
    return None


def _find_all_dates_in_text(raw_lines: List[str]) -> List[Tuple[str, str]]:
    """
    Devuelve todas las fechas detectadas en orden de aparición (aprox):
    - orden por línea
    - dentro de cada línea, por índice de match
    Determinista: desempate por orden de DATE_PATTERNS.
    """
    out: List[Tuple[str, str]] = []
    for ln in raw_lines:
        candidates: List[Tuple[int, int, str, str]] = []  # (start, pat_idx, iso, kind)
        for pat_idx, (kind, pat) in enumerate(DATE_PATTERNS):
            for m in pat.finditer(ln):
                iso = _to_iso_date(kind, m)
                if iso:
                    candidates.append((m.start(), pat_idx, iso, kind))
        candidates.sort(key=lambda x: (x[0], x[1]))
        for _, _, iso, kind in candidates:
            out.append((iso, f"matched {kind} in line"))
    return out


def detect_dates(text: str) -> Tuple[Dict[str, Any], List[str]]:
    """
    Devuelve extracted {issue_date, valid_until, issuer?} y un log de decisiones.
    Determinismo:
    - Busca keywords en orden.
    - En la primera línea que matchea, toma la primera fecha de esa línea.
    - Si no encuentra por keyword, toma la primera fecha global por aparición para issue_date.
    """
    logs: List[str] = []
    raw_lines = [re.sub(r"\s+", " ", (ln or "")).strip() for ln in text.splitlines()]
    lines_norm = [_normalize_for_match(ln) for ln in raw_lines]

    issue_date = None
    valid_until = None

    # Issue date por keyword
    for kw in ISSUE_KEYWORDS:
        kw_l = _normalize_for_match(kw)
        for raw_ln, ln_norm in zip(raw_lines, lines_norm):
            if kw_l and kw_l in ln_norm:
                found = _find_date_in_line(raw_ln)
                if found:
                    issue_date, why = found
                    logs.append(f"issue_date: keyword={kw!r} -> {issue_date} ({why})")
                    break
        if issue_date:
            break

    # Valid until por keyword
    for kw in VALID_UNTIL_KEYWORDS:
        kw_l = _normalize_for_match(kw)
        for raw_ln, ln_norm in zip(raw_lines, lines_norm):
            if kw_l and kw_l in ln_norm:
                found = _find_date_in_line(raw_ln)
                if found:
                    valid_until, why = found
                    logs.append(f"valid_until: keyword={kw!r} -> {valid_until} ({why})")
                    break
        if valid_until:
            break

    # Fallback determinista: primera fecha global por aparición
    all_dates = _find_all_dates_in_text(raw_lines)
    if issue_date is None and all_dates:
        issue_date, why = all_dates[0]
        logs.append(f"issue_date: fallback first_global -> {issue_date} ({why})")

    # Fallback determinista para valid_until: segunda fecha global si existe (y no hay keyword)
    if valid_until is None and len(all_dates) >= 2:
        valid_until, why = all_dates[1]
        logs.append(f"valid_until: fallback second_global -> {valid_until} ({why})")

    extracted = {
        "issue_date": issue_date,
        "valid_until": valid_until,
        "issuer": None,
    }
    return extracted, logs


class DocumentInspectorV1:
    def __init__(self, *, repository: DocumentRepositoryV1, config: Optional[InspectorConfigV1] = None):
        self.repo = repository
        self.cfg = config or InspectorConfigV1()

    def _inspection_dir(self) -> Path:
        d = self.repo.cfg.documents_dir / "_inspections"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _report_path(self, sha256: str) -> Path:
        return self._inspection_dir() / f"{sha256}.json"

    def extract_text_pdf(self, path: Path) -> str:
        try:
            reader = PdfReader(str(path))
        except Exception as e:
            raise DocumentInspectionError("DOCUMENT_PARSE_FAILED", "cannot open pdf", details={"cause": repr(e)})
        parts: List[str] = []
        size = 0
        for i, page in enumerate(reader.pages):
            try:
                t = page.extract_text() or ""
            except Exception as e:
                raise DocumentInspectionError("DOCUMENT_PARSE_FAILED", "pdf text extraction failed", details={"page": i, "cause": repr(e)})
            if not t:
                continue
            b = t.encode("utf-8", errors="ignore")
            if size + len(b) > self.cfg.max_text_bytes:
                # cortar determinista
                remain = max(0, self.cfg.max_text_bytes - size)
                parts.append(b[:remain].decode("utf-8", errors="ignore"))
                size = self.cfg.max_text_bytes
                break
            parts.append(t)
            size += len(b)

        text = "\n".join(parts).strip()
        if not text:
            raise DocumentInspectionError("DOCUMENT_NO_TEXT", "pdf contains no extractable text (no OCR in v1)")
        return text

    def inspect(self, *, file_ref: str, expected_criteria_profile: Optional[str] = None) -> Tuple[str, InspectionReportV1]:
        """
        Devuelve (status, report).
        Actualiza documents.json: inspection.* y report_ref/doc_hash.
        """
        entry: DocumentIndexEntryV1 = self.repo.validate(file_ref)
        doc_hash = entry.sha256

        profile = expected_criteria_profile or entry.expected_criteria_profile
        report_path = self._report_path(doc_hash)
        report_ref = str(report_path.relative_to(self.repo.cfg.project_root)).replace("\\", "/")

        # Cache por hash: si ya existe, reutilizar (determinista)
        if report_path.exists():
            try:
                cached = InspectionReportV1.model_validate_json(report_path.read_text(encoding="utf-8"))
                if cached.doc_hash == doc_hash and cached.file_ref == file_ref:
                    # actualizar índice como ok/failed según cached
                    self.repo.update_inspection(
                        file_ref,
                        status=cached.status,
                        doc_hash=doc_hash,
                        report_ref=report_ref,
                        last_inspected_at=_now_iso(),
                    )
                    return cached.status, cached
            except Exception:
                # si está corrupto, re-inspeccionar
                pass

        # Inspección
        errors: List[Dict[str, Any]] = []
        checks: List[Dict[str, Any]] = []
        extracted: Dict[str, Any] = {}

        try:
            text = self.extract_text_pdf(self.repo.resolve(file_ref))
        except DocumentInspectionError as e:
            errors.append({"error_code": e.error_code, "message": str(e), "details": e.details})
            rep = InspectionReportV1(
                file_ref=file_ref,
                doc_hash=doc_hash,
                doc_type=entry.doc_type,
                criteria_profile=profile,
                status="failed",
                checks=[],
                extracted={"issue_date": None, "valid_until": None, "issuer": None},
                errors=errors,
            )
            report_path.write_text(json.dumps(rep.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
            self.repo.update_inspection(file_ref, status="failed", doc_hash=doc_hash, report_ref=report_ref, last_inspected_at=_now_iso())
            return "failed", rep

        extracted, logs = detect_dates(text)
        extracted["_selection_log"] = logs

        criteria = get_profile(profile)
        ok_all = True
        for c in criteria:
            try:
                ok, details = c.fn(text, extracted, {"company_id": entry.company_id, "worker_id": entry.worker_id, **(entry.metadata or {})})
            except Exception as e:
                ok = False
                details = f"exception: {repr(e)}"
            checks.append({"id": c.id, "status": "ok" if ok else "failed", "details": details})
            if not ok:
                ok_all = False

        status = "ok" if ok_all else "failed"
        rep = InspectionReportV1(
            file_ref=file_ref,
            doc_hash=doc_hash,
            doc_type=entry.doc_type,
            criteria_profile=profile,
            status=status,
            checks=checks,
            extracted={k: v for k, v in extracted.items() if not k.startswith("_")},
            errors=errors,
        )

        report_path.write_text(json.dumps(rep.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        self.repo.update_inspection(file_ref, status=status, doc_hash=doc_hash, report_ref=report_ref, last_inspected_at=_now_iso())
        return status, rep


