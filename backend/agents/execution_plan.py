"""
ExecutionPlan: Plan de ejecución estructurado antes de la ejecución real.

v2.8.0: Permite al usuario ver y confirmar el plan antes de ejecutar.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class PlannedSubGoal:
    """
    Representa un sub-objetivo planificado con sus detalles.
    
    v2.8.0: Contiene información sobre estrategia, acciones esperadas,
    documentos necesarios y si puede tener retries.
    """
    index: int
    sub_goal: str
    strategy: str  # "wikipedia", "images", "cae", "other"
    expected_actions: List[str]  # e.g. ["navigate", "upload_file", "verify_upload"]
    documents_needed: List[str]  # Solo nombres de archivo, NO paths
    may_retry: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializa a dict para JSON."""
        return {
            "index": self.index,
            "sub_goal": self.sub_goal,
            "strategy": self.strategy,
            "expected_actions": self.expected_actions,
            "documents_needed": self.documents_needed,
            "may_retry": self.may_retry,
        }


@dataclass
class ExecutionPlan:
    """
    Plan de ejecución completo antes de la ejecución real.
    
    v2.8.0: Contiene toda la información necesaria para que el usuario
    pueda revisar y confirmar antes de ejecutar.
    """
    goal: str
    execution_profile: Dict[str, Any]
    context_strategies: List[str]
    sub_goals: List[PlannedSubGoal]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializa a dict para JSON."""
        return {
            "goal": self.goal,
            "execution_profile": self.execution_profile,
            "context_strategies": self.context_strategies,
            "sub_goals": [sg.to_dict() for sg in self.sub_goals],
        }















