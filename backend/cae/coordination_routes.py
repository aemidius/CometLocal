"""
Rutas para coordinación CAE v1.6.

Permite crear snapshots de pendientes de plataforma y generar planes desde selección.
"""

from __future__ import annotations

import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.cae.coordination_models_v1 import (
    CoordinationScopeV1,
    CoordinationSnapshotV1,
    PlatformPendingItemV1,
    SnapshotSelectionRequestV1,
)
from backend.cae.submission_models_v1 import CAEScopeContextV1
from backend.cae.submission_routes import get_doc_candidates, create_plan_from_selection, PlanFromSelectionRequest, SelectedItemV1
from backend.config import DATA_DIR


router = APIRouter(
    prefix="/api/cae/coordination",
    tags=["cae-coordination"],
)


def _generate_snapshot_id() -> str:
    """Genera un ID único para snapshot."""
    now = datetime.utcnow()
    short_id = str(uuid.uuid4())[:8]
    return f"CAESNAP-{now.strftime('%Y%m%d-%H%M%S')}-{short_id}"


def _create_fake_snapshot(scope: CoordinationScopeV1) -> CoordinationSnapshotV1:
    """Crea un snapshot FAKE para tests E2E."""
    snapshot_id = _generate_snapshot_id()
    created_at = datetime.utcnow()
    
    # Intentar encontrar tipos E2E existentes para usar en el snapshot
    from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
    store = DocumentRepositoryStoreV1()
    e2e_types = [t for t in store.list_types(include_inactive=True) if t.type_id.startswith("E2E_")]
    
    # Crear 2 pending items deterministas
    pending_items = []
    for i in range(2):
        # Usar un tipo E2E existente si está disponible, sino usar alias genéricos
        type_id = None
        type_alias_candidates = []
        if e2e_types and i < len(e2e_types):
            type_id = e2e_types[i].type_id
            type_alias_candidates = [type_id]
        else:
            type_alias_candidates = [f"E2E_MONTHLY_{i}", f"TEST_TYPE_{i+1}"]
        
        # Usar periodos recientes que puedan tener documentos
        from datetime import date
        today = date.today()
        period_key = f"{today.year}-{today.month-i:02d}" if today.month > i else f"{today.year-1}-{12+i-today.month:02d}"
        
        item = PlatformPendingItemV1(
            platform_item_id=f"FAKE_ITEM_{i}",
            type_id=type_id,
            platform_type_label=f"Tipo Test {i+1}",
            type_alias_candidates=type_alias_candidates,
            company_key=scope.company_key or "TEDELAB",
            person_key=scope.person_key or "EMILIO",
            period_key=period_key,
            raw_label=f"Pendiente Test {i+1}",
            raw_metadata={"index": i, "fake": True},
            status="PENDING",
        )
        pending_items.append(item)
    
    snapshot = CoordinationSnapshotV1(
        snapshot_id=snapshot_id,
        created_at=created_at,
        scope=scope,
        platform={"label": scope.coordination_label or "FAKE", "client_code": "FAKE_CLIENT"},
        pending_items=pending_items,
        evidence_path=f"docs/evidence/cae_snapshots/{snapshot_id}.json",
    )
    
    # Guardar snapshot
    evidence_dir = Path(DATA_DIR).parent / "docs" / "evidence" / "cae_snapshots"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = evidence_dir / f"{snapshot_id}.json"
    
    # Serializar sin secretos
    snapshot_dict = snapshot.model_dump(exclude_none=True)
    snapshot_dict["created_at"] = snapshot.created_at.isoformat()
    
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot_dict, f, indent=2, ensure_ascii=False)
    
    return snapshot


