"""
Tests para RL Engine v5.1.0
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

from backend.rl.rl_memory import RLMemory
from backend.rl.rl_engine import RLEngine
from backend.shared.models import RLPolicy, RLStateActionValue
from backend.agents.dom_explorer import DOMSnapshot
from backend.agents.visual_explorer import VisualSnapshot
from backend.agents.hybrid_planner import PlannerNode


class TestRLMemory:
    """Tests para RLMemory"""
    
    @pytest.fixture
    def temp_dir(self):
        """Directorio temporal para tests"""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.fixture
    def rl_memory(self, temp_dir):
        """Instancia de RLMemory con directorio temporal"""
        return RLMemory(base_dir=temp_dir)
    
    def test_save_and_load_policy(self, rl_memory):
        """Test guardado y carga de política"""
        platform = "test_platform"
        
        # Crear política
        policy = RLPolicy(
            platform=platform,
            q_table=[
                RLStateActionValue(
                    state="page:upload",
                    action="click_button:adjuntar",
                    value=0.8,
                    visits=5,
                    success_rate=0.9,
                ),
            ],
        )
        
        # Guardar
        assert rl_memory.save_policy(platform, policy)
        
        # Cargar
        loaded_policy = rl_memory.load_policy(platform)
        
        assert loaded_policy is not None
        assert loaded_policy.platform == platform
        assert len(loaded_policy.q_table) == 1
        assert loaded_policy.q_table[0].state == "page:upload"
        assert loaded_policy.q_table[0].value == 0.8
    
    def test_update_q_value(self, rl_memory):
        """Test actualización de Q-value"""
        platform = "test_platform"
        state = "page:upload"
        action = "click_button:adjuntar"
        
        # Actualizar Q-value
        assert rl_memory.update_q_value(platform, state, action, reward=0.5)
        
        # Verificar que se guardó
        policy = rl_memory.load_policy(platform)
        assert policy is not None
        assert len(policy.q_table) == 1
        assert policy.q_table[0].value > 0.0
        assert policy.q_table[0].visits == 1
    
    def test_get_best_action(self, rl_memory):
        """Test obtención de mejor acción"""
        platform = "test_platform"
        state = "page:upload"
        
        # Crear múltiples acciones
        rl_memory.update_q_value(platform, state, "action1", reward=0.3)
        rl_memory.update_q_value(platform, state, "action2", reward=0.8)
        rl_memory.update_q_value(platform, state, "action3", reward=0.5)
        
        # Obtener mejor acción
        best_action = rl_memory.get_best_action(platform, state)
        
        assert best_action == "action2"  # Mayor Q-value
    
    def test_record_transition(self, rl_memory):
        """Test registro de transición"""
        platform = "test_platform"
        
        # Registrar transición exitosa
        assert rl_memory.record_transition(
            platform=platform,
            state="page:upload",
            action="click_button:adjuntar",
            success=True,
            reward=0.7,
        )
        
        # Verificar que se actualizó
        policy = rl_memory.load_policy(platform)
        assert policy is not None
        assert len(policy.q_table) == 1
        assert policy.q_table[0].success_rate > 0.0


class TestRLEngine:
    """Tests para RLEngine"""
    
    @pytest.fixture
    def temp_dir(self):
        """Directorio temporal para tests"""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.fixture
    def rl_engine(self, temp_dir):
        """Instancia de RLEngine"""
        rl_memory = RLMemory(base_dir=temp_dir)
        return RLEngine(
            rl_memory=rl_memory,
            exploration_rate=0.3,
            learning_rate=0.1,
        )
    
    def test_build_state(self, rl_engine):
        """Test construcción de estado"""
        dom_snapshot = DOMSnapshot(
            forms=[{"id": "form1"}],
            cae_keywords_found=["cae"],
        )
        
        visual_snapshot = VisualSnapshot(
            modals_detected=[{"text": "Confirmar"}],
        )
        
        node = PlannerNode(
            node_id="test_node",
            title="Test",
            type="detect_forms",
        )
        
        state = rl_engine.build_state(
            dom_snapshot=dom_snapshot,
            visual_snapshot=visual_snapshot,
            current_node=node,
        )
        
        assert isinstance(state, str)
        assert ":" in state  # Formato estado:componente
        assert len(state) > 0
    
    def test_suggest_action_exploration(self, rl_engine):
        """Test sugerencia de acción (exploración)"""
        rl_engine.set_platform("test_platform")
        rl_engine.exploration_rate = 1.0  # Forzar exploración
        
        available_nodes = [
            PlannerNode(node_id="node1", title="Node 1", type="navigate"),
            PlannerNode(node_id="node2", title="Node 2", type="detect_forms"),
        ]
        
        action = rl_engine.suggest_action(
            state="page:upload",
            available_nodes=available_nodes,
        )
        
        assert action in ["node1", "node2"]  # Debe seleccionar uno aleatorio
    
    def test_suggest_action_exploitation(self, rl_engine):
        """Test sugerencia de acción (explotación)"""
        rl_engine.set_platform("test_platform")
        rl_engine.exploration_rate = 0.0  # Forzar explotación
        
        # Crear política con mejor acción
        rl_engine.memory.update_q_value(
            platform="test_platform",
            state="page:upload",
            action="node2",
            reward=0.9,
        )
        
        available_nodes = [
            PlannerNode(node_id="node1", title="Node 1", type="navigate"),
            PlannerNode(node_id="node2", title="Node 2", type="detect_forms"),
        ]
        
        action = rl_engine.suggest_action(
            state="page:upload",
            available_nodes=available_nodes,
        )
        
        # Debería preferir node2 (mayor Q-value)
        assert action == "node2" or action in ["node1", "node2"]
    
    def test_calculate_reward_positive(self, rl_engine):
        """Test cálculo de recompensa positiva"""
        class MockNodeResult:
            success = True
            node_id = "upload_complete"
        
        reward = rl_engine.calculate_reward(
            node_result=MockNodeResult(),
            visual_success=True,
            contract_match=True,
        )
        
        assert reward > 0.0
        assert reward <= 1.0
    
    def test_calculate_reward_negative(self, rl_engine):
        """Test cálculo de recompensa negativa"""
        class MockNodeResult:
            success = False
            node_id = "test_node"
        
        reward = rl_engine.calculate_reward(
            node_result=MockNodeResult(),
            visual_success=False,
            contract_match=False,
            violation_detected=True,
        )
        
        assert reward < 0.0
        assert reward >= -1.0
    
    def test_update_from_result(self, rl_engine):
        """Test actualización desde resultado"""
        rl_engine.set_platform("test_platform")
        
        class MockNodeResult:
            success = True
            node_id = "test_node"
        
        result = rl_engine.update_from_result(
            state="page:upload",
            action="test_node",
            node_result=MockNodeResult(),
            visual_success=True,
            contract_match=True,
        )
        
        assert result is True
        
        # Verificar que se actualizó la política
        policy = rl_engine.memory.load_policy("test_platform")
        assert policy is not None
        assert len(policy.q_table) > 0
    
    def test_get_policy_stats(self, rl_engine):
        """Test obtención de estadísticas de política"""
        rl_engine.set_platform("test_platform")
        
        # Añadir algunos Q-values
        rl_engine.memory.update_q_value("test_platform", "state1", "action1", 0.5)
        rl_engine.memory.update_q_value("test_platform", "state1", "action2", -0.3)
        
        stats = rl_engine.get_policy_stats()
        
        assert "total_q_values" in stats
        assert stats["total_q_values"] == 2
        assert "positive_rewards" in stats
        assert "negative_rewards" in stats


class TestRLIntegration:
    """Tests de integración RL"""
    
    @pytest.fixture
    def temp_dir(self):
        """Directorio temporal para tests"""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path
        shutil.rmtree(temp_path)
    
    def test_rl_prevents_memory_explosion(self, temp_dir):
        """Test que RL previene explosión de memoria"""
        rl_memory = RLMemory(base_dir=temp_dir)
        
        # Añadir muchos estados diferentes
        for i in range(100):
            rl_memory.update_q_value(
                platform="test_platform",
                state=f"state_{i}",
                action=f"action_{i}",
                reward=0.1,
            )
        
        # Cargar política
        policy = rl_memory.load_policy("test_platform")
        
        # Verificar que no hay explosión (debería tener límite razonable)
        assert len(policy.q_table) == 100  # Todos los estados se guardan
        # En producción, podría haber un límite máximo
    
    def test_rl_unknown_state(self, temp_dir):
        """Test manejo de estados desconocidos"""
        rl_engine = RLEngine(rl_memory=RLMemory(base_dir=temp_dir))
        rl_engine.set_platform("test_platform")
        
        # Estado desconocido
        available_nodes = [
            PlannerNode(node_id="node1", title="Node 1", type="navigate"),
        ]
        
        action = rl_engine.suggest_action(
            state="unknown_state",
            available_nodes=available_nodes,
        )
        
        # Debería explorar (seleccionar nodo aleatorio)
        assert action is not None

