"""
Endpoints para auto-upload con plan congelado.

SPRINT C2.17: Separación estricta PLAN → DECISION → EXECUTION
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from pathlib import Path
import json

from backend.config import DATA_DIR

router = APIRouter(tags=["auto_upload"])


class PlanRequest(BaseModel):
    """Request para crear plan."""
    coord: str = "Kern"
    company_key: str
    person_key: Optional[str] = None
    limit: int = 200
    only_target: bool = True
    max_items: int = 200
    max_pages: int = 10


class ExecuteRequest(BaseModel):
    """Request para ejecutar plan."""
    plan_id: str
    decision_pack_id: Optional[str] = Field(
        None,
        description="ID del Decision Pack con overrides manuales (SPRINT C2.18B)"
    )
    max_uploads: int = 5
    stop_on_first_error: bool = True
    continue_on_error: bool = False
    rate_limit_seconds: float = 1.5


@router.post("/runs/auto_upload/plan")
async def create_auto_upload_plan(
    request: PlanRequest,
    http_request: Request = None,
):
    """
    SPRINT C2.17: Crea plan de auto-upload con decisiones explícitas.
    
    Reutiliza build_auto_upload_plan pero con contrato C2.17.
    
    Response:
    {
        "status": "ok",
        "plan_id": "plan_abc123...",
        "snapshot": {...},
        "decisions": [...],
        "summary": {...}
    }
    """
    # Reutilizar endpoint existente
    from backend.adapters.egestiona.flows import egestiona_build_auto_upload_plan
    
    result = await egestiona_build_auto_upload_plan(
        coord=request.coord,
        company_key=request.company_key,
        person_key=request.person_key,
        limit=request.limit,
        only_target=request.only_target,
        max_items=request.max_items,
        max_pages=request.max_pages,
        request=http_request,
    )
    
    if result.get("status") != "ok":
        raise HTTPException(status_code=400, detail=result.get("message", "Plan creation failed"))
    
    return {
        "status": "ok",
        "plan_id": result.get("plan_id"),  # SPRINT C2.17: plan_id generado
        "snapshot": result.get("snapshot", {}),
        "decisions": result.get("decisions", []),
        "summary": result.get("summary", {}),
        "diagnostics": result.get("diagnostics", {}),
    }


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str):
    """
    SPRINT C2.18B.1: Endpoint simplificado para UI de revisión.
    
    Devuelve plan con estructura optimizada para UI.
    
    Response:
    {
        "plan_id": "...",
        "items": [{ item_id, tipo_doc, empresa, elemento, periodo, decision, reason_code... }],
        "summary": {...}
    }
    """
    plan_path = Path(DATA_DIR) / "runs" / plan_id / "plan_response.json"
    
    if not plan_path.exists():
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    
    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
        
        # Transformar a formato optimizado para UI
        snapshot_items = plan_data.get("snapshot", {}).get("items", [])
        decisions = plan_data.get("decisions", [])
        
        # Crear mapa de decisiones por item_id
        decisions_map = {}
        for decision in decisions:
            item_id = decision.get("pending_item_key") or decision.get("item_id")
            if item_id:
                decisions_map[item_id] = decision
        
        # Construir items con información combinada
        items = []
        for item in snapshot_items:
            item_id = item.get("pending_item_key") or item.get("item_id") or item.get("key")
            decision = decisions_map.get(item_id, {})
            
            items.append({
                "item_id": item_id,
                "tipo_doc": item.get("tipo_doc") or item.get("type_id"),
                "empresa": item.get("empresa") or item.get("company_key"),
                "elemento": item.get("elemento") or item.get("person_key"),
                "periodo": item.get("periodo") or item.get("period_key"),
                "decision": decision.get("decision", "UNKNOWN"),
                "reason_code": decision.get("reason_code") or decision.get("primary_reason_code"),
                "reason": decision.get("reason") or decision.get("decision_reason"),
                "confidence": decision.get("confidence"),
            })
        
        return {
            "plan_id": plan_id,
            "items": items,
            "summary": plan_data.get("summary", {}),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading plan: {str(e)}")


@router.get("/runs/auto_upload/plan/{plan_id}")
async def get_auto_upload_plan(plan_id: str):
    """
    SPRINT C2.17: Recupera plan congelado por plan_id.
    
    Response:
    {
        "status": "ok",
        "plan_id": "...",
        "snapshot": {...},
        "decisions": [...],
        "summary": {...}
    }
    """
    plan_path = Path(DATA_DIR) / "runs" / plan_id / "plan_response.json"
    
    if not plan_path.exists():
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    
    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
        
        return {
            "status": "ok",
            "plan_id": plan_id,
            "snapshot": plan_data.get("snapshot", {}),
            "decisions": plan_data.get("decisions", []),
            "summary": plan_data.get("summary", {}),
            "diagnostics": plan_data.get("diagnostics", {}),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading plan: {str(e)}")


@router.post("/runs/auto_upload/execute")
async def execute_auto_upload_plan(
    request: ExecuteRequest,
    http_request: Request = None,
):
    """
    SPRINT C2.17: Ejecuta plan congelado (solo items AUTO_UPLOAD).
    
    Requisitos:
    - Header X-USE-REAL-UPLOADER=1
    - ENVIRONMENT=dev
    - plan_id válido
    
    Response:
    {
        "status": "ok" | "partial" | "error",
        "plan_id": "...",
        "results": [...],
        "summary": {...}
    }
    """
    # Cargar plan congelado
    plan_path = Path(DATA_DIR) / "runs" / request.plan_id / "plan_response.json"
    
    if not plan_path.exists():
        raise HTTPException(status_code=404, detail=f"Plan {request.plan_id} not found")
    
    # SPRINT C2.18B: Validar Decision Pack si se proporciona (la aplicación se hace en execute_auto_upload)
    if request.decision_pack_id:
        from backend.shared.decision_pack_store import DecisionPackStore
        pack_store = DecisionPackStore()
        decision_pack = pack_store.load_pack(request.plan_id, request.decision_pack_id)
        if not decision_pack:
            raise HTTPException(
                status_code=404,
                detail=f"Decision pack {request.decision_pack_id} not found for plan {request.plan_id}"
            )
    
    # Obtener coord, company_key, person_key del plan (si están guardados)
    # Por ahora, requerirlos en el request o inferirlos del plan
    # TODO: Guardar metadata del plan para recuperar estos valores
    
    # Reutilizar endpoint existente
    from backend.adapters.egestiona.execute_auto_upload_gate import ExecuteAutoUploadRequest, egestiona_execute_auto_upload
    
    # SPRINT C2.17: Obtener coord, company_key, person_key del plan congelado
    artifacts = frozen_plan.get("artifacts", {})
    coord = artifacts.get("coord") or "Kern"
    company_key = artifacts.get("company_key") or ""
    person_key = artifacts.get("person_key")
    
    if not company_key:
        raise HTTPException(status_code=400, detail="Plan does not contain company_key in artifacts")
    
    # Crear request para execute_auto_upload
    execute_request = ExecuteAutoUploadRequest(
        coord=coord,
        company_key=company_key,
        person_key=person_key,
        plan_id=request.plan_id,  # SPRINT C2.17: Usar plan_id
        decision_pack_id=request.decision_pack_id,  # SPRINT C2.18B: Pasar decision_pack_id
        items=None,  # SPRINT C2.17: Se obtienen del plan (solo AUTO_UPLOAD)
        max_uploads=request.max_uploads,
        stop_on_first_error=request.stop_on_first_error,
        continue_on_error=request.continue_on_error,
        rate_limit_seconds=request.rate_limit_seconds,
    )
    
    result = await egestiona_execute_auto_upload(execute_request, http_request)
    
    # Añadir plan_id y decision_pack_id al resultado
    if isinstance(result, dict):
        result["plan_id"] = request.plan_id
        if request.decision_pack_id:
            result["decision_pack_id"] = request.decision_pack_id
    
    return result
