"""
SPRINT C2.29: Endpoints para scheduler y runs audit-ready.

Endpoints:
- POST /api/runs/start - Inicia un run
- GET /api/runs/latest - Obtiene el último run del contexto
- GET /api/runs/<run_id> - Obtiene un run específico
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.config import DATA_DIR
from backend.shared.context_guardrails import has_human_coordination_context
from backend.shared.tenant_context import get_tenant_from_request, compute_tenant_from_coordination_context
from backend.shared.run_summary import (
    RunSummaryV1, RunContextV1, create_run_dir, save_run_summary
)
from backend.shared.run_lock import RunLock
from backend.cae.execution_runner_v1 import CAEExecutionRunnerV1
from backend.cae.submission_routes import _get_plan_evidence
from backend.repository.config_store_v1 import ConfigStoreV1
from backend.api.coordination_context_routes import (
    CompanyOptionV1, PlatformOptionV1, CoordinationContextOptionsV1
)


router = APIRouter(prefix="/api/runs", tags=["runs"])


class StartRunRequestV1(BaseModel):
    """Request para iniciar un run."""
    plan_id: Optional[str] = None
    preset_id: Optional[str] = None
    decision_pack_id: Optional[str] = None
    dry_run: bool = False


class StartRunResponseV1(BaseModel):
    """Respuesta al iniciar un run."""
    run_id: str
    status: str
    run_dir_rel: str


def _get_context_from_request(request: Request) -> RunContextV1:
    """
    Extrae el contexto humano de la request y obtiene los nombres.
    
    Args:
        request: Request de FastAPI
    
    Returns:
        RunContextV1 con keys y names
    """
    own_company_key = request.headers.get("X-Coordination-Own-Company")
    platform_key = request.headers.get("X-Coordination-Platform")
    coordinated_company_key = request.headers.get("X-Coordination-Coordinated-Company")
    
    if not (own_company_key and platform_key and coordinated_company_key):
        raise HTTPException(
            status_code=400,
            detail={"error": "missing_coordination_context", "message": "Selecciona Empresa propia, Plataforma y Empresa coordinada"}
        )
    
    # Obtener opciones para conseguir los nombres
    # Usar ConfigStore directamente para evitar dependencia circular
    store = ConfigStoreV1(base_dir=DATA_DIR)
    
    # Construir opciones manualmente
    org = store.load_org()
    own_companies = [
        CompanyOptionV1(
            key=org.tax_id,
            name=org.legal_name,
            vat_id=org.tax_id
        )
    ]
    
    platforms_data = store.load_platforms()
    platforms = [
        PlatformOptionV1(
            key=p.key,
            name=p.key.replace("_", " ").title()
        )
        for p in platforms_data.platforms
    ]
    
    coordinated_companies_by_platform = {}
    for platform in platforms_data.platforms:
        coordinated = []
        for coord in platform.coordinations:
            coordinated.append(
                CompanyOptionV1(
                    key=coord.client_code,
                    name=coord.label,
                    vat_id=None
                )
            )
        if coordinated:
            coordinated_companies_by_platform[platform.key] = coordinated
    
    options = CoordinationContextOptionsV1(
        own_companies=own_companies,
        platforms=platforms,
        coordinated_companies_by_platform=coordinated_companies_by_platform
    )
    
    # Buscar nombres
    own_company_name = None
    for company in options.own_companies:
        if company.key == own_company_key:
            own_company_name = company.name
            break
    
    platform_name = None
    for platform in options.platforms:
        if platform.key == platform_key:
            platform_name = platform.name
            break
    
    coordinated_company_name = None
    coordinated_companies = options.coordinated_companies_by_platform.get(platform_key, [])
    for company in coordinated_companies:
        if company.key == coordinated_company_key:
            coordinated_company_name = company.name
            break
    
    return RunContextV1(
        own_company_key=own_company_key,
        own_company_name=own_company_name,
        platform_key=platform_key,
        platform_name=platform_name,
        coordinated_company_key=coordinated_company_key,
        coordinated_company_name=coordinated_company_name,
    )


@router.post("/start", response_model=StartRunResponseV1)
async def start_run(request: Request, body: StartRunRequestV1) -> StartRunResponseV1:
    """
    Inicia un run.
    
    Requiere contexto humano válido (headers humanos).
    Crea run_dir y ejecuta plan/preset/pack.
    """
    # SPRINT C2.29: Guardrail: requerir contexto humano
    if not has_human_coordination_context(request):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing_coordination_context",
                "message": "Selecciona Empresa propia, Plataforma y Empresa coordinada"
            }
        )
    
    # Obtener contexto con nombres
    context = _get_context_from_request(request)
    
    # Calcular tenant_id
    tenant_ctx = get_tenant_from_request(request)
    tenant_id = tenant_ctx.tenant_id
    
    # Generar run_id
    import uuid
    run_id = str(uuid.uuid4())[:8]
    
    # SPRINT C2.29: Lock por contexto
    lock = RunLock(DATA_DIR, tenant_id)
    acquired, lock_error = lock.acquire(run_id)
    if not acquired:
        raise HTTPException(status_code=409, detail=lock_error)
    
    try:
        # Crear run_dir
        run_dir = create_run_dir(DATA_DIR, tenant_id, run_id)
        run_dir_rel = f"tenants/{tenant_id}/runs/{run_dir.name}"
        
        # Determinar qué ejecutar
        if body.plan_id:
            # Ejecutar plan
            plan = _get_plan_evidence(body.plan_id)
            if not plan:
                raise HTTPException(status_code=404, detail=f"Plan {body.plan_id} not found")
            
            # Guardar input
            input_data = {
                "type": "plan",
                "plan_id": body.plan_id,
                "plan": plan.model_dump(mode="json")
            }
            
            # Ejecutar
            runner = CAEExecutionRunnerV1()
            result = runner.execute_plan_egestiona(plan=plan, dry_run=body.dry_run)
            
            # SPRINT C2.29: Copiar evidencias del executor al run_dir si existen
            if result.evidence_path and Path(result.evidence_path).exists():
                evidence_src = Path(result.evidence_path)
                evidence_dst = run_dir / "evidence"
                evidence_dst.mkdir(exist_ok=True)
                
                # Copiar contenido del directorio de evidencias
                import shutil
                if evidence_src.is_dir():
                    for item in evidence_src.iterdir():
                        if item.is_file():
                            shutil.copy2(item, evidence_dst / item.name)
                        elif item.is_dir():
                            shutil.copytree(item, evidence_dst / item.name, dirs_exist_ok=True)
            
            # Guardar result
            result_data = result.model_dump(mode="json", exclude_none=True)
            
            # Crear summary
            summary = RunSummaryV1(
                run_id=run_id,
                started_at=result.started_at,
                finished_at=result.finished_at,
                status=_map_status(result.status),
                context=context,
                plan_id=body.plan_id,
                dry_run=body.dry_run,
                steps_executed=_extract_steps(result),
                counters=_extract_counters(result),
                artifacts=_extract_artifacts(result, run_dir),
                error=result.error,
                run_dir_rel=run_dir_rel,
            )
            
        elif body.preset_id:
            # TODO: Implementar ejecución de preset
            raise HTTPException(status_code=501, detail="Preset execution not yet implemented")
        
        elif body.decision_pack_id:
            # TODO: Implementar ejecución de decision pack
            raise HTTPException(status_code=501, detail="Decision pack execution not yet implemented")
        
        else:
            raise HTTPException(status_code=400, detail="Debe especificar plan_id, preset_id o decision_pack_id")
        
        # Guardar summary
        save_run_summary(run_dir, summary, input_data, result_data)
        
        return StartRunResponseV1(
            run_id=run_id,
            status=summary.status,
            run_dir_rel=run_dir_rel,
        )
    
    finally:
        # Liberar lock
        lock.release(run_id)


def _map_status(status: str) -> str:
    """Mapea status de RunResultV1 a RunSummaryV1."""
    mapping = {
        "SUCCESS": "success",
        "FAILED": "error",
        "BLOCKED": "blocked",
        "PARTIAL_SUCCESS": "partial_success",
        "CANCELED": "canceled",
    }
    return mapping.get(status, "error")


def _extract_steps(result) -> list[str]:
    """Extrae pasos ejecutados del resultado."""
    # Por ahora, extraer de summary si existe
    summary = result.summary or {}
    steps = summary.get("steps", [])
    if isinstance(steps, list):
        return [str(s) for s in steps]
    return []


def _extract_counters(result) -> dict[str, int]:
    """Extrae contadores del resultado."""
    summary = result.summary or {}
    return {
        "docs_processed": summary.get("items_processed", 0),
        "uploads_attempted": summary.get("items_success", 0) + summary.get("items_failed", 0),
        "uploads_ok": summary.get("items_success", 0),
        "uploads_failed": summary.get("items_failed", 0),
    }


def _extract_artifacts(result, run_dir: Path) -> dict[str, str]:
    """Extrae paths de artefactos."""
    artifacts = {}
    
    # Evidence path
    if result.evidence_path:
        evidence_rel = Path(result.evidence_path).relative_to(run_dir.parent.parent.parent)
        artifacts["evidence"] = str(evidence_rel)
    
    return artifacts


@router.get("/latest")
async def get_latest_run(request: Request) -> dict:
    """
    Obtiene el último run del contexto actual.
    """
    # Requerir contexto humano
    if not has_human_coordination_context(request):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing_coordination_context",
                "message": "Selecciona Empresa propia, Plataforma y Empresa coordinada"
            }
        )
    
    tenant_ctx = get_tenant_from_request(request)
    tenant_id = tenant_ctx.tenant_id
    
    # Buscar último run
    from backend.shared.tenant_paths import tenant_runs_root
    runs_root = tenant_runs_root(DATA_DIR, tenant_id)
    
    if not runs_root.exists():
        raise HTTPException(status_code=404, detail="No runs found")
    
    # Buscar directorios de runs (formato: YYYYMMDD_HHMMSS__<run_id>)
    run_dirs = sorted(runs_root.glob("*__*"), key=lambda p: p.name, reverse=True)
    
    if not run_dirs:
        raise HTTPException(status_code=404, detail="No runs found")
    
    latest_run_dir = run_dirs[0]
    
    # Cargar summary.json
    summary_path = latest_run_dir / "summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="Run summary not found")
    
    with open(summary_path, "r", encoding="utf-8") as f:
        summary_data = json.load(f)
    
    return {
        "run_id": summary_data["run_id"],
        "summary": summary_data,
        "run_dir_rel": summary_data.get("run_dir_rel", ""),
        "summary_md_path": f"tenants/{tenant_id}/runs/{latest_run_dir.name}/summary.md",
    }


@router.get("/{run_id}")
async def get_run(run_id: str, request: Request) -> dict:
    """
    Obtiene un run específico.
    """
    # Requerir contexto humano
    if not has_human_coordination_context(request):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing_coordination_context",
                "message": "Selecciona Empresa propia, Plataforma y Empresa coordinada"
            }
        )
    
    tenant_ctx = get_tenant_from_request(request)
    tenant_id = tenant_ctx.tenant_id
    
    # Buscar run
    from backend.shared.tenant_paths import tenant_runs_root
    runs_root = tenant_runs_root(DATA_DIR, tenant_id)
    
    # Buscar directorio que contenga el run_id
    run_dirs = list(runs_root.glob(f"*__{run_id}"))
    
    if not run_dirs:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    run_dir = run_dirs[0]
    
    # Cargar summary.json
    summary_path = run_dir / "summary.json"
    if not summary_path.exists():
        raise HTTPException(status_code=404, detail="Run summary not found")
    
    with open(summary_path, "r", encoding="utf-8") as f:
        summary_data = json.load(f)
    
    # Cargar input.json y result.json si existen
    input_data = None
    input_path = run_dir / "input.json"
    if input_path.exists():
        with open(input_path, "r", encoding="utf-8") as f:
            input_data = json.load(f)
    
    result_data = None
    result_path = run_dir / "result.json"
    if result_path.exists():
        with open(result_path, "r", encoding="utf-8") as f:
            result_data = json.load(f)
    
    return {
        "run_id": run_id,
        "summary": summary_data,
        "input": input_data,
        "result": result_data,
        "run_dir_rel": summary_data.get("run_dir_rel", ""),
        "artifacts": {
            "summary_md": f"tenants/{tenant_id}/runs/{run_dir.name}/summary.md",
            "summary_json": f"tenants/{tenant_id}/runs/{run_dir.name}/summary.json",
            "input_json": f"tenants/{tenant_id}/runs/{run_dir.name}/input.json" if input_data else None,
            "result_json": f"tenants/{tenant_id}/runs/{run_dir.name}/result.json" if result_data else None,
        }
    }
