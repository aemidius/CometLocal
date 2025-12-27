"""
SessionContext: Memoria de contexto persistente por sesión.
v1.7.0: Gestión de entidades y referencias implícitas durante una ejecución.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class SessionContext:
    """
    Contexto de sesión para mantener memoria de entidades y referencias durante una ejecución.
    v1.7.0: Permite resolver pronombres y referencias implícitas sin usar LLM.
    """
    # Entidad "principal" más reciente (persona, empresa, etc.)
    current_focus_entity: Optional[str] = None
    
    # Última entidad válida confirmada (para fallback)
    last_valid_entity: Optional[str] = None
    
    # Historial ligero de entidades relevantes (en orden)
    entity_history: List[str] = field(default_factory=list)
    
    # Último goal y sub-goal ejecutados
    last_goal: Optional[str] = None
    last_sub_goal: Optional[str] = None
    
    def update_entity(self, entity: Optional[str]) -> None:
        """
        Actualiza el contexto si entity es válida:
        - current_focus_entity
        - last_valid_entity
        - entity_history (sin duplicados consecutivos)
        
        Args:
            entity: Entidad a añadir al contexto (None se ignora)
        """
        if not entity or not entity.strip():
            return
        
        entity = entity.strip()
        
        # Actualizar current_focus_entity
        self.current_focus_entity = entity
        
        # Actualizar last_valid_entity
        self.last_valid_entity = entity
        
        # Añadir a entity_history solo si no es duplicado consecutivo
        if not self.entity_history or self.entity_history[-1] != entity:
            self.entity_history.append(entity)
            # Limitar historial a las últimas 10 entidades para evitar crecimiento ilimitado
            if len(self.entity_history) > 10:
                self.entity_history = self.entity_history[-10:]
        
        logger.debug(
            "[context] current_focus_entity updated to %r (history: %d entities)",
            entity,
            len(self.entity_history),
        )
    
    def resolve_entity_reference(self, goal: str) -> Optional[str]:
        """
        Resuelve referencias implícitas en el goal:
        - 'él', 'ella', 'suyo/suya/suyos/suyas'
        - 'esa persona', 'esa empresa'
        
        Prioridad:
        1) current_focus_entity
        2) last_valid_entity
        3) None
        
        Args:
            goal: Texto del objetivo que puede contener referencias implícitas
            
        Returns:
            Entidad resuelta o None si no hay contexto disponible
        """
        # Si hay current_focus_entity, usarla
        if self.current_focus_entity:
            logger.debug(
                "[context] resolved entity from pronoun in goal=%r → %r",
                goal[:50],
                self.current_focus_entity,
            )
            return self.current_focus_entity
        
        # Fallback a last_valid_entity
        if self.last_valid_entity:
            logger.debug(
                "[context] resolved entity from last_valid_entity in goal=%r → %r",
                goal[:50],
                self.last_valid_entity,
            )
            return self.last_valid_entity
        
        # Sin contexto disponible
        logger.debug("[context] no entity context available for goal=%r", goal[:50])
        return None
    
    def update_goal(self, goal: str, sub_goal: Optional[str] = None) -> None:
        """
        Actualiza el último goal y sub-goal ejecutados.
        
        Args:
            goal: Goal completo
            sub_goal: Sub-goal específico (opcional)
        """
        self.last_goal = goal
        self.last_sub_goal = sub_goal
    
    def to_debug_dict(self) -> Dict[str, Any]:
        """
        Devuelve el estado del contexto para logging/debug.
        
        Returns:
            Dict con el estado actual del contexto
        """
        return {
            "current_focus_entity": self.current_focus_entity,
            "last_valid_entity": self.last_valid_entity,
            "entity_history": self.entity_history.copy(),
            "last_goal": self.last_goal,
            "last_sub_goal": self.last_sub_goal,
        }





























