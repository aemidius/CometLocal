from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from backend.repository.data_bootstrap_v1 import ensure_data_layout
from backend.repository.config_store_v1 import _atomic_write_json
from backend.shared.document_repository_v1 import (
    DocumentTypeV1,
    DocumentInstanceV1,
    SubmissionRuleV1,
    ValidityOverrideV1,
)


class DocumentRepositoryStoreV1:
    """
    Store local (JSON) para el repositorio documental.
    - types/types.json: tipos de documento
    - meta/<doc_id>.json: metadatos sidecar por documento
    - rules/submission_rules.json: reglas de envío (placeholder)
    - overrides/overrides.json: overrides de validez (placeholder)
    """

    def __init__(self, *, base_dir: str | Path = "data"):
        self.base_dir = ensure_data_layout(base_dir=base_dir)
        self.repo_dir = (Path(self.base_dir) / "repository").resolve()
        self.types_dir = self.repo_dir / "types"
        self.docs_dir = self.repo_dir / "docs"
        self.meta_dir = self.repo_dir / "meta"
        self.rules_dir = self.repo_dir / "rules"
        self.overrides_dir = self.repo_dir / "overrides"
        
        # Asegurar estructura de directorios
        self.types_dir.mkdir(parents=True, exist_ok=True)
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir.mkdir(parents=True, exist_ok=True)
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        self.overrides_dir.mkdir(parents=True, exist_ok=True)
        
        self.types_path = self.types_dir / "types.json"
        self.rules_path = self.rules_dir / "submission_rules.json"
        self.overrides_path = self.overrides_dir / "overrides.json"
        
        # Seed inicial si no existe
        self._ensure_seed()

    def _ensure_seed(self) -> None:
        """Crea el seed inicial T104_AUTONOMOS_RECEIPT si no existe types.json."""
        if not self.types_path.exists():
            from backend.shared.document_repository_v1 import (
                ValidityPolicyV1,
                MonthlyValidityConfigV1,
            )
            seed_type = DocumentTypeV1(
                type_id="T104_AUTONOMOS_RECEIPT",
                name="Recibo autónomos",
                description="Recibo de autónomos mensual",
                scope="worker",
                validity_policy=ValidityPolicyV1(
                    mode="monthly",
                    basis="name_date",
                    monthly=MonthlyValidityConfigV1(
                        month_source="name_date",
                        valid_from="period_start",
                        valid_to="period_end",
                        grace_days=0
                    )
                ),
                required_fields=["valid_from", "valid_to"],
                active=True
            )
            self._write_types([seed_type])
        
        # Seed placeholder para rules y overrides
        if not self.rules_path.exists():
            self._write_json(self.rules_path, {"schema_version": "v1", "rules": []})
        
        if not self.overrides_path.exists():
            self._write_json(self.overrides_path, {"schema_version": "v1", "overrides": []})

    def _read_json(self, path: Path) -> dict:
        """Lee JSON desde un path."""
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, payload: dict) -> None:
        """Escribe JSON de forma atómica."""
        _atomic_write_json(path, payload)

    # ========== TIPOS DE DOCUMENTO ==========

    def _read_types(self) -> Dict[str, DocumentTypeV1]:
        """Lee todos los tipos desde types.json."""
        raw = self._read_json(self.types_path)
        types_list = raw.get("types", []) if isinstance(raw, dict) else []
        if not isinstance(types_list, list):
            types_list = []
        
        result: Dict[str, DocumentTypeV1] = {}
        for item in types_list:
            try:
                doc_type = DocumentTypeV1.model_validate(item)
                result[doc_type.type_id] = doc_type
            except Exception:
                continue
        return result

    def _write_types(self, types: List[DocumentTypeV1]) -> None:
        """Escribe tipos a types.json."""
        payload = {
            "schema_version": "v1",
            "types": [t.model_dump(mode="json") for t in types]
        }
        self._write_json(self.types_path, payload)

    def list_types(self, include_inactive: bool = False) -> List[DocumentTypeV1]:
        """Lista todos los tipos (opcionalmente incluyendo inactivos)."""
        types_dict = self._read_types()
        result = list(types_dict.values())
        if not include_inactive:
            result = [t for t in result if t.active]
        return sorted(result, key=lambda t: t.name)

    def get_type(self, type_id: str) -> Optional[DocumentTypeV1]:
        """Obtiene un tipo por ID."""
        types_dict = self._read_types()
        return types_dict.get(type_id)

    def create_type(self, doc_type: DocumentTypeV1) -> DocumentTypeV1:
        """Crea un nuevo tipo."""
        types_dict = self._read_types()
        if doc_type.type_id in types_dict:
            raise ValueError(f"Type {doc_type.type_id} already exists")
        types_dict[doc_type.type_id] = doc_type
        self._write_types(list(types_dict.values()))
        return doc_type

    def update_type(self, type_id: str, doc_type: DocumentTypeV1) -> DocumentTypeV1:
        """Actualiza un tipo existente."""
        types_dict = self._read_types()
        if type_id not in types_dict:
            raise ValueError(f"Type {type_id} not found")
        if doc_type.type_id != type_id:
            raise ValueError(f"Cannot change type_id from {type_id} to {doc_type.type_id}")
        types_dict[type_id] = doc_type
        self._write_types(list(types_dict.values()))
        return doc_type

    def delete_type(self, type_id: str) -> None:
        """Elimina un tipo (hard delete)."""
        types_dict = self._read_types()
        if type_id not in types_dict:
            raise ValueError(f"Type {type_id} not found")
        del types_dict[type_id]
        self._write_types(list(types_dict.values()))

    def duplicate_type(self, type_id: str, new_type_id: str, new_name: Optional[str] = None) -> DocumentTypeV1:
        """Duplica un tipo con nuevo ID."""
        original = self.get_type(type_id)
        if not original:
            raise ValueError(f"Type {type_id} not found")
        
        types_dict = self._read_types()
        if new_type_id in types_dict:
            raise ValueError(f"Type {new_type_id} already exists")
        
        new_type = DocumentTypeV1(
            **original.model_dump(),
            type_id=new_type_id,
            name=new_name or f"{original.name} (copia)"
        )
        types_dict[new_type_id] = new_type
        self._write_types(list(types_dict.values()))
        return new_type

    # ========== DOCUMENTOS ==========

    def _get_doc_meta_path(self, doc_id: str) -> Path:
        """Obtiene el path del sidecar JSON de un documento."""
        return self.meta_dir / f"{doc_id}.json"

    def _get_doc_pdf_path(self, doc_id: str) -> Path:
        """Obtiene el path del PDF de un documento."""
        return self.docs_dir / f"{doc_id}.pdf"

    def get_document(self, doc_id: str) -> Optional[DocumentInstanceV1]:
        """Obtiene un documento por ID."""
        meta_path = self._get_doc_meta_path(doc_id)
        if not meta_path.exists():
            return None
        raw = self._read_json(meta_path)
        return DocumentInstanceV1.model_validate(raw)

    def list_documents(
        self,
        type_id: Optional[str] = None,
        scope: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[DocumentInstanceV1]:
        """Lista todos los documentos (con filtros opcionales)."""
        result: List[DocumentInstanceV1] = []
        for meta_path in self.meta_dir.glob("*.json"):
            try:
                raw = self._read_json(meta_path)
                doc = DocumentInstanceV1.model_validate(raw)
                
                if type_id and doc.type_id != type_id:
                    continue
                if scope and doc.scope != scope:
                    continue
                if status and doc.status != status:
                    continue
                
                result.append(doc)
            except Exception:
                continue
        
        return sorted(result, key=lambda d: d.created_at, reverse=True)

    def save_document(self, doc: DocumentInstanceV1) -> DocumentInstanceV1:
        """Guarda un documento (crea o actualiza el sidecar JSON)."""
        meta_path = self._get_doc_meta_path(doc.doc_id)
        payload = doc.model_dump(mode="json")
        self._write_json(meta_path, payload)
        return doc

    def compute_file_hash(self, file_path: Path) -> str:
        """Calcula SHA256 de un archivo."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def store_pdf(self, source_path: Path, doc_id: str) -> Path:
        """Copia un PDF al repositorio con nombre <doc_id>.pdf."""
        target_path = self._get_doc_pdf_path(doc_id)
        import shutil
        shutil.copy2(source_path, target_path)
        return target_path

    # ========== REGLAS Y OVERRIDES (PLACEHOLDER) ==========

    def list_submission_rules(self) -> List[SubmissionRuleV1]:
        """Lista reglas de envío (placeholder)."""
        raw = self._read_json(self.rules_path)
        rules_list = raw.get("rules", []) if isinstance(raw, dict) else []
        result: List[SubmissionRuleV1] = []
        for item in rules_list:
            try:
                rule = SubmissionRuleV1.model_validate(item)
                result.append(rule)
            except Exception:
                continue
        return result

    def list_validity_overrides(self) -> List[ValidityOverrideV1]:
        """Lista overrides de validez (placeholder)."""
        raw = self._read_json(self.overrides_path)
        overrides_list = raw.get("overrides", []) if isinstance(raw, dict) else []
        result: List[ValidityOverrideV1] = []
        for item in overrides_list:
            try:
                override = ValidityOverrideV1.model_validate(item)
                result.append(override)
            except Exception:
                continue
        return result

