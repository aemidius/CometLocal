"""
SPRINT C2.20A: API endpoints para Decision Presets.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, Dict, Any
from pydantic import BaseModel

from backend.shared.decision_preset import DecisionPresetV1, DecisionPresetScope, DecisionPresetDefaults
from backend.shared.decision_pack import ManualDecisionAction
from backend.shared.decision_preset_store import DecisionPresetStore

router = APIRouter(prefix="/api/presets", tags=["presets"])

store = DecisionPresetStore()


class CreatePresetRequest(BaseModel):
    """Request para crear/actualizar un preset."""
    name: str
    scope: Dict[str, Any]  # DecisionPresetScope como dict
    action: str  # ManualDecisionAction como string
    defaults: Optional[Dict[str, Any]] = None  # DecisionPresetDefaults como dict


@router.get("/decision_presets")
async def list_presets(
    type_id: Optional[str] = Query(None, description="Filtrar por type_id"),
    subject_key: Optional[str] = Query(None, description="Filtrar por subject_key"),
    period_key: Optional[str] = Query(None, description="Filtrar por period_key"),
    platform: Optional[str] = Query(None, description="Filtrar por platform"),
    include_disabled: bool = Query(False, description="Incluir presets desactivados"),
) -> dict:
    """
    Lista presets con filtros opcionales.
    
    Response:
    {
        "presets": [...],
        "total": N
    }
    """
    presets = store.list_presets(
        type_id=type_id,
        subject_key=subject_key,
        period_key=period_key,
        platform=platform,
        include_disabled=include_disabled,
    )
    
    return {
        "presets": [p.model_dump(mode="json") for p in presets],
        "total": len(presets),
    }


@router.post("/decision_presets")
async def create_preset(request: CreatePresetRequest) -> dict:
    """
    Crea o actualiza un preset.
    
    Body:
    {
        "name": "Skip T104",
        "scope": {
            "platform": "egestiona",
            "type_id": "T104_AUTONOMOS_RECEIPT",
            "subject_key": null,
            "period_key": null
        },
        "action": "SKIP",
        "defaults": {
            "reason": "No disponible"
        }
    }
    
    Response:
    {
        "preset_id": "...",
        "preset": {...}
    }
    """
    # Validar action
    try:
        action = ManualDecisionAction(request.action)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}. Must be SKIP, FORCE_UPLOAD, or MARK_AS_MATCH")
    
    # Construir scope
    try:
        scope = DecisionPresetScope(**request.scope)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid scope: {e}")
    
    # Construir defaults
    defaults = DecisionPresetDefaults()
    if request.defaults:
        defaults = DecisionPresetDefaults(**request.defaults)
    
    # Crear preset
    preset = DecisionPresetV1.create(
        name=request.name,
        scope=scope,
        action=action,
        defaults=defaults,
    )
    
    # Guardar
    preset_id = store.upsert_preset(preset)
    
    return {
        "preset_id": preset_id,
        "preset": preset.model_dump(mode="json"),
    }


@router.post("/decision_presets/{preset_id}/disable")
async def disable_preset(preset_id: str) -> dict:
    """
    Desactiva un preset.
    
    Response:
    {
        "preset_id": "...",
        "disabled": true
    }
    """
    success = store.disable_preset(preset_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Preset {preset_id} not found")
    
    return {
        "preset_id": preset_id,
        "disabled": True,
    }
