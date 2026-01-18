"""
Endpoint para histórico de runs y métricas de fiabilidad.

SPRINT C2.16: GET /api/runs/summary para listar summaries de runs.
"""
from __future__ import annotations

from fastapi import APIRouter, Query, Request
from typing import Optional, List
from backend.shared.run_summary import list_run_summaries
from backend.shared.tenant_context import get_tenant_from_request

router = APIRouter(tags=["runs"])


@router.get("/api/runs/summary")
async def get_runs_summary(
    limit: int = Query(50, ge=1, le=200, description="Límite de resultados"),
    platform: Optional[str] = Query(None, description="Filtrar por plataforma (ej: 'egestiona')"),
    request: Request = None,
):
    """
    Lista summaries de runs recientes.
    
    Response:
    {
        "status": "ok",
        "summaries": [
            {
                "run_id": "...",
                "platform": "egestiona",
                "coord": "...",
                "company_key": "...",
                "person_key": "...",
                "started_at": "2026-01-15T10:00:00",
                "finished_at": "2026-01-15T10:05:00",
                "duration_ms": 300000,
                "counts": {
                    "pending_total": 16,
                    "auto_upload": 4,
                    "review_required": 8,
                    "no_match": 4,
                },
                "execution": {
                    "attempted_uploads": 3,
                    "success_uploads": 2,
                    "failed_uploads": 1,
                },
                "errors": [
                    {
                        "phase": "upload",
                        "error_code": "upload_failed",
                        "message": "...",
                        "transient": false,
                        "attempt": 1,
                    }
                ],
            }
        ],
        "total": 10,
    }
    """
    # SPRINT C2.22A: Extraer tenant_id del request
    tenant_ctx = get_tenant_from_request(request)
    summaries = list_run_summaries(limit=limit, platform=platform, tenant_id=tenant_ctx.tenant_id)
    
    return {
        "status": "ok",
        "summaries": summaries,
        "total": len(summaries),
    }
