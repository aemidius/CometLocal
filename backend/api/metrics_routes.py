"""
SPRINT C2.20B: API endpoints para métricas operativas.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
from pathlib import Path
import json

from backend.config import DATA_DIR
from backend.shared.run_metrics import load_metrics, RunMetricsV1

router = APIRouter(prefix="/api", tags=["metrics"])


@router.get("/runs/{run_id}/metrics")
async def get_run_metrics(run_id: str) -> dict:
    """
    Obtiene métricas de un run específico.
    
    Si run_id es un plan_id, devuelve métricas del plan.
    """
    # Intentar cargar como plan_id primero
    metrics = load_metrics(run_id)
    
    if not metrics:
        raise HTTPException(status_code=404, detail=f"Metrics for {run_id} not found")
    
    return metrics.to_dict()


@router.get("/metrics/summary")
async def get_metrics_summary(
    limit: int = Query(10, description="Número de runs a incluir", ge=1, le=100),
    platform: Optional[str] = Query(None, description="Filtrar por plataforma"),
) -> dict:
    """
    Obtiene resumen agregado de métricas.
    
    Response:
    {
        "total_runs": N,
        "total_items": N,
        "decisions_breakdown": {...},
        "source_breakdown": {...},
        "percentages": {
            "auto_upload": X,
            "skip": X,
            "review_required": X,
            "with_learning": X,
            "with_presets": X,
        }
    }
    """
    base = Path(DATA_DIR)
    runs_dir = base / "runs"
    
    if not runs_dir.exists():
        return {
            "total_runs": 0,
            "total_items": 0,
            "decisions_breakdown": {},
            "source_breakdown": {},
            "percentages": {},
        }
    
    # Buscar todos los metrics.json
    all_metrics = []
    for plan_dir in runs_dir.iterdir():
        if not plan_dir.is_dir():
            continue
        
        metrics_path = plan_dir / "metrics.json"
        if metrics_path.exists():
            try:
                metrics = load_metrics(plan_dir.name)
                if metrics:
                    # Filtrar por platform si se proporciona
                    if platform:
                        # Por ahora no tenemos platform en metrics, saltar filtro
                        pass
                    all_metrics.append(metrics)
            except Exception as e:
                print(f"[Metrics] Error loading metrics from {plan_dir.name}: {e}")
                continue
    
    # Ordenar por created_at descendente y limitar
    all_metrics.sort(key=lambda m: m.created_at, reverse=True)
    recent_metrics = all_metrics[:limit]
    
    # Agregar
    total_runs = len(recent_metrics)
    total_items = sum(m.total_items for m in recent_metrics)
    
    decisions_breakdown = {
        "AUTO_UPLOAD": 0,
        "REVIEW_REQUIRED": 0,
        "NO_MATCH": 0,
        "SKIP": 0,
    }
    
    source_breakdown = {
        "auto_matching": 0,
        "learning_hint_resolved": 0,
        "preset_applied": 0,
        "manual_single": 0,
        "manual_batch": 0,
    }
    
    runs_with_learning = 0
    runs_with_presets = 0
    
    for metrics in recent_metrics:
        # Decisions
        for decision_type, count in metrics.decisions_count.items():
            if decision_type in decisions_breakdown:
                decisions_breakdown[decision_type] += count
        
        # Sources
        for source, count in metrics.source_breakdown.items():
            if source in source_breakdown:
                source_breakdown[source] += count
        
        # Flags
        if metrics.source_breakdown.get("learning_hint_resolved", 0) > 0:
            runs_with_learning += 1
        if metrics.source_breakdown.get("preset_applied", 0) > 0:
            runs_with_presets += 1
    
    # Calcular porcentajes
    total_decisions = sum(decisions_breakdown.values())
    total_sources = sum(source_breakdown.values())
    
    percentages = {}
    if total_decisions > 0:
        percentages["auto_upload"] = (decisions_breakdown["AUTO_UPLOAD"] / total_decisions) * 100
        percentages["skip"] = (decisions_breakdown["SKIP"] / total_decisions) * 100
        percentages["review_required"] = (decisions_breakdown["REVIEW_REQUIRED"] / total_decisions) * 100
    
    if total_runs > 0:
        percentages["with_learning"] = (runs_with_learning / total_runs) * 100
        percentages["with_presets"] = (runs_with_presets / total_runs) * 100
    
    return {
        "total_runs": total_runs,
        "total_items": total_items,
        "decisions_breakdown": decisions_breakdown,
        "source_breakdown": source_breakdown,
        "percentages": percentages,
    }
