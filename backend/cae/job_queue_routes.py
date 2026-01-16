"""
Rutas para cola de ejecuciones CAE v1.8.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from backend.cae.job_queue_models_v1 import CAEJobV1, CAEJobStatus
from backend.cae.job_queue_v1 import enqueue_job, get_job, list_jobs, cancel_job, retry_job
from backend.cae.submission_routes import _validate_challenge
from backend.cae.submission_models_v1 import CAESubmissionPlanV1
from backend.cae.job_report_v1 import generate_job_report_html
from backend.config import DATA_DIR


router = APIRouter(prefix="/api/cae", tags=["cae-jobs"])


class EnqueueRequest(BaseModel):
    """Request para encolar un job."""
    challenge_token: str
    challenge_response: str
    dry_run: bool = False


@router.post("/execute/{plan_id}/enqueue", response_model=CAEJobV1)
async def enqueue_execution_job(
    plan_id: str,
    request: EnqueueRequest,
) -> CAEJobV1:
    """
    Encola un job de ejecución.
    
    Valida el challenge igual que /execute, pero en vez de ejecutar inmediatamente,
    encola el job para procesamiento secuencial.
    """
    # Obtener plan desde evidencia guardada
    plan_file = Path(DATA_DIR) / "docs" / "evidence" / "cae_plans" / f"{plan_id}.json"
    if not plan_file.exists():
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} no encontrado")
    
    try:
        plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
        from backend.cae.submission_models_v1 import CAESubmissionPlanV1
        plan = CAESubmissionPlanV1(**plan_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al cargar plan: {str(e)}")
    
    # Validar challenge
    is_valid, error_msg = _validate_challenge(
        request.challenge_token,
        request.challenge_response,
        plan_id,
    )
    if not is_valid:
        raise HTTPException(status_code=403, detail=error_msg or "Challenge inválido o expirado")
    
    # Validar que el plan es READY
    if plan.decision != "READY":
        raise HTTPException(
            status_code=409,
            detail=f"Plan no es READY (decision: {plan.decision})",
        )
    
    # Encolar job
    job = enqueue_job(
        plan=plan,
        challenge_token=request.challenge_token,
        challenge_response=request.challenge_response,
        dry_run=request.dry_run,
    )
    
    return job


@router.get("/jobs/{job_id}", response_model=CAEJobV1)
async def get_job_status(job_id: str) -> CAEJobV1:
    """Obtiene el estado de un job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} no encontrado")
    return job


@router.get("/jobs", response_model=List[CAEJobV1])
async def list_jobs_endpoint(
    limit: int = Query(50, ge=1, le=100),
) -> List[CAEJobV1]:
    """Lista jobs ordenados por created_at desc."""
    return list_jobs(limit=limit)


@router.post("/jobs/{job_id}/cancel", response_model=CAEJobV1)
async def cancel_job_endpoint(job_id: str) -> CAEJobV1:
    """
    Cancela un job.
    
    - Si status == QUEUED: marca CANCELED y elimina de cola
    - Si status == RUNNING: señala cancelación (worker lo manejará)
    - Si status terminal: retorna 409 Conflict
    """
    job = cancel_job(job_id)
    if not job:
        # Verificar si el job existe pero es terminal
        existing_job = get_job(job_id)
        if existing_job:
            raise HTTPException(
                status_code=409,
                detail=f"Job {job_id} no se puede cancelar (status: {existing_job.status})"
            )
        raise HTTPException(status_code=404, detail=f"Job {job_id} no encontrado")
    return job


@router.post("/jobs/{job_id}/retry", response_model=CAEJobV1)
async def retry_job_endpoint(job_id: str) -> CAEJobV1:
    """
    Crea un nuevo job como retry de otro.
    
    Solo permite retry de FAILED o PARTIAL_SUCCESS.
    No permite retry de SUCCESS o CANCELED.
    """
    new_job = retry_job(job_id)
    if not new_job:
        # Verificar si el job existe pero no se puede hacer retry
        existing_job = get_job(job_id)
        if existing_job:
            if existing_job.status in ["SUCCESS", "CANCELED"]:
                raise HTTPException(
                    status_code=409,
                    detail=f"Job {job_id} no se puede reintentar (status: {existing_job.status})"
                )
            raise HTTPException(
                status_code=400,
                detail=f"Job {job_id} no se puede reintentar (status: {existing_job.status}). Solo FAILED o PARTIAL_SUCCESS."
            )
        raise HTTPException(status_code=404, detail=f"Job {job_id} no encontrado")
    return new_job


@router.get("/jobs/{job_id}/report", response_class=HTMLResponse)
async def get_job_report(job_id: str, format: Optional[str] = Query(None, description="Formato: html (default) o pdf")) -> Response:
    """
    Genera un informe HTML del job.
    
    Args:
        job_id: ID del job
        format: Formato del informe (html o pdf). Por ahora solo HTML está disponible.
    
    Returns:
        HTMLResponse con el informe
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} no encontrado")
    
    if format == "pdf":
        # Por ahora, retornar HTML. PDF requeriría reportlab
        raise HTTPException(
            status_code=501,
            detail="Formato PDF no disponible aún. Use format=html o omita el parámetro."
        )
    
    html = generate_job_report_html(job)
    return HTMLResponse(content=html)

