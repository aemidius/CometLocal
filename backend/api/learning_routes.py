"""
SPRINT C2.19A: API endpoints para Learning Store (hints de aprendizaje).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional, List
from pydantic import BaseModel

from backend.shared.learning_store import LearningStore, LearnedHintV1, HintStrength
from backend.shared.tenant_context import get_tenant_from_request

router = APIRouter(prefix="/api/learning", tags=["learning"])


@router.get("/hints")
async def list_hints(
    type_id: Optional[str] = Query(None, description="Filtrar por type_id"),
    subject_key: Optional[str] = Query(None, description="Filtrar por subject_key"),
    period_key: Optional[str] = Query(None, description="Filtrar por period_key"),
    platform: Optional[str] = Query(None, description="Filtrar por platform (ej: egestiona)"),
    strength: Optional[str] = Query(None, description="Filtrar por strength (EXACT/SOFT)"),
    include_disabled: bool = Query(False, description="Incluir hints desactivados"),
    limit: int = Query(200, description="Límite de resultados", ge=1, le=1000),
    request: Request = None,
) -> dict:
    """
    Lista hints con filtros opcionales.
    
    Response:
    {
        "hints": [...],
        "total": N
    }
    """
    # SPRINT C2.22B: Extraer tenant_id del request
    tenant_ctx = get_tenant_from_request(request)
    store = LearningStore(tenant_id=tenant_ctx.tenant_id)
    
    strength_enum = None
    if strength:
        try:
            strength_enum = HintStrength(strength)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid strength: {strength}. Must be EXACT or SOFT")
    
    hints = store.list_hints(
        plan_id=None,
        decision_pack_id=None,
        strength=strength_enum,
        include_disabled=include_disabled,
    )
    
    # Aplicar filtros adicionales si se proporcionan
    filtered = []
    for hint in hints:
        if type_id and hint.learned_mapping.get("type_id_expected") != type_id:
            continue
        if subject_key and hint.conditions.get("subject_key") != subject_key:
            continue
        if period_key and hint.conditions.get("period_key") != period_key:
            continue
        # Platform no se almacena en el hint actualmente, pero se puede filtrar por source
        # Por ahora, si se proporciona platform, solo incluimos hints de decision_pack (egestiona)
        if platform and hint.source != "decision_pack":
            continue
        filtered.append(hint)
    
    # Aplicar límite
    limited = filtered[:limit]
    
    return {
        "hints": [h.model_dump(mode="json") for h in limited],
        "total": len(filtered),
        "returned": len(limited),
    }


class DisableHintRequest(BaseModel):
    reason: Optional[str] = None


@router.post("/hints/{hint_id}/disable")
async def disable_hint(hint_id: str, body: Optional[DisableHintRequest] = None, request: Request = None) -> dict:
    """
    Desactiva un hint.
    
    Body opcional:
    {
        "reason": "Razón para desactivar"
    }
    
    Response:
    {
        "hint_id": "...",
        "disabled": true
    }
    """
    # SPRINT C2.22B: Extraer tenant_id del request
    tenant_ctx = get_tenant_from_request(request)
    store = LearningStore(tenant_id=tenant_ctx.tenant_id)
    
    reason = body.reason if body else None
    success = store.disable_hint(hint_id, reason=reason)
    if not success:
        raise HTTPException(status_code=404, detail=f"Hint {hint_id} not found")
    
    return {
        "hint_id": hint_id,
        "disabled": True,
    }
