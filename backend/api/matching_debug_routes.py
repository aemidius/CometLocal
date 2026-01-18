"""
SPRINT C2.18A: Endpoints API para matching debug reports.

Expone reportes de debug determinista del matching sin romper compatibilidad.
"""

import json
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from backend.config import DATA_DIR

router = APIRouter(prefix="/api/runs", tags=["matching-debug"])


@router.get("/{run_id}/matching_debug")
async def get_matching_debug_index(run_id: str):
    """
    SPRINT C2.18A: Devuelve índice y resumen de matching debug reports para un run.
    
    Response:
    {
        "run_id": "...",
        "summary": {
            "total_items": 4,
            "no_match_count": 4,
            "review_required_count": 0,
            "auto_upload_count": 0,
            "repo_empty_count": 0,
            "type_filter_zero_count": 4,
            ...
        },
        "items": [
            {
                "item_id": "item_abc123",
                "pending_label": "...",
                "outcome": {...},
                "report_path": "matching_debug/item_abc123__debug.json",
                "created_at": "..."
            },
            ...
        ]
    }
    """
    run_dir = Path(DATA_DIR) / "runs" / run_id
    index_path = run_dir / "matching_debug" / "index.json"
    
    if not index_path.exists():
        # Si no existe, puede ser que el run no tenga matching_debug aún
        # Devolver estructura vacía en lugar de 404
        return {
            "run_id": run_id,
            "summary": {
                "total_items": 0,
                "no_match_count": 0,
                "review_required_count": 0,
                "auto_upload_count": 0,
                "repo_empty_count": 0,
                "type_filter_zero_count": 0,
                "subject_filter_zero_count": 0,
                "period_filter_zero_count": 0,
                "confidence_too_low_count": 0,
            },
            "items": [],
            "matching_debug_available": False,
        }
    
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index_data = json.load(f)
        
        index_data["run_id"] = run_id
        index_data["matching_debug_available"] = True
        return index_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading matching debug index: {str(e)}")


@router.get("/{run_id}/matching_debug/{item_id}")
async def get_matching_debug_item(run_id: str, item_id: str):
    """
    SPRINT C2.18A: Devuelve el debug report completo para un item específico.
    
    Response: MatchingDebugReportV1 completo (JSON)
    """
    run_dir = Path(DATA_DIR) / "runs" / run_id
    report_path = run_dir / "matching_debug" / f"{item_id}__debug.json"
    
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Matching debug report for item {item_id} not found in run {run_id}")
    
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            report_data = json.load(f)
        return report_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading matching debug report: {str(e)}")
