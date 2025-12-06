"""
ExecutionProfile: Perfiles de ejecución para controlar el comportamiento del agente.
v1.9.0: Permite controlar profundidad, pasos máximos, tipos de objetivos y condiciones de parada.
"""
from dataclasses import dataclass
from typing import Optional
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExecutionProfile:
    """
    Perfil de ejecución que controla el comportamiento del agente.
    v1.9.0: Permite ajustar parámetros de ejecución sin modificar la lógica base.
    """
    mode: str = "balanced"  # "fast" | "balanced" | "thorough"
    max_steps_per_subgoal: Optional[int] = None  # None = usar max_steps del parámetro
    allow_wikipedia: bool = True
    allow_images: bool = True
    stop_on_first_success: bool = False
    confidence_threshold: Optional[float] = None  # No usado aún, preparado para futuro
    allow_auto_form_fill: bool = True  # v4.6.0: Permitir mapeo automático de formularios
    use_hybrid_planner: bool = False  # v5.0.0: Usar planificador híbrido autónomo
    use_rl_learning: bool = True  # v5.1.0: Usar aprendizaje por refuerzo
    rl_policy_exploration_rate: float = 0.30  # v5.1.0: Tasa de exploración RL (0.0 a 1.0)
    rl_policy_learning_rate: float = 0.10  # v5.1.0: Tasa de aprendizaje RL
    rl_policy_discount_factor: float = 0.85  # v5.1.0: Factor de descuento RL
    use_visual_heatmap: bool = True  # v5.2.0: Usar memoria visual (heatmaps y landmarks)
    visual_memory_max_clicks_per_recovery: int = 2  # v5.2.0: Máximo clicks extra basados en memoria
    
    @classmethod
    def default(cls) -> "ExecutionProfile":
        """Crea un perfil por defecto (balanced)."""
        return cls()
    
    @classmethod
    def fast(cls) -> "ExecutionProfile":
        """Crea un perfil rápido (menos pasos, parada temprana)."""
        return cls(
            mode="fast",
            max_steps_per_subgoal=4,
            stop_on_first_success=True,
        )
    
    @classmethod
    def thorough(cls) -> "ExecutionProfile":
        """Crea un perfil exhaustivo (más pasos, sin parada temprana)."""
        return cls(
            mode="thorough",
            max_steps_per_subgoal=12,
            stop_on_first_success=False,
        )
    
    @classmethod
    def from_goal_text(cls, goal: str) -> "ExecutionProfile":
        """
        Infiere un ExecutionProfile a partir del texto del objetivo.
        v1.9.0: Detecta palabras clave para ajustar el comportamiento.
        
        Palabras clave detectadas:
        - "rápido", "breve", "en resumen", "resumen" → fast
        - "exhaustivo", "en detalle", "a fondo", "detallado" → thorough
        - "solo wikipedia", "solo wikipedia" → allow_images = False
        - "máx X pasos", "máximo X pasos", "max X pasos" → max_steps_per_subgoal = X
        
        Args:
            goal: Texto del objetivo del usuario
            
        Returns:
            ExecutionProfile inferido o default si no se detecta nada
        """
        goal_lower = goal.lower()
        profile = cls.default()
        
        # Detectar modo fast
        fast_keywords = [
            r"\brápido\b", r"\brápidamente\b", r"\bbreve\b", r"\ben resumen\b", r"\bresumen\b",
            r"\bquick\b", r"\bquickly\b", r"\bbrief\b", r"\bsummary\b",
        ]
        if any(re.search(keyword, goal_lower) for keyword in fast_keywords):
            profile = cls.fast()
            logger.debug("[profile] inferred mode=fast from goal text")
        
        # Detectar modo thorough
        thorough_keywords = [
            r"\bexhaustivo\b", r"\bexhaustivamente\b", r"\ben detalle\b", r"\bdetallado\b", r"\bdetallada\b",
            r"\ba fondo\b", r"\bthorough\b", r"\bdetailed\b", r"\bin depth\b",
        ]
        if any(re.search(keyword, goal_lower) for keyword in thorough_keywords):
            profile = cls.thorough()
            logger.debug("[profile] inferred mode=thorough from goal text")
        
        # Detectar restricción de imágenes
        no_images_keywords = [
            r"\bsolo wikipedia\b", r"\bsólo wikipedia\b", r"\bsolo en wikipedia\b",
            r"\bonly wikipedia\b", r"\bno imágenes\b", r"\bsin imágenes\b",
        ]
        if any(re.search(keyword, goal_lower) for keyword in no_images_keywords):
            profile.allow_images = False
            logger.debug("[profile] inferred allow_images=False from goal text")
        
        # Detectar restricción de Wikipedia
        no_wikipedia_keywords = [
            r"\bsolo imágenes\b", r"\bsólo imágenes\b", r"\bonly images\b",
            r"\bno wikipedia\b", r"\bsin wikipedia\b",
        ]
        if any(re.search(keyword, goal_lower) for keyword in no_wikipedia_keywords):
            profile.allow_wikipedia = False
            logger.debug("[profile] inferred allow_wikipedia=False from goal text")
        
        # Detectar límite explícito de pasos
        # Patrones: "máx 5 pasos", "máximo 3 pasos", "max 10 pasos"
        step_patterns = [
            r"\bmáx(?:imo)?\s+(\d+)\s+pasos?\b",
            r"\bmax(?:imum)?\s+(\d+)\s+steps?\b",
            r"\b(\d+)\s+pasos?\s+máx(?:imo)?\b",
        ]
        for pattern in step_patterns:
            match = re.search(pattern, goal_lower)
            if match:
                try:
                    max_steps = int(match.group(1))
                    if 1 <= max_steps <= 20:  # Límite razonable
                        profile.max_steps_per_subgoal = max_steps
                        logger.debug(f"[profile] inferred max_steps_per_subgoal={max_steps} from goal text")
                        break
                except (ValueError, IndexError):
                    pass
        
        return profile
    
    def get_effective_max_steps(self, default_max_steps: int) -> int:
        """
        Obtiene el número máximo de pasos efectivo a usar.
        
        Args:
            default_max_steps: Valor por defecto si max_steps_per_subgoal es None
            
        Returns:
            max_steps_per_subgoal si está definido, sino default_max_steps
        """
        if self.max_steps_per_subgoal is not None:
            return self.max_steps_per_subgoal
        return default_max_steps
    
    def should_skip_goal(self, goal: str) -> bool:
        """
        Determina si un objetivo debe ser saltado según las restricciones del perfil.
        
        Args:
            goal: Texto del objetivo a evaluar
            
        Returns:
            True si el objetivo debe ser saltado, False en caso contrario
        """
        goal_lower = goal.lower()
        
        # Saltar objetivos de imágenes si allow_images=False
        if not self.allow_images:
            if _goal_mentions_images(goal):
                logger.debug(f"[profile] skipping image goal (allow_images=False): {goal[:50]}")
                return True
        
        # Saltar objetivos de Wikipedia si allow_wikipedia=False
        if not self.allow_wikipedia:
            if _goal_mentions_wikipedia(goal):
                logger.debug(f"[profile] skipping wikipedia goal (allow_wikipedia=False): {goal[:50]}")
                return True
        
        return False
    
    def to_dict(self) -> dict:
        """
        Serializa el perfil a un diccionario para logging/métricas.
        
        Returns:
            Dict con los campos del perfil
        """
        return {
            "mode": self.mode,
            "max_steps_per_subgoal": self.max_steps_per_subgoal,
            "allow_wikipedia": self.allow_wikipedia,
            "allow_images": self.allow_images,
            "stop_on_first_success": self.stop_on_first_success,
            "confidence_threshold": self.confidence_threshold,
            "allow_auto_form_fill": self.allow_auto_form_fill,  # v4.6.0
        }


# Importar helpers necesarios (evitar import circular)
def _goal_mentions_images(goal: str) -> bool:
    """Helper para detectar si un objetivo menciona imágenes."""
    from backend.agents.agent_runner import _goal_mentions_images as _check_images
    return _check_images(goal)


def _goal_mentions_wikipedia(goal: str) -> bool:
    """Helper para detectar si un objetivo menciona Wikipedia."""
    from backend.agents.agent_runner import _goal_mentions_wikipedia as _check_wikipedia
    return _check_wikipedia(goal)

