"""
Métricas de fiabilidad y resumen histórico de runs.

SPRINT C2.16: Genera run_summary.json y endpoint para histórico.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import os

from backend.config import DATA_DIR


def save_run_summary(
    run_id: str,
    platform: str,
    coord: str,
    company_key: str,
    person_key: Optional[str],
    started_at: datetime,
    finished_at: Optional[datetime] = None,
    duration_ms: Optional[int] = None,
    pending_total: int = 0,
    auto_upload_count: int = 0,
    review_required_count: int = 0,
    no_match_count: int = 0,
    attempted_uploads: int = 0,
    success_uploads: int = 0,
    failed_uploads: int = 0,
    errors: Optional[List[Dict[str, Any]]] = None,
    evidence_root: Optional[str] = None,  # SPRINT C2.16.1: Ruta base de evidencias
    evidence_paths: Optional[Dict[str, str]] = None,  # SPRINT C2.16.1: Rutas principales de evidencias
    run_kind: str = "execution",  # SPRINT C2.16.2: "execution" | "plan"
    base_dir: str | Path = "data",
) -> Path:
    """
    Guarda run_summary.json con métricas de fiabilidad.
    
    Args:
        run_id: ID del run
        platform: Plataforma ("egestiona", etc.)
        coord: Coordinación
        company_key: Clave de empresa
        person_key: Clave de persona (opcional)
        started_at: Timestamp de inicio
        finished_at: Timestamp de finalización (opcional)
        duration_ms: Duración en milisegundos (opcional)
        pending_total: Total de pendientes encontrados
        auto_upload_count: Items clasificados como AUTO_UPLOAD
        review_required_count: Items clasificados como REVIEW_REQUIRED
        no_match_count: Items clasificados como NO_MATCH
        attempted_uploads: Intentos de upload
        success_uploads: Uploads exitosos
        failed_uploads: Uploads fallidos
        errors: Lista de errores [{phase, error_code, message, transient, attempt}]
        base_dir: Directorio base (default "data")
    
    Returns:
        Path al archivo run_summary.json guardado
    """
    base = Path(base_dir) if isinstance(base_dir, str) else base_dir
    run_dir = base / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    summary = {
        "run_id": run_id,
        "platform": platform,
        "coord": coord,
        "company_key": company_key,
        "person_key": person_key,
        "run_kind": run_kind,  # SPRINT C2.16.2: "execution" | "plan"
        "started_at": started_at.isoformat() if isinstance(started_at, datetime) else str(started_at),
        "finished_at": finished_at.isoformat() if finished_at and isinstance(finished_at, datetime) else (str(finished_at) if finished_at else None),
        "duration_ms": duration_ms,
        "counts": {
            "pending_total": pending_total,
            "auto_upload": auto_upload_count,
            "review_required": review_required_count,
            "no_match": no_match_count,
        },
        "execution": {
            "attempted_uploads": attempted_uploads,
            "success_uploads": success_uploads,
            "failed_uploads": failed_uploads,
        },
        "errors": errors or [],
    }
    
    # SPRINT C2.16.1: Añadir rutas de evidencia principales
    if evidence_root:
        summary["evidence_root"] = evidence_root
    if evidence_paths:
        summary["evidence_paths"] = evidence_paths
    
    summary_path = run_dir / "run_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"[RUN_SUMMARY] Guardado: {summary_path}")
    return summary_path


def load_run_summary(run_id: str, base_dir: str | Path = "data") -> Optional[Dict[str, Any]]:
    """
    Carga run_summary.json de un run.
    
    Args:
        run_id: ID del run
        base_dir: Directorio base (default "data")
    
    Returns:
        Dict con el summary o None si no existe
    """
    base = Path(base_dir) if isinstance(base_dir, str) else base_dir
    summary_path = base / "runs" / run_id / "run_summary.json"
    
    if not summary_path.exists():
        return None
    
    try:
        with open(summary_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[RUN_SUMMARY] ⚠️ Error cargando summary de {run_id}: {e}")
        return None


def list_run_summaries(
    limit: int = 50,
    platform: Optional[str] = None,
    base_dir: str | Path = "data",
) -> List[Dict[str, Any]]:
    """
    Lista summaries de runs recientes.
    
    Args:
        limit: Límite de resultados
        platform: Filtrar por plataforma (opcional)
        base_dir: Directorio base (default "data")
    
    Returns:
        Lista de summaries ordenados por started_at descendente
    """
    base = Path(base_dir) if isinstance(base_dir, str) else base_dir
    runs_dir = base / "runs"
    
    if not runs_dir.exists():
        return []
    
    summaries = []
    
    # Iterar sobre directorios de runs
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        
        run_id = run_dir.name
        
        # Saltar directorios temporales
        if run_id.startswith("tmp_"):
            continue
        
        summary = load_run_summary(run_id, base_dir)
        if not summary:
            continue
        
        # Filtrar por plataforma si se especifica
        if platform and summary.get("platform") != platform:
            continue
        
        summaries.append(summary)
    
    # Ordenar por started_at descendente
    summaries.sort(
        key=lambda s: s.get("started_at", ""),
        reverse=True,
    )
    
    return summaries[:limit]
