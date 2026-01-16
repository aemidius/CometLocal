from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4
from datetime import datetime

from backend.repository.data_bootstrap_v1 import ensure_data_layout
from backend.repository.config_store_v1 import _atomic_write_json
from backend.shared.document_repository_v1 import SubmissionRecordV1


class SubmissionHistoryStoreV1:
    """
    Store local (JSON) para historial de envíos.
    - history/submissions.json: lista de registros
    """

    def __init__(self, *, base_dir: str | Path = "data"):
        self.base_dir = ensure_data_layout(base_dir=base_dir)
        self.repo_dir = (Path(self.base_dir) / "repository").resolve()
        self.history_dir = self.repo_dir / "history"
        
        # Asegurar estructura de directorios
        self.history_dir.mkdir(parents=True, exist_ok=True)
        
        self.submissions_path = self.history_dir / "submissions.json"
        
        # Seed inicial si no existe
        self._ensure_seed()

    def _ensure_seed(self) -> None:
        """Crea el seed inicial (lista vacía) si no existe."""
        if not self.submissions_path.exists():
            self._write_submissions([])

    def _read_json(self, path: Path) -> dict:
        """Lee JSON desde un path."""
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: dict) -> None:
        """Escribe JSON de forma atómica."""
        _atomic_write_json(path, payload)

    def _read_submissions(self) -> Dict[str, SubmissionRecordV1]:
        """Lee todos los registros desde submissions.json."""
        raw = self._read_json(self.submissions_path)
        submissions_list = raw.get("submissions", [])
        return {r.record_id: r for r in [SubmissionRecordV1.model_validate(item) for item in submissions_list]}

    def _write_submissions(self, submissions: List[SubmissionRecordV1]) -> None:
        """Escribe la lista de registros a submissions.json."""
        payload = {
            "schema_version": "v1",
            "submissions": [s.model_dump(mode="json") for s in submissions]
        }
        self._write_json(self.submissions_path, payload)

    def list_records(
        self,
        platform_key: Optional[str] = None,
        coord_label: Optional[str] = None,
        company_key: Optional[str] = None,
        person_key: Optional[str] = None,
        doc_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[SubmissionRecordV1]:
        """
        Lista registros con filtros opcionales.
        Retorna ordenados por created_at descendente (más recientes primero).
        """
        records = list(self._read_submissions().values())
        
        # Aplicar filtros
        if platform_key:
            records = [r for r in records if r.platform_key == platform_key]
        if coord_label:
            records = [r for r in records if r.coord_label == coord_label]
        if company_key:
            records = [r for r in records if r.company_key == company_key]
        if person_key:
            records = [r for r in records if r.person_key == person_key]
        if doc_id:
            records = [r for r in records if r.doc_id == doc_id]
        if action:
            records = [r for r in records if r.action == action]
        
        # Ordenar por created_at descendente
        records.sort(key=lambda r: r.created_at, reverse=True)
        
        # Aplicar límite
        if limit:
            records = records[:limit]
        
        return records

    def get_record(self, record_id: str) -> Optional[SubmissionRecordV1]:
        """Obtiene un registro por ID."""
        return self._read_submissions().get(record_id)

    def find_by_fingerprint(
        self,
        fingerprint: str,
        action: Optional[str] = None,
    ) -> Optional[SubmissionRecordV1]:
        """
        Busca un registro por fingerprint.
        Si action está especificado, filtra por esa acción.
        Retorna el más reciente si hay múltiples.
        """
        records = list(self._read_submissions().values())
        matches = [r for r in records if r.pending_fingerprint == fingerprint]
        
        if action:
            matches = [r for r in matches if r.action == action]
        
        if not matches:
            return None
        
        # Retornar el más reciente
        matches.sort(key=lambda r: r.created_at, reverse=True)
        return matches[0]

    def create_record(self, record: SubmissionRecordV1) -> SubmissionRecordV1:
        """Crea un nuevo registro."""
        records = self._read_submissions()
        if record.record_id in records:
            raise ValueError(f"Record with ID {record.record_id} already exists")
        records[record.record_id] = record
        self._write_submissions(list(records.values()))
        return record

    def update_record(self, record_id: str, record: SubmissionRecordV1) -> SubmissionRecordV1:
        """Actualiza un registro existente."""
        records = self._read_submissions()
        if record_id not in records:
            raise ValueError(f"Record with ID {record_id} not found")
        if record_id != record.record_id:
            raise ValueError("Record ID in path and body must match")
        records[record_id] = record
        self._write_submissions(list(records.values()))
        return record

    def delete_record(self, record_id: str) -> None:
        """Elimina un registro."""
        records = self._read_submissions()
        if record_id not in records:
            raise ValueError(f"Record with ID {record_id} not found")
        del records[record_id]
        self._write_submissions(list(records.values()))




