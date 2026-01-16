"""
Modelos para la planificación de envíos CAE v1.1.

Define los modelos de datos para el scope, decisiones y planes de envío.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Optional, List, Literal
from pydantic import BaseModel, field_validator, field_serializer


class CAEScopeContextV1(BaseModel):
    """Contexto de scope para planificación de envío CAE."""
    
    platform_key: str  # ej: "egestiona"
    type_ids: List[str]  # Lista de type_ids (vacío = todos los visibles si el frontend lo decide)
    company_key: Optional[str] = None
    person_key: Optional[str] = None
    period_keys: Optional[List[str]] = None  # ej: ["2025-12", "2026-01"]
    mode: Literal["READ_ONLY", "PREPARE_WRITE", "WRITE"] = "READ_ONLY"
    
    @field_validator('type_ids')
    @classmethod
    def validate_type_ids(cls, v: List[str]) -> List[str]:
        """Valida que type_ids sea una lista (puede estar vacía)."""
        if not isinstance(v, list):
            return []
        return v
    
    @field_validator('period_keys')
    @classmethod
    def validate_period_keys(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Valida que period_keys sea una lista o None."""
        if v is None:
            return None
        if not isinstance(v, list):
            return []
        return v


CAEPlanDecisionV1 = Literal["READY", "NEEDS_CONFIRMATION", "BLOCKED"]
"""Decisión del planificador."""


class CAESubmissionItemV1(BaseModel):
    """Item individual en un plan de envío."""
    
    kind: Literal["MISSING_PERIOD", "DOC_INSTANCE"]
    type_id: str
    scope: Literal["company", "worker"]
    company_key: Optional[str] = None
    person_key: Optional[str] = None
    period_key: Optional[str] = None
    suggested_doc_id: Optional[str] = None
    resolved_dates: Optional[dict] = None  # {"issued_at": "2025-12-01", "valid_from": "2025-12-01", "valid_to": "2025-12-31"}
    status: Literal["PLANNED", "NEEDS_CONFIRMATION", "BLOCKED"] = "PLANNED"
    reason: str = ""


class CAESubmissionPlanV1(BaseModel):
    """Plan de envío CAE completo."""
    
    plan_id: str  # CAEPLAN-YYYYMMDD-HHMMSS-<shortid>
    created_at: datetime
    scope: CAEScopeContextV1
    decision: CAEPlanDecisionV1
    reasons: List[str]
    items: List[CAESubmissionItemV1]
    summary: dict  # {"pending_items": 5, "docs_candidates": 3, ...}
    executor_hint: Optional[str] = None  # ej: "egestiona_upload_v1" si platform_key=="egestiona"
    
    @field_serializer('created_at')
    def serialize_datetime(self, value: datetime, _info) -> str:
        return value.isoformat()

