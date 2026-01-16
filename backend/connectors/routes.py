"""
Rutas API para conectores.

Endpoint DEV-ONLY para ejecutar conectores.
"""

import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.connectors.runner import run_connector

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


class ConnectorRunRequest(BaseModel):
    """Request para ejecutar un conector."""
    platform_id: str
    tenant_id: Optional[str] = None
    headless: bool = True
    max_items: int = 3
    dry_run: bool = False


@router.post("/run")
async def run_connector_endpoint(request: ConnectorRunRequest):
    """
    Ejecuta un conector (DEV-ONLY).
    
    Solo disponible si E2E_SEED_ENABLED=1 o ENVIRONMENT=dev.
    
    Args:
        request: Parámetros de ejecución
    
    Returns:
        Resumen de ejecución con counts y results
    """
    # Verificar que esté habilitado (DEV-ONLY)
    e2e_enabled = os.getenv("E2E_SEED_ENABLED") == "1"
    env_dev = os.getenv("ENVIRONMENT") in ("dev", "development", "local")
    
    if not (e2e_enabled or env_dev):
        raise HTTPException(
            status_code=404,
            detail="Connector endpoints disabled. Set E2E_SEED_ENABLED=1 or ENVIRONMENT=dev"
        )
    
    try:
        result = await run_connector(
            platform_id=request.platform_id,
            tenant_id=request.tenant_id,
            headless=request.headless,
            max_items=request.max_items,
            dry_run=request.dry_run,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")
