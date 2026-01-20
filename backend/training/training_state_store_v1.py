"""
SPRINT C2.35: Store persistente para estado de training guiado.

El training es obligatorio y debe completarse antes de desbloquear acciones asistidas.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone


class TrainingStateStoreV1:
    """Store para estado de training guiado."""
    
    def __init__(self, base_dir: str | Path = "data"):
        self.base_dir = Path(base_dir)
        self.state_file = self.base_dir / "training" / "state.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
    
    def get_state(self) -> Dict[str, Any]:
        """
        Obtiene el estado actual del training.
        
        Returns:
            {
                "training_completed": bool,
                "completed_at": str | None (ISO format),
                "version": str
            }
        """
        if not self.state_file.exists():
            # Por defecto: NOT COMPLETED
            return {
                "training_completed": False,
                "completed_at": None,
                "version": "C2.35"
            }
        
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            
            # Asegurar campos mínimos
            if "training_completed" not in state:
                state["training_completed"] = False
            if "completed_at" not in state:
                state["completed_at"] = None
            if "version" not in state:
                state["version"] = "C2.35"
            
            return state
        except Exception as e:
            # Si hay error leyendo, asumir NOT COMPLETED
            print(f"[TrainingState] Error reading state: {e}, defaulting to NOT COMPLETED")
            return {
                "training_completed": False,
                "completed_at": None,
                "version": "C2.35"
            }
    
    def mark_completed(self, confirm: bool = False) -> bool:
        """
        Marca el training como completado.
        
        Args:
            confirm: Debe ser True para confirmar explícitamente
        
        Returns:
            True si se marcó como completado, False si no se confirmó
        """
        if not confirm:
            return False
        
        state = self.get_state()
        
        # Si ya está completado, idempotente
        if state.get("training_completed"):
            return True
        
        # Marcar como completado
        state["training_completed"] = True
        state["completed_at"] = datetime.now(timezone.utc).isoformat()
        state["version"] = "C2.35"
        
        # Persistir
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[TrainingState] Error writing state: {e}")
            return False
    
    def is_training_completed(self) -> bool:
        """
        Helper para verificar si el training está completado.
        
        Returns:
            True si training_completed = True, False en caso contrario
        """
        state = self.get_state()
        return state.get("training_completed", False)


# Singleton global (opcional, para fácil acceso)
_global_store: Optional[TrainingStateStoreV1] = None


def get_training_store(base_dir: str | Path = "data") -> TrainingStateStoreV1:
    """Obtiene instancia global del store."""
    global _global_store
    if _global_store is None:
        _global_store = TrainingStateStoreV1(base_dir=base_dir)
    return _global_store


def is_training_completed(base_dir: str | Path = "data") -> bool:
    """Helper global para verificar si training está completado."""
    return get_training_store(base_dir).is_training_completed()
