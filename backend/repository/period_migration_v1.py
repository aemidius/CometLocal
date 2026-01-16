"""
Migración/backfill de period_key para documentos existentes.

Para documentos con tipos periódicos (mensual/anual), infiere y asigna period_key
basándose en metadatos disponibles (issue_date, name_date, filename).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any

from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.repository.period_planner_v1 import PeriodPlannerV1
from backend.shared.document_repository_v1 import PeriodKindV1


class PeriodMigrationV1:
    """Migración de period_key para documentos existentes."""
    
    def __init__(self, store: DocumentRepositoryStoreV1):
        self.store = store
        self.planner = PeriodPlannerV1(store)
    
    def migrate_document(self, doc: "DocumentInstanceV1", dry_run: bool = False) -> Dict[str, Any]:
        """
        Migra un documento: infiere y asigna period_key si es posible.
        
        Returns:
            Dict con:
            - migrated: bool
            - period_key: str o None
            - needs_period: bool (si no se pudo inferir pero debería tenerlo)
            - reason: str
        """
        doc_type = self.store.get_type(doc.type_id)
        if not doc_type:
            return {
                "migrated": False,
                "period_key": None,
                "needs_period": False,
                "reason": f"Type {doc.type_id} not found"
            }
        
        period_kind = self.planner.get_period_kind_from_type(doc_type)
        
        # Si no es periódico, no necesita period_key
        if period_kind == PeriodKindV1.NONE:
            return {
                "migrated": False,
                "period_key": None,
                "needs_period": False,
                "reason": "Type is not periodic"
            }
        
        # Si ya tiene period_key, no hacer nada
        if doc.period_key:
            return {
                "migrated": False,
                "period_key": doc.period_key,
                "needs_period": False,
                "reason": "Already has period_key"
            }
        
        # Intentar inferir period_key
        period_key = self.planner.infer_period_key(
            doc_type=doc_type,
            issue_date=doc.extracted.issue_date or doc.issued_at,
            name_date=doc.extracted.name_date,
            filename=doc.file_name_original,
        )
        
        if period_key:
            # Actualizar documento con period_key y period_kind
            from backend.shared.document_repository_v1 import DocumentInstanceV1
            doc_dict = doc.model_dump()
            doc_dict["period_kind"] = period_kind
            doc_dict["period_key"] = period_key
            doc_dict["needs_period"] = False
            updated_doc = DocumentInstanceV1(**doc_dict)
            if not dry_run:
                self.store.save_document(updated_doc)
            
            return {
                "migrated": True,
                "period_key": period_key,
                "needs_period": False,
                "reason": f"Inferred from metadata"
            }
        else:
            # No se pudo inferir, marcar como needs_period
            from backend.shared.document_repository_v1 import DocumentInstanceV1
            doc_dict = doc.model_dump()
            doc_dict["period_kind"] = period_kind
            doc_dict["period_key"] = None
            doc_dict["needs_period"] = True
            updated_doc = DocumentInstanceV1(**doc_dict)
            if not dry_run:
                self.store.save_document(updated_doc)
            
            return {
                "migrated": True,
                "period_key": None,
                "needs_period": True,
                "reason": "Could not infer period_key from available metadata"
            }
    
    def migrate_all(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Migra todos los documentos del repositorio.
        
        Args:
            dry_run: Si True, no guarda cambios, solo reporta
        
        Returns:
            Dict con estadísticas de migración
        """
        all_docs = self.store.list_documents()
        
        stats = {
            "total": len(all_docs),
            "migrated": 0,
            "already_has_period": 0,
            "not_periodic": 0,
            "needs_period": 0,
            "errors": 0,
        }
        
        for doc in all_docs:
            try:
                result = self.migrate_document(doc, dry_run=dry_run)
                
                if result["migrated"]:
                    stats["migrated"] += 1
                    if result["needs_period"]:
                        stats["needs_period"] += 1
                elif result["period_key"]:
                    stats["already_has_period"] += 1
                else:
                    stats["not_periodic"] += 1
            except Exception as e:
                stats["errors"] += 1
                print(f"[MIGRATION] Error migrating doc {doc.doc_id}: {e}")
        
        return stats

