"""
SPRINT C2.30: Endpoints para scheduling de runs.

Endpoints:
- GET /api/schedules/list - Lista schedules del contexto
- POST /api/schedules/upsert - Crea o actualiza schedule
- POST /api/schedules/toggle - Habilita/deshabilita schedule
- POST /api/schedules/delete - Elimina schedule
- POST /api/schedules/tick - Ejecuta tick de schedules (gated)
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.config import DATA_DIR
from backend.shared.context_guardrails import has_human_coordination_context
from backend.shared.tenant_context import get_tenant_from_request
from backend.shared.schedule_models import ScheduleV1, ScheduleStore
from backend.shared.schedule_tick import execute_schedule_tick


router = APIRouter(prefix="/api/schedules", tags=["schedules"])


class UpsertScheduleRequestV1(BaseModel):
    """Request para crear/actualizar schedule."""
    schedule_id: Optional[str] = None  # Si no se proporciona, se genera uno nuevo
    plan_id: str
    dry_run: bool = False
    cadence: str  # "daily" | "weekly"
    at_time: str  # "HH:MM"
    weekday: Optional[int] = None  # 0-6, solo si weekly
    enabled: bool = True


class ToggleScheduleRequestV1(BaseModel):
    """Request para habilitar/deshabilitar schedule."""
    schedule_id: str
    enabled: bool


class DeleteScheduleRequestV1(BaseModel):
    """Request para eliminar schedule."""
    schedule_id: str


@router.get("/list")
async def list_schedules(request: Request) -> dict:
    """
    Lista todos los schedules del contexto actual.
    
    Requiere contexto humano válido.
    """
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
    
    store = ScheduleStore(DATA_DIR, tenant_id)
    schedules = store.list_schedules()
    
    return {
        "schedules": [s.model_dump(mode="json", exclude_none=True) for s in schedules]
    }


@router.post("/upsert")
async def upsert_schedule(request: Request, body: UpsertScheduleRequestV1) -> dict:
    """
    Crea o actualiza un schedule.
    
    Requiere contexto humano válido.
    """
    if not has_human_coordination_context(request):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing_coordination_context",
                "message": "Selecciona Empresa propia, Plataforma y Empresa coordinada"
            }
        )
    
    # Validar cadence
    if body.cadence not in ("daily", "weekly"):
        raise HTTPException(status_code=400, detail="cadence debe ser 'daily' o 'weekly'")
    
    if body.cadence == "weekly" and body.weekday is None:
        raise HTTPException(status_code=400, detail="weekday es requerido para cadence 'weekly'")
    
    if body.cadence == "daily" and body.weekday is not None:
        raise HTTPException(status_code=400, detail="weekday no debe especificarse para cadence 'daily'")
    
    # Validar at_time
    try:
        hour, minute = map(int, body.at_time.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError("Invalid time")
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="at_time debe estar en formato 'HH:MM'")
    
    tenant_ctx = get_tenant_from_request(request)
    tenant_id = tenant_ctx.tenant_id
    
    # Obtener contexto
    own_company_key = request.headers.get("X-Coordination-Own-Company")
    platform_key = request.headers.get("X-Coordination-Platform")
    coordinated_company_key = request.headers.get("X-Coordination-Coordinated-Company")
    
    if not (own_company_key and platform_key and coordinated_company_key):
        raise HTTPException(status_code=400, detail="Contexto humano incompleto")
    
    store = ScheduleStore(DATA_DIR, tenant_id)
    
    # Determinar si es nuevo o actualización
    if body.schedule_id:
        existing = [s for s in store.list_schedules() if s.schedule_id == body.schedule_id]
        if existing:
            # Actualizar
            schedule = existing[0]
            schedule.plan_id = body.plan_id
            schedule.dry_run = body.dry_run
            schedule.cadence = body.cadence
            schedule.at_time = body.at_time
            schedule.weekday = body.weekday
            schedule.enabled = body.enabled
            schedule.updated_at = datetime.now()
        else:
            # No existe, crear nuevo
            schedule = ScheduleV1(
                schedule_id=body.schedule_id,
                enabled=body.enabled,
                plan_id=body.plan_id,
                dry_run=body.dry_run,
                cadence=body.cadence,
                at_time=body.at_time,
                weekday=body.weekday,
                own_company_key=own_company_key,
                platform_key=platform_key,
                coordinated_company_key=coordinated_company_key,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
    else:
        # Crear nuevo con ID generado
        schedule_id = f"schedule_{uuid.uuid4().hex[:8]}"
        schedule = ScheduleV1(
            schedule_id=schedule_id,
            enabled=body.enabled,
            plan_id=body.plan_id,
            dry_run=body.dry_run,
            cadence=body.cadence,
            at_time=body.at_time,
            weekday=body.weekday,
            own_company_key=own_company_key,
            platform_key=platform_key,
            coordinated_company_key=coordinated_company_key,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
    
    store.save_schedule(schedule)
    
    return {
        "schedule": schedule.model_dump(mode="json", exclude_none=True)
    }


@router.post("/toggle")
async def toggle_schedule(request: Request, body: ToggleScheduleRequestV1) -> dict:
    """
    Habilita o deshabilita un schedule.
    
    Requiere contexto humano válido.
    """
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
    
    store = ScheduleStore(DATA_DIR, tenant_id)
    schedules = store.list_schedules()
    
    schedule = next((s for s in schedules if s.schedule_id == body.schedule_id), None)
    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule {body.schedule_id} not found")
    
    schedule.enabled = body.enabled
    schedule.updated_at = datetime.now()
    store.save_schedule(schedule)
    
    return {
        "schedule": schedule.model_dump(mode="json", exclude_none=True)
    }


@router.post("/delete")
async def delete_schedule(request: Request, body: DeleteScheduleRequestV1) -> dict:
    """
    Elimina un schedule.
    
    Requiere contexto humano válido.
    """
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
    
    store = ScheduleStore(DATA_DIR, tenant_id)
    deleted = store.delete_schedule(body.schedule_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Schedule {body.schedule_id} not found")
    
    return {"deleted": True, "schedule_id": body.schedule_id}


@router.post("/tick")
async def tick_schedules(request: Request) -> dict:
    """
    Ejecuta un "tick" de schedules para el contexto actual.
    
    Gated a dev/test o API key local.
    Requiere contexto humano válido.
    """
    # SPRINT C2.30: Gate a dev/test
    env = os.getenv("ENVIRONMENT", "").lower()
    if env not in ("dev", "test"):
        # Verificar API key si existe patrón
        api_key = request.headers.get("X-API-Key")
        if not api_key or api_key != os.getenv("SCHEDULE_TICK_API_KEY", ""):
            raise HTTPException(
                status_code=403,
                detail="Tick endpoint only available in dev/test or with valid API key"
            )
    
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
    
    # Ejecutar tick
    results = execute_schedule_tick(tenant_id, dry_run_mode=False)
    
    return results
