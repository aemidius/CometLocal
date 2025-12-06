"""
RL Memory: Almacenamiento persistente de políticas de aprendizaje por refuerzo.

v5.1.0: Gestiona la carga y guardado de políticas RL en memoria local.
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from backend.shared.models import RLPolicy, RLStateActionValue
from backend.config import MEMORY_BASE_DIR

logger = logging.getLogger(__name__)


class RLMemory:
    """
    Gestor de memoria para políticas de aprendizaje por refuerzo.
    
    v5.1.0: Carga y guarda políticas RL en archivos JSON locales.
    """
    
    def __init__(self, base_dir: Optional[Path] = None):
        """
        Inicializa el gestor de memoria RL.
        
        Args:
            base_dir: Directorio base para almacenar políticas (default: memory/rl/)
        """
        if base_dir is None:
            base_dir = Path(MEMORY_BASE_DIR) / "rl"
        else:
            base_dir = Path(base_dir) / "rl"
        
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"[rl-memory] Initialized with base_dir: {self.base_dir}")
    
    def _get_policy_path(self, platform: str) -> Path:
        """
        Obtiene la ruta del archivo de política para una plataforma.
        
        Args:
            platform: Nombre de la plataforma
            
        Returns:
            Path al archivo JSON
        """
        # Normalizar nombre de plataforma para usar como nombre de archivo
        safe_platform = platform.replace(" ", "_").replace("/", "_").lower()
        return self.base_dir / f"{safe_platform}.json"
    
    def load_policy(self, platform: str) -> Optional[RLPolicy]:
        """
        Carga una política desde disco.
        
        Args:
            platform: Nombre de la plataforma
            
        Returns:
            RLPolicy cargada o None si no existe
        """
        policy_path = self._get_policy_path(platform)
        
        if not policy_path.exists():
            logger.debug(f"[rl-memory] No policy found for platform: {platform}")
            return None
        
        try:
            with open(policy_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Convertir lista de dicts a RLStateActionValue
            q_table = [
                RLStateActionValue(**item) for item in data.get("q_table", [])
            ]
            
            policy = RLPolicy(
                platform=data.get("platform", platform),
                q_table=q_table,
                last_updated=data.get("last_updated"),
            )
            
            logger.info(f"[rl-memory] Loaded policy for {platform}: {len(q_table)} Q-values")
            return policy
        
        except Exception as e:
            logger.warning(f"[rl-memory] Error loading policy for {platform}: {e}")
            return None
    
    def save_policy(self, platform: str, policy: RLPolicy) -> bool:
        """
        Guarda una política en disco.
        
        Args:
            platform: Nombre de la plataforma
            policy: Política a guardar
            
        Returns:
            True si se guardó correctamente
        """
        policy_path = self._get_policy_path(platform)
        
        try:
            # Actualizar timestamp
            policy.last_updated = datetime.now().isoformat()
            
            # Convertir a dict
            data = {
                "platform": policy.platform,
                "q_table": [item.model_dump() for item in policy.q_table],
                "last_updated": policy.last_updated,
            }
            
            # Guardar JSON
            with open(policy_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[rl-memory] Saved policy for {platform}: {len(policy.q_table)} Q-values")
            return True
        
        except Exception as e:
            logger.error(f"[rl-memory] Error saving policy for {platform}: {e}", exc_info=True)
            return False
    
    def update_q_value(
        self,
        platform: str,
        state: str,
        action: str,
        reward: float,
        learning_rate: float = 0.1,
        discount_factor: float = 0.85,
    ) -> bool:
        """
        Actualiza un Q-value en la política.
        
        Args:
            platform: Nombre de la plataforma
            state: Estado actual
            action: Acción tomada
            reward: Recompensa recibida (-1.0 a +1.0)
            learning_rate: Tasa de aprendizaje (default: 0.1)
            discount_factor: Factor de descuento (default: 0.85)
            
        Returns:
            True si se actualizó correctamente
        """
        # Cargar política existente o crear nueva
        policy = self.load_policy(platform)
        if policy is None:
            policy = RLPolicy(platform=platform, q_table=[])
        
        # Buscar Q-value existente
        q_value = None
        for q in policy.q_table:
            if q.state == state and q.action == action:
                q_value = q
                break
        
        # Si no existe, crear nuevo
        if q_value is None:
            q_value = RLStateActionValue(
                state=state,
                action=action,
                value=0.0,
                visits=0,
                success_rate=0.0,
            )
            policy.q_table.append(q_value)
        
        # Actualizar Q-value usando fórmula Q-learning simplificada
        # Q(s,a) = Q(s,a) + α * (reward + γ * max(Q(s',a')) - Q(s,a))
        # Para simplificar, usamos: Q(s,a) = Q(s,a) + α * reward
        old_value = q_value.value
        q_value.value = old_value + learning_rate * (reward - old_value)
        
        # Actualizar visitas
        q_value.visits += 1
        
        # Actualizar success_rate basándose en reward
        if reward > 0:
            # Recompensa positiva incrementa success_rate
            q_value.success_rate = min(1.0, q_value.success_rate + learning_rate * reward)
        else:
            # Recompensa negativa la reduce
            q_value.success_rate = max(0.0, q_value.success_rate + learning_rate * reward)
        
        # Guardar política actualizada
        return self.save_policy(platform, policy)
    
    def get_best_action(self, platform: str, state: str) -> Optional[str]:
        """
        Obtiene la mejor acción para un estado según la política.
        
        Args:
            platform: Nombre de la plataforma
            state: Estado actual
            
        Returns:
            Mejor acción o None si no hay datos
        """
        policy = self.load_policy(platform)
        if policy is None:
            return None
        
        # Buscar todas las acciones para este estado
        state_actions = [q for q in policy.q_table if q.state == state]
        
        if not state_actions:
            return None
        
        # Seleccionar acción con mayor Q-value
        best_q = max(state_actions, key=lambda q: q.value)
        return best_q.action
    
    def record_transition(
        self,
        platform: str,
        state: str,
        action: str,
        success: bool,
        reward: float,
        extra: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Registra una transición y actualiza Q-values.
        
        Args:
            platform: Nombre de la plataforma
            state: Estado actual
            action: Acción tomada
            success: Si la acción fue exitosa
            reward: Recompensa recibida
            extra: Información adicional opcional
            
        Returns:
            True si se registró correctamente
        """
        # Ajustar reward basándose en success
        if success and reward > 0:
            adjusted_reward = reward
        elif success:
            adjusted_reward = 0.3  # Bonus por éxito aunque reward sea bajo
        else:
            adjusted_reward = min(reward, -0.3)  # Penalización por fallo
        
        # Actualizar Q-value
        return self.update_q_value(
            platform=platform,
            state=state,
            action=action,
            reward=adjusted_reward,
        )
    
    def get_all_states(self, platform: str) -> List[str]:
        """
        Obtiene todos los estados conocidos para una plataforma.
        
        Args:
            platform: Nombre de la plataforma
            
        Returns:
            Lista de estados únicos
        """
        policy = self.load_policy(platform)
        if policy is None:
            return []
        
        states = set(q.state for q in policy.q_table)
        return sorted(list(states))
    
    def get_state_action_stats(self, platform: str, state: str) -> Dict[str, Any]:
        """
        Obtiene estadísticas de acciones para un estado.
        
        Args:
            platform: Nombre de la plataforma
            state: Estado
            
        Returns:
            Dict con estadísticas
        """
        policy = self.load_policy(platform)
        if policy is None:
            return {}
        
        state_actions = [q for q in policy.q_table if q.state == state]
        
        if not state_actions:
            return {}
        
        return {
            "total_actions": len(state_actions),
            "best_action": max(state_actions, key=lambda q: q.value).action,
            "best_value": max(q.value for q in state_actions),
            "avg_value": sum(q.value for q in state_actions) / len(state_actions),
            "total_visits": sum(q.visits for q in state_actions),
        }

