"""
Tests unitarios para SessionContext v1.7.0
"""
import pytest
from backend.agents.session_context import SessionContext


class TestSessionContext:
    """Tests para SessionContext"""
    
    def test_create_empty_context(self):
        """Crear instancia vacía de SessionContext"""
        context = SessionContext()
        assert context.current_focus_entity is None
        assert context.last_valid_entity is None
        assert len(context.entity_history) == 0
        assert context.last_goal is None
        assert context.last_sub_goal is None
    
    def test_update_entity(self):
        """Actualizar entidad en el contexto"""
        context = SessionContext()
        
        context.update_entity("Ada Lovelace")
        
        assert context.current_focus_entity == "Ada Lovelace"
        assert context.last_valid_entity == "Ada Lovelace"
        assert len(context.entity_history) == 1
        assert "Ada Lovelace" in context.entity_history
    
    def test_update_entity_no_duplicates_consecutive(self):
        """No añadir duplicados consecutivos al historial"""
        context = SessionContext()
        
        context.update_entity("Ada Lovelace")
        context.update_entity("Ada Lovelace")
        context.update_entity("Charles Babbage")
        context.update_entity("Charles Babbage")
        
        assert len(context.entity_history) == 2
        assert context.entity_history == ["Ada Lovelace", "Charles Babbage"]
    
    def test_update_entity_history_limit(self):
        """Limitar historial a 10 entidades"""
        context = SessionContext()
        
        for i in range(15):
            context.update_entity(f"Entity{i}")
        
        assert len(context.entity_history) == 10
        assert context.entity_history[0] == "Entity5"  # Las primeras 5 se eliminaron
        assert context.entity_history[-1] == "Entity14"
    
    def test_update_entity_ignores_empty(self):
        """Ignorar entidades vacías o None"""
        context = SessionContext()
        
        context.update_entity("Ada Lovelace")
        context.update_entity("")
        context.update_entity(None)
        context.update_entity("   ")
        
        assert context.current_focus_entity == "Ada Lovelace"
        assert len(context.entity_history) == 1
    
    def test_resolve_entity_reference_with_current(self):
        """Resolver referencia usando current_focus_entity"""
        context = SessionContext()
        context.update_entity("Ada Lovelace")
        
        result = context.resolve_entity_reference("muéstrame imágenes suyas")
        
        assert result == "Ada Lovelace"
    
    def test_resolve_entity_reference_with_last_valid(self):
        """Resolver referencia usando last_valid_entity como fallback"""
        context = SessionContext()
        context.update_entity("Ada Lovelace")
        context.current_focus_entity = None  # Simular que se perdió
        
        result = context.resolve_entity_reference("muéstrame imágenes suyas")
        
        assert result == "Ada Lovelace"  # Usa last_valid_entity
    
    def test_resolve_entity_reference_no_context(self):
        """Devolver None si no hay contexto disponible"""
        context = SessionContext()
        
        result = context.resolve_entity_reference("muéstrame imágenes suyas")
        
        assert result is None
    
    def test_update_goal(self):
        """Actualizar goal y sub-goal en el contexto"""
        context = SessionContext()
        
        context.update_goal("goal completo", "sub-goal 1")
        
        assert context.last_goal == "goal completo"
        assert context.last_sub_goal == "sub-goal 1"
    
    def test_to_debug_dict(self):
        """Generar dict de debug con el estado del contexto"""
        context = SessionContext()
        context.update_entity("Ada Lovelace")
        context.update_goal("test goal", "test sub-goal")
        
        debug_dict = context.to_debug_dict()
        
        assert "current_focus_entity" in debug_dict
        assert "last_valid_entity" in debug_dict
        assert "entity_history" in debug_dict
        assert "last_goal" in debug_dict
        assert "last_sub_goal" in debug_dict
        assert debug_dict["current_focus_entity"] == "Ada Lovelace"
        assert isinstance(debug_dict["entity_history"], list)


class TestSessionContextIntegration:
    """Tests de integración de SessionContext con el flujo de sub-goals"""
    
    def test_resolve_pronouns_sequence(self):
        """Simular secuencia de sub-goals con pronombres"""
        context = SessionContext()
        
        # Sub-goal 1: entidad explícita
        entity1 = "Ada Lovelace"
        context.update_entity(entity1)
        context.update_goal("goal completo", "investiga quién fue Ada Lovelace")
        
        # Sub-goal 2: pronombres
        resolved = context.resolve_entity_reference("muéstrame imágenes suyas")
        assert resolved == "Ada Lovelace"
        
        # Actualizar después del sub-goal 2
        context.update_entity(resolved)
        context.update_goal("goal completo", "muéstrame imágenes suyas")
        
        # Verificar que el contexto se mantiene
        assert context.current_focus_entity == "Ada Lovelace"
        assert len(context.entity_history) == 1
    
    def test_multiple_entities_sequence(self):
        """Secuencia con múltiples entidades diferentes"""
        context = SessionContext()
        
        # Primera entidad
        context.update_entity("Ada Lovelace")
        context.update_goal("goal", "sub-goal 1")
        
        # Segunda entidad (reemplaza la primera)
        context.update_entity("Charles Babbage")
        context.update_goal("goal", "sub-goal 2")
        
        # Verificar que la segunda entidad es la actual
        assert context.current_focus_entity == "Charles Babbage"
        assert context.last_valid_entity == "Charles Babbage"
        assert len(context.entity_history) == 2
        assert "Ada Lovelace" in context.entity_history
        assert "Charles Babbage" in context.entity_history