def _create_real_snapshot(scope: CoordinationScopeV1) -> CoordinationSnapshotV1:
    """Crea un snapshot REAL consultando eGestiona."""
    from concurrent.futures import ThreadPoolExecutor
    from backend.adapters.egestiona.frame_scan_headful import run_list_pending_documents_readonly_headful
    
    snapshot_id = _generate_snapshot_id()
    created_at = datetime.utcnow()
    
    # Ejecutar READ en thread pool (es síncrono)
    coordination_label = scope.coordination_label or "Kern"
    
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            run_id = executor.submit(
                run_list_pending_documents_readonly_headful,
                base_dir=str(DATA_DIR),
                platform=scope.platform_key,
                coordination=coordination_label,
                slow_mo_ms=300,
                wait_after_login_s=2.5,
            ).result(timeout=300)  # 5 minutos timeout
        
        # Leer el JSON filtrado del run
        run_dir = Path(DATA_DIR) / "runs" / run_id
        filtered_json_path = run_dir / "evidence" / "pending_documents_filtered.json"
        
        if not filtered_json_path.exists():
            raise HTTPException(
                status_code=500,
                detail=f"Snapshot run completed but filtered JSON not found: {filtered_json_path}"
            )
        
        with open(filtered_json_path, "r", encoding="utf-8") as f:
            filtered_data = json.load(f)
        
        # Mapear filas a PlatformPendingItemV1
        pending_items = []
        rows = filtered_data.get("rows", [])
        
        for row in rows:
            # Extraer datos básicos de la fila (estructura depende del grid)
            raw_label = str(row.get("label", "") or row.get("tipo", "") or "")
            company_raw = str(row.get("empresa", "") or row.get("company", "") or "")
            person_raw = str(row.get("elemento", "") or row.get("person", "") or "")
            period_raw = str(row.get("periodo", "") or row.get("period", "") or "")
            
            # Mapear a keys (simplificado, en producción usar matcher)
            company_key = scope.company_key  # Por ahora usar scope
            person_key = scope.person_key
            
            # Intentar mapear type_id (simplificado)
            type_id = None
            platform_type_label = raw_label
            type_alias_candidates = [raw_label]
            
            item = PlatformPendingItemV1(
                platform_item_id=str(row.get("id", "") or ""),
                type_id=type_id,
                platform_type_label=platform_type_label,
                type_alias_candidates=type_alias_candidates,
                company_key=company_key,
                person_key=person_key,
                period_key=period_raw if period_raw else None,
                raw_label=raw_label,
                raw_metadata=row,
                status="PENDING",
            )
            pending_items.append(item)
        
        # Obtener info de plataforma (sin secretos)
        from backend.repository.config_store_v1 import ConfigStoreV1
        config_store = ConfigStoreV1(base_dir=str(DATA_DIR))
        platforms = config_store.load_platforms()
        plat = next((p for p in platforms.platforms if p.key == scope.platform_key), None)
        coord = None
        if plat:
            coord = next((c for c in plat.coordinations if c.label == coordination_label), None)
        
        platform_info = {
            "label": coordination_label,
            "client_code": coord.client_code if coord else None,
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating snapshot: {str(e)}"
        )
    
    snapshot = CoordinationSnapshotV1(
        snapshot_id=snapshot_id,
        created_at=created_at,
        scope=scope,
        platform=platform_info,
        pending_items=pending_items,
        evidence_path=f"docs/evidence/cae_snapshots/{snapshot_id}.json",
    )
    
    # Guardar snapshot
    evidence_dir = Path(DATA_DIR).parent / "docs" / "evidence" / "cae_snapshots"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = evidence_dir / f"{snapshot_id}.json"
    
    # Serializar sin secretos
    snapshot_dict = snapshot.model_dump(exclude_none=True)
    snapshot_dict["created_at"] = snapshot.created_at.isoformat()
    
    with open(snapshot_path, "w", encoding="utf-8") as f:
        json.dump(snapshot_dict, f, indent=2, ensure_ascii=False)
    
    return snapshot


@router.post("/snapshot", response_model=CoordinationSnapshotV1)
async def create_snapshot(scope: CoordinationScopeV1) -> CoordinationSnapshotV1:
    """
    Crea un snapshot de pendientes de plataforma (READ-only).
    
    Si CAE_COORDINATION_MODE=FAKE, devuelve datos deterministas para tests.
    Si CAE_COORDINATION_MODE=REAL (o no está definido), consulta eGestiona real.
    """
    coordination_mode = os.getenv("CAE_COORDINATION_MODE", "REAL")
    
    if coordination_mode == "FAKE":
        return _create_fake_snapshot(scope)
    else:
        return _create_real_snapshot(scope)


@router.get("/snapshot/{snapshot_id}", response_model=CoordinationSnapshotV1)
async def get_snapshot(snapshot_id: str) -> CoordinationSnapshotV1:
    """Lee un snapshot guardado."""
    evidence_dir = Path(DATA_DIR).parent / "docs" / "evidence" / "cae_snapshots"
    snapshot_path = evidence_dir / f"{snapshot_id}.json"
    
    if not snapshot_path.exists():
        raise HTTPException(status_code=404, detail=f"Snapshot not found: {snapshot_id}")
    
    with open(snapshot_path, "r", encoding="utf-8") as f:
        snapshot_dict = json.load(f)
    
    # Parsear datetime
    if isinstance(snapshot_dict.get("created_at"), str):
        snapshot_dict["created_at"] = datetime.fromisoformat(snapshot_dict["created_at"])
    
    return CoordinationSnapshotV1(**snapshot_dict)


