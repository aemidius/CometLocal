"""
SPRINT C2.36: API endpoints para sugerencias de tipos (read-only).
"""

from __future__ import annotations

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from backend.repository.type_suggestions_v1 import suggest_types, TypeSuggestionV1
from backend.repository.document_matcher_v1 import PendingItemV1
from backend.shared.tenant_context import get_tenant_from_request
from backend.config import DATA_DIR


router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])


@router.get("/types")
async def get_type_suggestions(
    pending: Dict[str, Any],  # PendingItemV1 serializado como query param (JSON string)
    context: Dict[str, Any],  # Contexto como query param (JSON string)
    limit: int = Query(3, ge=1, le=10),
    request: Request = None
) -> Dict[str, Any]:
    """
    SPRINT C2.36: Obtiene sugerencias de tipos existentes para un pending item.
    
    Read-only: No escribe nada, solo sugiere tipos basados en scoring determinista.
    
    Args:
        pending: PendingItemV1 serializado como JSON string en query param
        context: Contexto (company_key, person_key, platform_key) como JSON string
        limit: Número máximo de sugerencias (default: 3, max: 10)
    
    Returns:
        {
            "suggestions": [
                {
                    "type_id": "...",
                    "type_name": "...",
                    "score": 0.85,
                    "reasons": ["...", "..."]
                },
                ...
            ]
        }
    """
    # Validar contexto humano (aunque sea read-only, queremos contexto válido)
    if request:
        tenant_ctx = get_tenant_from_request(request)
    
    # Parsear pending (debe venir como JSON string en query param)
    # Nota: FastAPI no parsea automáticamente JSON en query params,
    # así que esperamos que venga como dict en el body o como query param parseado
    # Por ahora, asumimos que viene como dict desde el frontend
    
    try:
        # Convertir pending dict a PendingItemV1
        if isinstance(pending, dict):
            # Parsear fechas si vienen como strings ISO
            fecha_inicio = pending.get("fecha_inicio")
            if isinstance(fecha_inicio, str):
                try:
                    from datetime import datetime
                    fecha_inicio = datetime.fromisoformat(fecha_inicio.replace('Z', '+00:00')).date()
                except:
                    fecha_inicio = None
            
            fecha_fin = pending.get("fecha_fin")
            if isinstance(fecha_fin, str):
                try:
                    from datetime import datetime
                    fecha_fin = datetime.fromisoformat(fecha_fin.replace('Z', '+00:00')).date()
                except:
                    fecha_fin = None
            
            pending_obj = PendingItemV1(
                tipo_doc=pending.get("tipo_doc"),
                elemento=pending.get("elemento"),
                empresa=pending.get("empresa"),
                trabajador=pending.get("trabajador"),
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                raw_data=pending.get("raw_data", {})
            )
        else:
            raise ValueError("pending must be a dict")
        
        # Obtener sugerencias
        suggestions = suggest_types(
            pending=pending_obj,
            context=context if isinstance(context, dict) else {},
            limit=limit,
            base_dir=DATA_DIR
        )
        
        return {
            "suggestions": [s.to_dict() for s in suggestions]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating suggestions: {str(e)}")


# Alternativa: POST para aceptar JSON en body
class GetSuggestionsRequest(BaseModel):
    """Request para obtener sugerencias."""
    pending: Dict[str, Any]
    context: Dict[str, Any]
    limit: int = 3


@router.post("/types")
async def get_type_suggestions_post(
    request: GetSuggestionsRequest,
    http_request: Request = None
) -> Dict[str, Any]:
    """
    SPRINT C2.36: Obtiene sugerencias de tipos existentes (POST version).
    
    Más conveniente para enviar JSON complejo en el body.
    """
    if http_request:
        tenant_ctx = get_tenant_from_request(http_request)
    
    try:
        # Convertir pending dict a PendingItemV1
        # Parsear fechas si vienen como strings ISO
        fecha_inicio = request.pending.get("fecha_inicio")
        if isinstance(fecha_inicio, str):
            try:
                from datetime import datetime
                fecha_inicio = datetime.fromisoformat(fecha_inicio.replace('Z', '+00:00')).date()
            except:
                fecha_inicio = None
        
        fecha_fin = request.pending.get("fecha_fin")
        if isinstance(fecha_fin, str):
            try:
                from datetime import datetime
                fecha_fin = datetime.fromisoformat(fecha_fin.replace('Z', '+00:00')).date()
            except:
                fecha_fin = None
        
        pending_obj = PendingItemV1(
            tipo_doc=request.pending.get("tipo_doc"),
            elemento=request.pending.get("elemento"),
            empresa=request.pending.get("empresa"),
            trabajador=request.pending.get("trabajador"),
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            raw_data=request.pending.get("raw_data", {})
        )
        
        # Obtener sugerencias
        suggestions = suggest_types(
            pending=pending_obj,
            context=request.context,
            limit=request.limit,
            base_dir=DATA_DIR
        )
        
        return {
            "suggestions": [s.to_dict() for s in suggestions]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating suggestions: {str(e)}")
