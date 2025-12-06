"""
Tests para execution_profile_name y context_strategies desde la UI (v2.7.0)
"""

import pytest
from backend.shared.models import AgentAnswerRequest
from backend.agents.execution_profile import ExecutionProfile


class TestExecutionProfileFromRequest:
    """Tests para execution_profile_name en AgentAnswerRequest"""
    
    def test_execution_profile_name_fast(self):
        """execution_profile_name="fast" se acepta correctamente"""
        request = AgentAnswerRequest(
            goal="test goal",
            execution_profile_name="fast"
        )
        assert request.execution_profile_name == "fast"
    
    def test_execution_profile_name_balanced(self):
        """execution_profile_name="balanced" se acepta correctamente"""
        request = AgentAnswerRequest(
            goal="test goal",
            execution_profile_name="balanced"
        )
        assert request.execution_profile_name == "balanced"
    
    def test_execution_profile_name_thorough(self):
        """execution_profile_name="thorough" se acepta correctamente"""
        request = AgentAnswerRequest(
            goal="test goal",
            execution_profile_name="thorough"
        )
        assert request.execution_profile_name == "thorough"
    
    def test_execution_profile_name_none(self):
        """execution_profile_name=None es válido (comportamiento por defecto)"""
        request = AgentAnswerRequest(
            goal="test goal",
            execution_profile_name=None
        )
        assert request.execution_profile_name is None
    
    def test_execution_profile_name_invalid_ignored(self):
        """execution_profile_name inválido se acepta pero se ignorará en el backend"""
        # Pydantic acepta cualquier string, pero el backend lo validará
        request = AgentAnswerRequest(
            goal="test goal",
            execution_profile_name="superfast"
        )
        assert request.execution_profile_name == "superfast"
    
    def test_context_strategies_list(self):
        """context_strategies como lista se acepta correctamente"""
        request = AgentAnswerRequest(
            goal="test goal",
            context_strategies=["wikipedia", "images"]
        )
        assert request.context_strategies == ["wikipedia", "images"]
    
    def test_context_strategies_none(self):
        """context_strategies=None es válido"""
        request = AgentAnswerRequest(
            goal="test goal",
            context_strategies=None
        )
        assert request.context_strategies is None
    
    def test_both_fields_together(self):
        """execution_profile_name y context_strategies pueden usarse juntos"""
        request = AgentAnswerRequest(
            goal="test goal",
            execution_profile_name="fast",
            context_strategies=["wikipedia", "cae"]
        )
        assert request.execution_profile_name == "fast"
        assert request.context_strategies == ["wikipedia", "cae"]





