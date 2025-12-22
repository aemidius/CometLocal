"""
H7.5 — DocumentRepository v1

Objetivo:
- Resolver documentos por file_ref (nunca por path directo)
- Validar integridad (sha256) antes de usar
- Registrar documentos en estructura canónica bajo data/
- Copiar a tmp/uploads para usos efímeros (p.ej. upload Playwright)

No hace inspección de contenido (eso será H7.6).
"""

from __future__ import annotations

import json
import mimetypes
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from backend.shared.executor_contracts_v1 import _sha256_bytes
from backend.shared.file_ref_v1 import FileRefV1, parse, validate_syntax


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class InspectionPlaceholderV1(BaseModel):
    status: str = "not_inspected"  # not_inspected | ok | failed (placeholder)
    last_inspected_at: Optional[str] = None
    report_ref: Optional[str] = None
    doc_hash: Optional[str] = None


class DocumentIndexEntryV1(BaseModel):
    file_ref: str
    doc_type: str
    path: str  # relativo al project_root, p.ej. "data/documents/..."
    sha256: str
    mime_type: str
    size_bytes: int
    created_at: str = Field(default_factory=_now_iso)

    issuer: Optional[str] = None
    issue_date: Optional[str] = None  # YYYY-MM-DD
    valid_until: Optional[str] = None  # YYYY-MM-DD
    company_id: str
    worker_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    expected_criteria_profile: Optional[str] = None

    inspection: InspectionPlaceholderV1 = Field(default_factory=InspectionPlaceholderV1)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("file_ref")
    @classmethod
    def _validate_file_ref(cls, v: str) -> str:
        if not validate_syntax(v):
            raise ValueError("Invalid file_ref syntax")
        return v


@dataclass(frozen=True)
class DocumentRepositoryConfigV1:
    project_root: Path
    data_dir: Path
    documents_dir: Path
    refs_dir: Path
    tmp_uploads_dir: Path
    index_path: Path


