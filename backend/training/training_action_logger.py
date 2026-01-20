"""
SPRINT C2.35: Logger de acciones asistidas (append-only).

Registra todas las acciones asistidas en un log JSONL para auditoría.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional


def log_training_action(
    action: str,
    type_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    base_dir: str | Path = "data"
) -> None:
    """
    Registra una acción asistida en el log.
    
    Args:
        action: Tipo de acción ("assign_existing_type" | "create_new_type")
        type_id: ID del tipo afectado (opcional)
        details: Detalles adicionales de la acción
        base_dir: Directorio base para el log
    """
    log_file = Path(base_dir) / "training" / "actions.log.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "type_id": type_id,
        "details": details or {}
    }
    
    try:
        # Append-only: añadir al final del archivo
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        # No fallar si no se puede escribir el log
        print(f"[TrainingActionLogger] Error writing log: {e}")
