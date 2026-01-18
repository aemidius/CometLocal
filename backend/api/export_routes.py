"""
SPRINT C2.21: API endpoints para export CAE.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import uuid
import tempfile

from backend.config import DATA_DIR
from backend.export.cae_exporter import export_cae

router = APIRouter(prefix="/api/export", tags=["export"])


class ExportCAERequest(BaseModel):
    """Request para exportar CAE."""
    company_key: str
    period: str  # "2025" o "2025-01"


# Store temporal de exports (en producción usar cache/DB)
_exports_store: dict[str, Path] = {}


@router.post("/cae")
async def create_cae_export(request: ExportCAERequest) -> dict:
    """
    Crea un export CAE para un cliente y periodo.
    
    Response:
    {
        "export_id": "...",
        "zip_path": "...",
        "download_url": "/api/export/cae/download/..."
    }
    """
    try:
        # Validar periodo
        period_parts = request.period.split("-")
        if len(period_parts) == 1:
            # Año completo
            year = period_parts[0]
            if not year.isdigit() or len(year) != 4:
                raise HTTPException(status_code=400, detail="Period must be YYYY or YYYY-MM")
        elif len(period_parts) == 2:
            # Año-mes
            year, month = period_parts
            if not year.isdigit() or len(year) != 4:
                raise HTTPException(status_code=400, detail="Period year must be YYYY")
            if not month.isdigit() or len(month) != 2 or int(month) < 1 or int(month) > 12:
                raise HTTPException(status_code=400, detail="Period month must be MM (01-12)")
        else:
            raise HTTPException(status_code=400, detail="Period must be YYYY or YYYY-MM")
        
        # Crear directorio temporal para exports
        exports_dir = Path(DATA_DIR) / "exports"
        exports_dir.mkdir(parents=True, exist_ok=True)
        
        # Generar export
        zip_path = export_cae(
            company_key=request.company_key,
            period=request.period,
            output_dir=exports_dir,
        )
        
        # Generar export_id
        export_id = f"export_{uuid.uuid4().hex[:16]}"
        _exports_store[export_id] = zip_path
        
        return {
            "export_id": export_id,
            "zip_path": str(zip_path),
            "download_url": f"/api/export/cae/download/{export_id}",
            "filename": zip_path.name,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating export: {str(e)}")


@router.get("/cae/download/{export_id}")
async def download_cae_export(export_id: str):
    """
    Descarga un export CAE por ID.
    """
    if export_id not in _exports_store:
        raise HTTPException(status_code=404, detail=f"Export {export_id} not found")
    
    zip_path = _exports_store[export_id]
    
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail=f"Export file not found: {zip_path}")
    
    return FileResponse(
        path=zip_path,
        filename=zip_path.name,
        media_type="application/zip",
    )
