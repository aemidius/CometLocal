"""
Modelos para coordinación CAE v1.6.

Define los modelos para snapshot de pendientes de plataforma y coordinación.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, field_serializer


class CoordinationScopeV1(BaseModel):
    """Scope para coordinación con plataforma."""
    
    platform_key: str = "egestiona"  # Por ahora solo eGestiona
    company_key: Optional[str] = None
    person_key: Optional[str] = None
    type_ids: Optional[List[str]] = None  # Filtro opcional por tipos
    period_keys: Optional[List[str]] = None  # Filtro opcional por periodos
    coordination_label: Optional[str] = None  # ej: "Kern"


class PlatformPendingItemV1(BaseModel):
    """Item pendiente de la plataforma."""
    
    platform_item_id: Optional[str] = None  # ID si existe en la plataforma
    type_id: Optional[str] = None  # Si se puede mapear exactamente
    platform_type_label: Optional[str] = None  # Label del tipo en la plataforma
    type_alias_candidates: Optional[List[str]] = None  # Candidatos de alias para matching
    company_key: Optional[str] = None
    person_key: Optional[str] = None
    period_key: Optional[str] = None  # Si existe
    raw_label: Optional[str] = None  # Label crudo para auditoría
    raw_metadata: Optional[dict] = None  # Metadatos crudos adicionales
    status: Literal["PENDING", "UNKNOWN"] = "PENDING"


class CoordinationSnapshotV1(BaseModel):
    """Snapshot de pendientes de plataforma."""
    
    snapshot_id: str  # CAESNAP-YYYYMMDD-HHMMSS-<id>
    created_at: datetime
    scope: CoordinationScopeV1
    platform: dict  # { label, client_code } (sin secretos)
    pending_items: List[PlatformPendingItemV1]
    evidence_path: str  # Ruta al JSON del snapshot
    
    @field_serializer('created_at')
    def serialize_datetime(self, dt: datetime) -> str:
        """Serializa datetime a ISO string."""
        return dt.isoformat()


class SnapshotSelectionRequestV1(BaseModel):
    """Request para generar plan desde selección de snapshot."""
    
    snapshot_id: str
    selected: List[dict]  # [{ "pending_index": 0, "suggested_doc_id": "..." }]
    scope: "CAEScopeContextV1"  # type: ignore  # Forward reference