class DocumentRepositoryV1:
    def __init__(self, *, project_root: str | Path = ".", data_root: str | Path = "data"):
        project_root = Path(project_root).resolve()
        data_dir = (project_root / data_root).resolve()
        self.cfg = DocumentRepositoryConfigV1(
            project_root=project_root,
            data_dir=data_dir,
            documents_dir=data_dir / "documents",
            refs_dir=data_dir / "refs",
            tmp_uploads_dir=data_dir / "tmp" / "uploads",
            index_path=data_dir / "refs" / "documents.json",
        )
        self._ensure_layout()

    def _ensure_layout(self) -> None:
        self.cfg.documents_dir.mkdir(parents=True, exist_ok=True)
        self.cfg.refs_dir.mkdir(parents=True, exist_ok=True)
        self.cfg.tmp_uploads_dir.mkdir(parents=True, exist_ok=True)
        if not self.cfg.index_path.exists():
            self.cfg.index_path.write_text(json.dumps({"schema_version": "v1", "documents": {}}, indent=2), encoding="utf-8")

    def _load_index(self) -> Dict[str, DocumentIndexEntryV1]:
        raw = json.loads(self.cfg.index_path.read_text(encoding="utf-8"))
        docs_obj = raw.get("documents") if isinstance(raw, dict) else None
        if docs_obj is None and isinstance(raw, dict):
            # compat: si el fichero era directamente un dict file_ref -> entry
            docs_obj = {k: v for k, v in raw.items() if k != "schema_version"}
        if not isinstance(docs_obj, dict):
            docs_obj = {}

        out: Dict[str, DocumentIndexEntryV1] = {}
        for k, v in docs_obj.items():
            try:
                entry = DocumentIndexEntryV1.model_validate(v)
                out[k] = entry
            except Exception:
                continue
        return out

    def _write_index(self, docs: Dict[str, DocumentIndexEntryV1]) -> None:
        payload = {"schema_version": "v1", "documents": {k: v.model_dump(mode="json") for k, v in docs.items()}}
        tmp = self.cfg.index_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.cfg.index_path)

    def _hash_file(self, path: Path) -> str:
        h = None
        with open(path, "rb") as f:
            data = f.read()
            h = _sha256_bytes(data)
        return h

    def _safe_resolve_repo_path(self, rel_path: str) -> Path:
        p = Path(rel_path)
        if p.is_absolute():
            raise ValueError("Absolute paths are not allowed")
        candidate = (self.cfg.project_root / p).resolve()
        # Debe estar dentro de data/
        try:
            candidate.relative_to(self.cfg.data_dir)
        except Exception as e:
            raise ValueError("Path escapes data/") from e
        return candidate

    def resolve(self, file_ref: str) -> Path:
        docs = self._load_index()
        if file_ref not in docs:
            raise FileNotFoundError(f"Unknown file_ref: {file_ref}")
        entry = docs[file_ref]
        return self._safe_resolve_repo_path(entry.path)

    def validate(self, file_ref: str) -> DocumentIndexEntryV1:
        docs = self._load_index()
        if file_ref not in docs:
            raise FileNotFoundError(f"Unknown file_ref: {file_ref}")
        entry = docs[file_ref]
        path = self._safe_resolve_repo_path(entry.path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Document missing for file_ref: {file_ref}")
        actual = self._hash_file(path)
        if actual != entry.sha256:
            raise ValueError(f"sha256 mismatch for {file_ref}: expected={entry.sha256} actual={actual}")
        return entry

    def list(self, *, company_id: str, worker_id: Optional[str] = None, doc_type: Optional[str] = None) -> List[DocumentIndexEntryV1]:
        docs = self._load_index()
        out: List[DocumentIndexEntryV1] = []
        for e in docs.values():
            if e.company_id != company_id:
                continue
            if worker_id is not None and e.worker_id != worker_id:
                continue
            if doc_type is not None and e.doc_type != doc_type:
                continue
            out.append(e)
        out.sort(key=lambda x: (x.worker_id or "", x.doc_type, x.created_at, x.file_ref))
        return out

    def register(self, *, path: str | Path, metadata: Dict[str, Any]) -> str:
        """
        Registra un fichero existente en la estructura canónica.

        metadata mínimo requerido (v1):
        - company_id (str)
        - doc_type (str)
        - namespace (str): p.ej. training | medical | contracts | insurance | other
        - name (str): slug estable p.ej. prl_2024
        - worker_id (opcional)
        - issuer/issue_date/valid_until/tags/expected_criteria_profile (opcionales)
        """
        src = Path(path).resolve()
        if not src.exists() or not src.is_file():
            raise FileNotFoundError(f"Cannot register missing file: {src}")

        company_id = str(metadata.get("company_id") or "")
        if not company_id:
            raise ValueError("metadata.company_id is required")
        worker_id = metadata.get("worker_id")
        if worker_id is not None:
            worker_id = str(worker_id)

        doc_type = str(metadata.get("doc_type") or "")
        if not doc_type:
            raise ValueError("metadata.doc_type is required")

        namespace = str(metadata.get("namespace") or "")
        name = str(metadata.get("name") or "")
        if not namespace or not name:
            raise ValueError("metadata.namespace and metadata.name are required")

        # Construir file_ref
        if worker_id:
            file_ref = f"doc:company:{company_id}:worker:{worker_id}:{namespace}:{name}"
        else:
            file_ref = f"doc:company:{company_id}:company_docs:{namespace}:{name}"
        fr = parse(file_ref)  # valida sintaxis y shape

        docs = self._load_index()
        if file_ref in docs:
            raise ValueError(f"file_ref already exists (no overwrite): {file_ref}")

        # Destino canónico
        if fr.scope == "worker":
            dest_dir = self.cfg.documents_dir / "companies" / company_id / "workers" / str(worker_id) / namespace
        else:
            dest_dir = self.cfg.documents_dir / "companies" / company_id / "company_docs" / namespace
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Mantener nombre original si sirve; pero asegurar determinismo por slug
        ext = src.suffix.lower() if src.suffix else ".bin"
        dest_name = f"{name}{ext}"
        dest = (dest_dir / dest_name).resolve()

        # Seguridad: dest debe estar en data/documents
        try:
            dest.relative_to(self.cfg.documents_dir.resolve())
        except Exception as e:
            raise ValueError("Destination escapes documents_dir") from e

        if dest.exists():
            raise ValueError(f"Destination exists (no overwrite): {dest}")

        shutil.copy2(src, dest)

        sha = self._hash_file(dest)
        size = dest.stat().st_size
        mime = mimetypes.guess_type(dest.name)[0] or "application/octet-stream"
        rel_to_project = str(dest.relative_to(self.cfg.project_root)).replace("\\", "/")

        entry = DocumentIndexEntryV1(
            file_ref=file_ref,
            doc_type=doc_type,
            path=rel_to_project,
            sha256=sha,
            mime_type=mime,
            size_bytes=size,
            issuer=metadata.get("issuer"),
            issue_date=metadata.get("issue_date"),
            valid_until=metadata.get("valid_until"),
            company_id=company_id,
            worker_id=worker_id,
            tags=list(metadata.get("tags") or []),
            expected_criteria_profile=metadata.get("expected_criteria_profile"),
            inspection=InspectionPlaceholderV1(),  # default not_inspected
            metadata={k: v for k, v in (metadata.get("metadata") or {}).items()} if isinstance(metadata.get("metadata"), dict) else {},
        )

        docs[file_ref] = entry
        self._write_index(docs)
        return file_ref

    def copy_to_tmp(self, file_ref: str) -> Path:
        """
        Copia efímera del documento a data/tmp/uploads/.
        No toca el original.
        """
        entry = self.validate(file_ref)
        src = self._safe_resolve_repo_path(entry.path)
        self.cfg.tmp_uploads_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix="upload_", suffix=Path(entry.path).suffix, dir=str(self.cfg.tmp_uploads_dir))
        os.close(fd)
        dst = Path(tmp_name).resolve()
        shutil.copy2(src, dst)
        return dst