@router.get("/snapshot/{snapshot_id}/doc_candidates")
async def get_snapshot_doc_candidates(
    snapshot_id: str,
    pending_index: int = Query(..., ge=0),
    allow_period_fallback: bool = Query(False),
    include_best: bool = Query(False),
) -> Dict[str, Any]:
    """
    Obtiene candidatos de documentos para un pending item del snapshot.
    
    Reutiliza la lógica de doc_candidates usando los datos del pending item.
    """
    # Cargar snapshot
    evidence_dir = Path(DATA_DIR).parent / "docs" / "evidence" / "cae_snapshots"
    snapshot_path = evidence_dir / f"{snapshot_id}.json"
    
    if not snapshot_path.exists():
        raise HTTPException(status_code=404, detail=f"Snapshot not found: {snapshot_id}")
    
    with open(snapshot_path, "r", encoding="utf-8") as f:
        snapshot_dict = json.load(f)
    
    snapshot = CoordinationSnapshotV1(**snapshot_dict)
    
    # Validar índice
    if pending_index >= len(snapshot.pending_items):
        raise HTTPException(
            status_code=400,
            detail=f"pending_index {pending_index} out of range (snapshot has {len(snapshot.pending_items)} items)"
        )
    
    pending_item = snapshot.pending_items[pending_index]
    
    # Determinar scope y type_id
    scope = "worker" if pending_item.person_key else "company"
    
    # Intentar usar type_id exacto primero, luego alias candidates
    type_id = pending_item.type_id
    if not type_id and pending_item.type_alias_candidates:
        # Probar cada alias hasta encontrar uno que exista
        from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
        store = DocumentRepositoryStoreV1()
        for alias in pending_item.type_alias_candidates:
            doc_type = store.get_type(alias)
            if doc_type:
                type_id = alias
                break
        
        # Si ninguno existe, usar el primero de todas formas (doc_candidates puede devolver vacío)
        if not type_id:
            type_id = pending_item.type_alias_candidates[0]
    
    if not type_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot determine type_id for pending item"
        )
    
    # Llamar a doc_candidates
    response = await get_doc_candidates(
        type_id=type_id,
        scope=scope,
        company_key=pending_item.company_key,
        person_key=pending_item.person_key,
        period_key=pending_item.period_key,
        allow_period_fallback=allow_period_fallback,
        include_best=include_best,  # v1.7: Pasar include_best
    )
    
    return response.model_dump()


@router.post("/plan_from_snapshot_selection")
async def plan_from_snapshot_selection(request: SnapshotSelectionRequestV1) -> Dict[str, Any]:
    """
    Genera un plan desde selección de items del snapshot.
    
    Construye selected_items a partir del snapshot y llama a la lógica existente de plan_from_selection.
    """
    from backend.cae.submission_routes import create_plan_from_selection
    
    # Cargar snapshot
    evidence_dir = Path(DATA_DIR).parent / "docs" / "evidence" / "cae_snapshots"
    snapshot_path = evidence_dir / f"{request.snapshot_id}.json"
    
    if not snapshot_path.exists():
        raise HTTPException(status_code=404, detail=f"Snapshot not found: {request.snapshot_id}")
    
    with open(snapshot_path, "r", encoding="utf-8") as f:
        snapshot_dict = json.load(f)
    
    snapshot = CoordinationSnapshotV1(**snapshot_dict)
    
    # Construir selected_items desde snapshot y selección
    selected_items = []
    for sel in request.selected:
        pending_index = sel.get("pending_index")
        suggested_doc_id = sel.get("suggested_doc_id")
        
        if pending_index is None or pending_index >= len(snapshot.pending_items):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid pending_index: {pending_index}"
            )
        
        pending_item = snapshot.pending_items[pending_index]
        
        # Determinar scope
        scope_str = "worker" if pending_item.person_key else "company"
        
        # Determinar type_id (usar el primero de alias_candidates si no hay type_id exacto)
        type_id = pending_item.type_id
        if not type_id and pending_item.type_alias_candidates:
            type_id = pending_item.type_alias_candidates[0]
        
        if not type_id:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot determine type_id for pending item at index {pending_index}"
            )
        
        selected_items.append({
            "type_id": type_id,
            "scope": scope_str,
            "company_key": pending_item.company_key,
            "person_key": pending_item.person_key,
            "period_key": pending_item.period_key,
            "suggested_doc_id": suggested_doc_id,
        })
    
    # Construir SelectedItemV1 desde los dicts
    selected_items_typed = []
    for item_dict in selected_items:
        selected_items_typed.append(SelectedItemV1(**item_dict))
    
    # Llamar a create_plan_from_selection
    plan_request = PlanFromSelectionRequest(
        scope=request.scope,
        selected_items=selected_items_typed,
    )
    
    plan_response = await create_plan_from_selection(plan_request)
    
    return plan_response.model_dump()

