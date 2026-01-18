"""
SPRINT C2.20B: Métricas operativas CAE (valor y eficiencia).

Recolecta métricas sobre:
- Volumen de items procesados
- Distribución de decisiones
- Impacto del learning y presets
- Esfuerzo humano evitado
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from pathlib import Path
import json

from backend.config import DATA_DIR


class RunMetricsV1(BaseModel):
    """Métricas operativas de un run/plan."""
    run_id: Optional[str] = Field(None, description="ID del run (si es ejecución)")
    plan_id: str = Field(..., description="ID del plan")
    total_items: int = Field(0, description="Total de items en el plan")
    decisions_count: Dict[str, int] = Field(
        default_factory=lambda: {
            "AUTO_UPLOAD": 0,
            "REVIEW_REQUIRED": 0,
            "NO_MATCH": 0,
            "SKIP": 0,
        },
        description="Conteo de decisiones por tipo"
    )
    source_breakdown: Dict[str, int] = Field(
        default_factory=lambda: {
            "auto_matching": 0,
            "learning_hint_resolved": 0,
            "preset_applied": 0,
            "manual_single": 0,
            "manual_batch": 0,
        },
        description="Conteo de decisiones por origen"
    )
    timestamps: Dict[str, Optional[str]] = Field(
        default_factory=lambda: {
            "plan_created_at": None,
            "decision_pack_created_at": None,
            "execution_started_at": None,
            "execution_finished_at": None,
        },
        description="Timestamps clave del flujo"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp de creación de métricas"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp de última actualización"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a dict para serialización JSON."""
        return {
            "run_id": self.run_id,
            "plan_id": self.plan_id,
            "total_items": self.total_items,
            "decisions_count": self.decisions_count,
            "source_breakdown": self.source_breakdown,
            "timestamps": self.timestamps,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunMetricsV1":
        """Crea desde dict (deserialización JSON)."""
        # Convertir timestamps ISO a datetime
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
        
        return cls(**data)


def initialize_metrics(plan_id: str, total_items: int, base_dir: Path = None) -> RunMetricsV1:
    """
    Inicializa métricas para un plan.
    
    Args:
        plan_id: ID del plan
        total_items: Total de items en el plan
        base_dir: Directorio base (default: DATA_DIR)
    
    Returns:
        RunMetricsV1 inicializado
    """
    base = Path(base_dir) if base_dir else Path(DATA_DIR)
    metrics = RunMetricsV1(
        plan_id=plan_id,
        total_items=total_items,
    )
    metrics.timestamps["plan_created_at"] = datetime.now(timezone.utc).isoformat()
    
    # Guardar
    save_metrics(metrics, base_dir=base)
    
    return metrics


def load_metrics(plan_id: str, base_dir: Path = None) -> Optional[RunMetricsV1]:
    """
    Carga métricas de un plan.
    
    Args:
        plan_id: ID del plan
        base_dir: Directorio base (default: DATA_DIR)
    
    Returns:
        RunMetricsV1 o None si no existe
    """
    base = Path(base_dir) if base_dir else Path(DATA_DIR)
    metrics_path = base / "runs" / plan_id / "metrics.json"
    
    if not metrics_path.exists():
        return None
    
    try:
        with open(metrics_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return RunMetricsV1.from_dict(data)
    except Exception as e:
        print(f"[RunMetrics] Error loading metrics: {e}")
        return None


def save_metrics(metrics: RunMetricsV1, base_dir: Path = None) -> Path:
    """
    Guarda métricas de un plan.
    
    Args:
        metrics: Métricas a guardar
        base_dir: Directorio base (default: DATA_DIR)
    
    Returns:
        Path al archivo guardado
    """
    base = Path(base_dir) if base_dir else Path(DATA_DIR)
    metrics_path = base / "runs" / metrics.plan_id / "metrics.json"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Actualizar updated_at
    metrics.updated_at = datetime.now(timezone.utc)
    
    # Guardar
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics.to_dict(), f, indent=2, ensure_ascii=False)
    
    return metrics_path


def update_metrics_from_decisions(
    plan_id: str,
    decisions: List[Dict[str, Any]],
    source: str = "auto_matching",
    base_dir: Path = None,
) -> RunMetricsV1:
    """
    Actualiza métricas desde decisiones del plan.
    
    Args:
        plan_id: ID del plan
        decisions: Lista de decisiones
        source: Origen de las decisiones ("auto_matching", "learning_hint_resolved", "preset_applied", "manual_single", "manual_batch")
        base_dir: Directorio base (default: DATA_DIR)
    
    Returns:
        RunMetricsV1 actualizado
    """
    metrics = load_metrics(plan_id, base_dir=base_dir)
    if not metrics:
        # Inicializar si no existe
        metrics = initialize_metrics(plan_id, len(decisions), base_dir=base_dir)
    
    # Actualizar conteos
    for decision in decisions:
        decision_type = decision.get("decision", "UNKNOWN")
        if decision_type in metrics.decisions_count:
            metrics.decisions_count[decision_type] += 1
        
        # Actualizar source_breakdown
        if source in metrics.source_breakdown:
            metrics.source_breakdown[source] += 1
    
    # Guardar
    save_metrics(metrics, base_dir=base_dir)
    
    return metrics


def record_decision_pack_created(plan_id: str, base_dir: Path = None) -> None:
    """Registra que se creó un decision pack."""
    metrics = load_metrics(plan_id, base_dir=base_dir)
    if metrics:
        metrics.timestamps["decision_pack_created_at"] = datetime.now(timezone.utc).isoformat()
        save_metrics(metrics, base_dir=base_dir)


def record_execution_started(plan_id: str, run_id: str, base_dir: Path = None) -> None:
    """Registra que comenzó la ejecución."""
    metrics = load_metrics(plan_id, base_dir=base_dir)
    if metrics:
        metrics.run_id = run_id
        metrics.timestamps["execution_started_at"] = datetime.now(timezone.utc).isoformat()
        save_metrics(metrics, base_dir=base_dir)


def record_execution_finished(plan_id: str, base_dir: Path = None) -> None:
    """Registra que finalizó la ejecución."""
    metrics = load_metrics(plan_id, base_dir=base_dir)
    if metrics:
        metrics.timestamps["execution_finished_at"] = datetime.now(timezone.utc).isoformat()
        save_metrics(metrics, base_dir=base_dir)


def record_learning_hint_applied(plan_id: str, count: int = 1, base_dir: Path = None) -> None:
    """Registra que se aplicaron hints de learning."""
    metrics = load_metrics(plan_id, base_dir=base_dir)
    if metrics:
        metrics.source_breakdown["learning_hint_resolved"] += count
        save_metrics(metrics, base_dir=base_dir)


def record_preset_applied(plan_id: str, count: int = 1, base_dir: Path = None) -> None:
    """Registra que se aplicaron presets."""
    metrics = load_metrics(plan_id, base_dir=base_dir)
    if metrics:
        metrics.source_breakdown["preset_applied"] += count
        save_metrics(metrics, base_dir=base_dir)


def record_manual_decision(plan_id: str, is_batch: bool = False, base_dir: Path = None) -> None:
    """Registra una decisión manual."""
    metrics = load_metrics(plan_id, base_dir=base_dir)
    if metrics:
        source = "manual_batch" if is_batch else "manual_single"
        metrics.source_breakdown[source] += 1
        save_metrics(metrics, base_dir=base_dir)
