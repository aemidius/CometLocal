"""
RL Engine: Motor de aprendizaje por refuerzo simplificado.

v5.1.0: Construye estados, sugiere acciones y actualiza políticas RL.
"""

import logging
import random
from typing import Optional, List, Dict, Any, Tuple

from backend.rl.rl_memory import RLMemory
from backend.shared.models import RLPolicy, RLStateActionValue
from backend.agents.dom_explorer import DOMSnapshot
from backend.agents.visual_explorer import VisualSnapshot
from backend.agents.hybrid_planner import PlannerNode

logger = logging.getLogger(__name__)


class RLEngine:
    """
    Motor de aprendizaje por refuerzo simplificado.
    
    v5.1.0: Construye estados, sugiere acciones y actualiza políticas.
    """
    
    def __init__(
        self,
        rl_memory: Optional[RLMemory] = None,
        exploration_rate: float = 0.30,
        learning_rate: float = 0.10,
        discount_factor: float = 0.85,
    ):
        """
        Inicializa el motor RL.
        
        Args:
            rl_memory: Gestor de memoria RL (se crea uno nuevo si es None)
            exploration_rate: Tasa de exploración (0.0 a 1.0)
            learning_rate: Tasa de aprendizaje (default: 0.1)
            discount_factor: Factor de descuento (default: 0.85)
        """
        self.memory = rl_memory or RLMemory()
        self.exploration_rate = exploration_rate
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        
        self.current_platform: Optional[str] = None
        self.current_policy: Optional[RLPolicy] = None
    
    def set_platform(self, platform: str):
        """
        Establece la plataforma actual y carga su política.
        
        Args:
            platform: Nombre de la plataforma
        """
        self.current_platform = platform
        self.current_policy = self.memory.load_policy(platform)
        
        if self.current_policy is None:
            self.current_policy = RLPolicy(platform=platform, q_table=[])
            logger.debug(f"[rl-engine] Created new policy for platform: {platform}")
        else:
            logger.debug(f"[rl-engine] Loaded policy for {platform}: {len(self.current_policy.q_table)} Q-values")
    
    def build_state(
        self,
        dom_snapshot: Optional[DOMSnapshot] = None,
        visual_snapshot: Optional[VisualSnapshot] = None,
        current_node: Optional[PlannerNode] = None,
        memory_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Construye un estado simbólico compacto.
        
        Args:
            dom_snapshot: Snapshot del DOM
            visual_snapshot: Snapshot visual
            current_node: Nodo actual del planner
            memory_context: Contexto de memoria opcional
            
        Returns:
            Estado simbólico (ej: "page:upload", "modal:confirmation")
        """
        state_parts = []
        
        # Detectar tipo de página
        if dom_snapshot:
            if dom_snapshot.forms:
                state_parts.append("page:form")
            if dom_snapshot.cae_keywords_found:
                state_parts.append("page:cae")
            if dom_snapshot.tables:
                state_parts.append("page:table")
        
        if visual_snapshot:
            if visual_snapshot.modals_detected:
                state_parts.append("modal:detected")
            if visual_snapshot.forms_detected:
                state_parts.append("form:visual")
            if visual_snapshot.cae_keywords_found:
                state_parts.append("cae:visual")
        
        # Tipo de nodo actual
        if current_node:
            node_type = current_node.type
            if node_type == "explore_dom":
                state_parts.append("state:exploring_dom")
            elif node_type == "explore_visual":
                state_parts.append("state:exploring_visual")
            elif node_type == "detect_forms":
                state_parts.append("state:detecting_forms")
            elif node_type == "detect_buttons":
                state_parts.append("state:detecting_buttons")
            elif node_type == "fill_form":
                state_parts.append("state:filling_form")
            elif node_type == "upload_file":
                state_parts.append("state:uploading")
            elif node_type == "navigate":
                state_parts.append("state:navigating")
            elif node_type == "confirm":
                state_parts.append("state:confirming")
        
        # Contexto de memoria
        if memory_context:
            if memory_context.get("missing_fields"):
                state_parts.append("state:missing_fields")
            if memory_context.get("errors"):
                state_parts.append("state:errors")
        
        # Si no hay partes, usar estado genérico
        if not state_parts:
            state_parts.append("state:unknown")
        
        # Construir estado final
        state = ":".join(state_parts[:3])  # Limitar a 3 partes para mantener compacto
        
        return state
    
    def suggest_action(
        self,
        state: str,
        available_nodes: List[PlannerNode],
        platform: Optional[str] = None,
    ) -> Optional[str]:
        """
        Sugiere una acción basándose en la política RL.
        
        Args:
            state: Estado actual
            available_nodes: Nodos disponibles del planner
            platform: Plataforma (usa current_platform si es None)
            
        Returns:
            ID del nodo sugerido o None
        """
        if platform:
            self.set_platform(platform)
        
        if not self.current_platform:
            logger.warning("[rl-engine] No platform set, cannot suggest action")
            return None
        
        # Obtener mejor acción según política
        best_action = self.memory.get_best_action(self.current_platform, state)
        
        # Decidir entre exploración y explotación
        if random.random() < self.exploration_rate or best_action is None:
            # Explorar: seleccionar nodo aleatorio
            if available_nodes:
                exploration_node = random.choice(available_nodes)
                logger.debug(f"[rl-engine] Exploration: selected node {exploration_node.node_id}")
                return exploration_node.node_id
            return None
        else:
            # Explotar: usar mejor acción conocida
            # Buscar nodo que coincida con la acción
            for node in available_nodes:
                if node.node_id == best_action or node.type in best_action:
                    logger.debug(f"[rl-engine] Exploitation: selected node {node.node_id} (Q-value: {best_action})")
                    return node.node_id
            
            # Si no hay coincidencia exacta, usar mejor nodo disponible
            if available_nodes:
                logger.debug(f"[rl-engine] Best action not available, using first available node")
                return available_nodes[0].node_id
        
        return None
    
    def calculate_reward(
        self,
        node_result: Any,
        visual_success: bool = False,
        contract_match: bool = False,
        retry_count: int = 0,
        violation_detected: bool = False,
        steps_saved: int = 0,
    ) -> float:
        """
        Calcula la recompensa para una transición.
        
        Args:
            node_result: Resultado de ejecución del nodo
            visual_success: Si hubo éxito visual
            contract_match: Si el contrato visual coincide
            retry_count: Número de reintentos
            violation_detected: Si se detectó una violación
            steps_saved: Pasos ahorrados
            
        Returns:
            Recompensa entre -1.0 y +1.0
        """
        reward = 0.0
        
        # Recompensas positivas
        if visual_success and contract_match:
            reward += 1.0  # Éxito completo
        elif visual_success:
            reward += 0.5  # Éxito parcial
        elif contract_match:
            reward += 0.3  # Contrato coincide
        
        # Recompensas por nodos específicos
        if hasattr(node_result, 'node_id'):
            if "upload_complete" in node_result.node_id or "upload" in node_result.node_id:
                if node_result.success:
                    reward += 0.8
        
        # Bonus por ahorro de pasos
        if steps_saved > 0:
            reward += min(0.2, steps_saved * 0.05)
        
        # Penalizaciones
        if violation_detected:
            reward -= 1.0  # Violación grave
        elif retry_count > 0:
            reward -= 0.5 * min(retry_count, 2)  # Penalización por retries
        elif not visual_success and not contract_match:
            reward -= 0.3  # Mismatch
        
        # Limitar entre -1.0 y +1.0
        reward = max(-1.0, min(1.0, reward))
        
        return reward
    
    def update_from_result(
        self,
        state: str,
        action: str,
        node_result: Any,
        visual_success: bool = False,
        contract_match: bool = False,
        retry_count: int = 0,
        violation_detected: bool = False,
        steps_saved: int = 0,
        platform: Optional[str] = None,
    ) -> bool:
        """
        Actualiza la política RL basándose en el resultado.
        
        Args:
            state: Estado en el que se tomó la acción
            action: Acción tomada (node_id)
            node_result: Resultado de ejecución del nodo
            visual_success: Si hubo éxito visual
            contract_match: Si el contrato visual coincide
            retry_count: Número de reintentos
            violation_detected: Si se detectó una violación
            steps_saved: Pasos ahorrados
            platform: Plataforma (usa current_platform si es None)
            
        Returns:
            True si se actualizó correctamente
        """
        if platform:
            self.set_platform(platform)
        
        if not self.current_platform:
            logger.warning("[rl-engine] No platform set, cannot update policy")
            return False
        
        # Calcular recompensa
        reward = self.calculate_reward(
            node_result=node_result,
            visual_success=visual_success,
            contract_match=contract_match,
            retry_count=retry_count,
            violation_detected=violation_detected,
            steps_saved=steps_saved,
        )
        
        # Determinar éxito
        success = (
            hasattr(node_result, 'success') and node_result.success
        ) or visual_success
        
        # Registrar transición
        return self.memory.record_transition(
            platform=self.current_platform,
            state=state,
            action=action,
            success=success,
            reward=reward,
            extra={
                "visual_success": visual_success,
                "contract_match": contract_match,
                "retry_count": retry_count,
            },
        )
    
    def get_policy_stats(self, platform: Optional[str] = None) -> Dict[str, Any]:
        """
        Obtiene estadísticas de la política actual.
        
        Args:
            platform: Plataforma (usa current_platform si es None)
            
        Returns:
            Dict con estadísticas
        """
        if platform:
            self.set_platform(platform)
        
        if not self.current_platform or not self.current_policy:
            return {}
        
        q_table = self.current_policy.q_table
        
        if not q_table:
            return {"total_q_values": 0}
        
        positive_rewards = sum(1 for q in q_table if q.value > 0)
        negative_rewards = sum(1 for q in q_table if q.value < 0)
        total_visits = sum(q.visits for q in q_table)
        
        return {
            "total_q_values": len(q_table),
            "positive_rewards": positive_rewards,
            "negative_rewards": negative_rewards,
            "total_visits": total_visits,
            "avg_value": sum(q.value for q in q_table) / len(q_table),
            "states_known": len(set(q.state for q in q_table)),
        }
















