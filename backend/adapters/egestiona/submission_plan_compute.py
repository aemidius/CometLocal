"""
Función pura para computar submission plan sin tocar filesystem.

Esta función NO crea runs, NO crea directorios, NO escribe archivos.
Solo computa el plan basado en pendientes, matching y guardrails.
"""

from typing import Dict, List, Any, Optional
from datetime import date
import time


def compute_submission_plan_readonly(
    *,
    pending_items: List[Dict[str, Any]],
    match_results: List[Dict[str, Any]],
    submission_plan: List[Dict[str, Any]],
    today: date,
    duration_ms: int = 0,
) -> Dict[str, Any]:
    """
    Función pura que computa el submission plan sin tocar filesystem.
    
    Args:
        pending_items: Lista de pendientes extraídos del portal
        match_results: Lista de resultados de matching
        submission_plan: Lista de items del plan con decisiones
        today: Fecha actual
        duration_ms: Duración del proceso en milisegundos
    
    Returns:
        Dict con:
        - plan: List[Dict] - Items del plan
        - summary: Dict - Estadísticas (pending_count, matched_count, unmatched_count, duration_ms)
        - stats: Dict - Estadísticas adicionales si es necesario
    """
    # Computar estadísticas
    pending_count = len(pending_items)
    matched_count = sum(1 for item in submission_plan if item.get("matched_doc") and item.get("matched_doc", {}).get("doc_id"))
    unmatched_count = pending_count - matched_count
    
    summary = {
        "pending_count": pending_count,
        "matched_count": matched_count,
        "unmatched_count": unmatched_count,
        "duration_ms": duration_ms,
    }
    
    return {
        "plan": submission_plan,
        "summary": summary,
        "stats": {
            "total_pending": pending_count,
            "total_matched": matched_count,
            "total_unmatched": unmatched_count,
            "plan_items": len(submission_plan),
        }
    }
