"""
SPRINT C2.18B: API endpoints para Decision Packs.

Permite crear y consultar Decision Packs para revisión humana de planes.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import List, Optional
from pathlib import Path
import json

from backend.shared.decision_pack import (
    DecisionPackV1,
    ManualDecisionV1,
    ManualDecisionAction,
)
from backend.shared.decision_pack_store import DecisionPackStore
from backend.config import DATA_DIR
from backend.shared.tenant_context import get_tenant_from_request
from backend.shared.tenant_paths import get_runs_root

router = APIRouter(prefix="/api/plans", tags=["decision-packs"])

store = DecisionPackStore()


class CreateDecisionPackRequest(BaseModel):
    """Request para crear un Decision Pack."""
    decisions: List[ManualDecisionV1] = Field(..., description="Lista de decisiones manuales")


@router.post("/{plan_id}/decision_packs")
async def create_decision_pack(
    plan_id: str,
    request: CreateDecisionPackRequest,
    http_request: Request = None,
) -> DecisionPackV1:
    """
    Crea un Decision Pack para un plan.
    
    Valida que el plan existe y crea el pack con hash estable.
    
    Response:
        DecisionPackV1 con decision_pack_id generado
    """
    # Validar que el plan existe
    plan_path = Path(DATA_DIR) / "runs" / plan_id / "plan_response.json"
    if not plan_path.exists():
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    
    # Validar decisiones
    if not request.decisions:
        raise HTTPException(status_code=400, detail="Decisions list cannot be empty")
    
    # Validar que todos los item_id existen en el plan
    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading plan: {str(e)}")
    
    # Obtener item_ids del plan
    snapshot_items = plan_data.get("snapshot", {}).get("items", [])
    plan_item_ids = set()
    for item in snapshot_items:
        item_id = item.get("pending_item_key") or item.get("item_id") or item.get("key")
        if item_id:
            plan_item_ids.add(item_id)
    
    # Validar que todos los item_id en decisiones existen
    for decision in request.decisions:
        if decision.item_id not in plan_item_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Item {decision.item_id} not found in plan {plan_id}"
            )
        
        # Validar acción específica
        if decision.action == ManualDecisionAction.MARK_AS_MATCH:
            if not decision.chosen_local_doc_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"MARK_AS_MATCH requires chosen_local_doc_id for item {decision.item_id}"
                )
            # SPRINT C2.18B: Validar que el doc_id existe en el repositorio
            from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
            try:
                store = DocumentRepositoryStoreV1()
                doc = store.get_document(decision.chosen_local_doc_id)
                if not doc:
                    raise HTTPException(
                        status_code=400,
                        detail=f"MARK_AS_MATCH doc_id {decision.chosen_local_doc_id} not found in repository"
                    )
                # Verificar que tiene file asociado
                if not doc.stored_path:
                    raise HTTPException(
                        status_code=400,
                        detail=f"MARK_AS_MATCH doc_id {decision.chosen_local_doc_id} has no stored_path"
                    )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Error validating MARK_AS_MATCH doc_id: {str(e)}"
                )
        elif decision.action == ManualDecisionAction.FORCE_UPLOAD:
            if not decision.chosen_file_path:
                raise HTTPException(
                    status_code=400,
                    detail=f"FORCE_UPLOAD requires chosen_file_path for item {decision.item_id}"
                )
            # SPRINT C2.18B: Validar que el path está dentro de repository_root_dir o allowlist
            from backend.repository.settings_routes import load_settings
            try:
                settings = load_settings()
                repository_root = Path(settings.repository_root_dir)
                chosen_path = Path(decision.chosen_file_path)
                
                # Resolver paths absolutos
                if not chosen_path.is_absolute():
                    # Si es relativo, asumir que es relativo al repository_root
                    chosen_path = repository_root / chosen_path
                chosen_path = chosen_path.resolve()
                repository_root = repository_root.resolve()
                
                # Verificar que está dentro del repository_root o su padre (data_dir)
                if not str(chosen_path).startswith(str(repository_root)) and not str(chosen_path).startswith(str(repository_root.parent)):
                    raise HTTPException(
                        status_code=400,
                        detail=f"FORCE_UPLOAD file path {decision.chosen_file_path} is outside allowed repository directory"
                    )
                
                # Verificar que el archivo existe
                if not chosen_path.exists():
                    raise HTTPException(
                        status_code=400,
                        detail=f"FORCE_UPLOAD file path {decision.chosen_file_path} does not exist"
                    )
            except Exception as e:
                if isinstance(e, HTTPException):
                    raise
                raise HTTPException(
                    status_code=400,
                    detail=f"Error validating FORCE_UPLOAD file path: {str(e)}"
                )
        elif decision.action == ManualDecisionAction.SKIP:
            if not decision.reason or not decision.reason.strip():
                raise HTTPException(
                    status_code=400,
                    detail=f"SKIP requires non-empty reason for item {decision.item_id}"
                )
    
    # Crear pack
    pack = DecisionPackV1.create(
        plan_id=plan_id,
        decisions=request.decisions,
    )
    
    # Guardar pack
    store.save_pack(pack)
    
    # SPRINT C2.20B: Registrar creación de decision pack y actualizar métricas
    try:
        from backend.shared.run_metrics import record_decision_pack_created, record_manual_decision
        
        record_decision_pack_created(plan_id)
        
        # Contar decisiones manuales y detectar presets
        # Por ahora, si hay más de 1 decisión, asumimos batch
        is_batch = len(request.decisions) > 1
        preset_applied_count = 0
        
        for decision in request.decisions:
            # Detectar si viene de preset (razón contiene "Applied preset" o "preset:")
            reason = decision.reason or ""
            if "Applied preset" in reason or "preset:" in reason.lower():
                preset_applied_count += 1
            else:
                record_manual_decision(plan_id, is_batch=is_batch)
        
        # Registrar presets aplicados
        if preset_applied_count > 0:
            from backend.shared.run_metrics import record_preset_applied
            record_preset_applied(plan_id, count=preset_applied_count)
    except Exception as e:
        print(f"[CAE][DECISION_PACK] WARNING: Error recording metrics: {e}")
    
    return pack


@router.get("/{plan_id}/decision_packs")
async def list_decision_packs(plan_id: str, request: Request = None) -> dict:
    """
    Lista todos los Decision Packs de un plan.
    
    Response:
        {
            "plan_id": "...",
            "packs": [...]
        }
    """
    # SPRINT C2.22A: Resolver path con tenant y fallback legacy
    tenant_ctx = get_tenant_from_request(request)
    runs_root = get_runs_root(DATA_DIR, tenant_ctx.tenant_id, mode="read")
    plan_path = runs_root / plan_id / "plan_response.json"
    if not plan_path.exists():
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    
    packs = store.list_packs(plan_id)
    
    return {
        "plan_id": plan_id,
        "packs": packs,
    }


@router.get("/{plan_id}/decision_packs/{decision_pack_id}")
async def get_decision_pack(
    plan_id: str,
    decision_pack_id: str,
    request: Request = None,
) -> DecisionPackV1:
    """
    Obtiene un Decision Pack completo.
    
    Response:
        DecisionPackV1
    """
    # SPRINT C2.22A: Resolver path con tenant y fallback legacy
    tenant_ctx = get_tenant_from_request(request)
    runs_root = get_runs_root(DATA_DIR, tenant_ctx.tenant_id, mode="read")
    plan_path = runs_root / plan_id / "plan_response.json"
    if not plan_path.exists():
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    
    pack = store.load_pack(plan_id, decision_pack_id)
    if not pack:
        raise HTTPException(
            status_code=404,
            detail=f"Decision pack {decision_pack_id} not found for plan {plan_id}"
        )
    
    return pack
