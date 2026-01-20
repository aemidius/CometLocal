"""
SPRINT C2.36: API endpoints para preview de impacto (read-only).

Endpoints que permiten previsualizar el impacto de acciones asistidas
sin aplicar cambios.
"""

from __future__ import annotations

from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.repository.impact_preview_v1 import (
    preview_assign_alias,
    preview_create_type,
    ImpactPreviewV1
)
from backend.repository.document_matcher_v1 import PendingItemV1
from backend.shared.document_repository_v1 import DocumentTypeV1
from backend.shared.context_guardrails import validate_write_request_context
from backend.shared.tenant_context import get_tenant_from_request
from backend.config import DATA_DIR


router = APIRouter(prefix="/api/preview", tags=["preview"])


class PreviewAssignAliasRequest(BaseModel):
    """Request para preview de asignar alias."""
    pending: Dict[str, Any]  # PendingItemV1 serializado
    type_id: str
    alias: str
    platform_key: str = "egestiona"
    context: Dict[str, Any]  # company_key, person_key, etc.


class PreviewCreateTypeRequest(BaseModel):
    """Request para preview de crear tipo."""
    pending: Dict[str, Any]  # PendingItemV1 serializado
    draft_type: Dict[str, Any]  # DocumentTypeV1 serializado
    platform_key: str = "egestiona"
    context: Dict[str, Any]  # company_key, person_key, etc.


@router.post("/assign-alias")
async def preview_assign_alias_endpoint(
    request: PreviewAssignAliasRequest,
    http_request: Request = None
) -> Dict[str, Any]:
    """
    SPRINT C2.36: Preview del impacto de asignar un alias a un tipo existente.
    
    Read-only: No escribe nada, solo calcula el impacto esperado.
    """
    # Validar contexto humano (aunque sea read-only, queremos contexto válido)
    if http_request:
        tenant_ctx = get_tenant_from_request(http_request)
        # No requerimos validación de WRITE para preview, pero usamos el contexto
    
    # Convertir pending dict a PendingItemV1
    pending_dict = request.pending
    
    # Parsear fechas si vienen como strings ISO
    fecha_inicio = pending_dict.get("fecha_inicio")
    if isinstance(fecha_inicio, str):
        try:
            from datetime import datetime
            fecha_inicio = datetime.fromisoformat(fecha_inicio.replace('Z', '+00:00')).date()
        except:
            fecha_inicio = None
    
    fecha_fin = pending_dict.get("fecha_fin")
    if isinstance(fecha_fin, str):
        try:
            from datetime import datetime
            fecha_fin = datetime.fromisoformat(fecha_fin.replace('Z', '+00:00')).date()
        except:
            fecha_fin = None
    
    pending = PendingItemV1(
        tipo_doc=pending_dict.get("tipo_doc"),
        elemento=pending_dict.get("elemento"),
        empresa=pending_dict.get("empresa"),
        trabajador=pending_dict.get("trabajador"),
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        raw_data=pending_dict.get("raw_data", {})
    )
    
    try:
        preview = preview_assign_alias(
            pending=pending,
            type_id=request.type_id,
            alias=request.alias,
            platform_key=request.platform_key,
            context=request.context,
            base_dir=DATA_DIR
        )
        return preview.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating preview: {str(e)}")


@router.post("/create-type")
async def preview_create_type_endpoint(
    request: PreviewCreateTypeRequest,
    http_request: Request = None
) -> Dict[str, Any]:
    """
    SPRINT C2.36: Preview del impacto de crear un nuevo tipo de documento.
    
    Read-only: No escribe nada, solo calcula el impacto esperado.
    """
    # Validar contexto humano (aunque sea read-only, queremos contexto válido)
    if http_request:
        tenant_ctx = get_tenant_from_request(http_request)
        # No requerimos validación de WRITE para preview, pero usamos el contexto
    
    # Convertir pending dict a PendingItemV1
    pending_dict = request.pending
    
    # Parsear fechas si vienen como strings ISO
    fecha_inicio = pending_dict.get("fecha_inicio")
    if isinstance(fecha_inicio, str):
        try:
            from datetime import datetime
            fecha_inicio = datetime.fromisoformat(fecha_inicio.replace('Z', '+00:00')).date()
        except:
            fecha_inicio = None
    
    fecha_fin = pending_dict.get("fecha_fin")
    if isinstance(fecha_fin, str):
        try:
            from datetime import datetime
            fecha_fin = datetime.fromisoformat(fecha_fin.replace('Z', '+00:00')).date()
        except:
            fecha_fin = None
    
    pending = PendingItemV1(
        tipo_doc=pending_dict.get("tipo_doc"),
        elemento=pending_dict.get("elemento"),
        empresa=pending_dict.get("empresa"),
        trabajador=pending_dict.get("trabajador"),
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        raw_data=pending_dict.get("raw_data", {})
    )
    
    # Convertir draft_type dict a DocumentTypeV1
    try:
        draft_type = DocumentTypeV1(**request.draft_type)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid draft_type: {str(e)}")
    
    try:
        preview = preview_create_type(
            pending=pending,
            draft_type=draft_type,
            platform_key=request.platform_key,
            context=request.context,
            base_dir=DATA_DIR
        )
        return preview.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating preview: {str(e)}")
