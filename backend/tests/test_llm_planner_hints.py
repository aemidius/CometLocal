"""
Tests para llm_planner_hints v4.0.0
"""

import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from backend.agents.llm_planner_hints import build_planner_hints
from backend.shared.models import PlannerHints, PlannerHintSubGoal, PlannerHintProfileSuggestion, PlannerHintGlobal
from backend.agents.execution_plan import ExecutionPlan, PlannedSubGoal
from backend.shared.models import ReasoningSpotlight, ReasoningInterpretation, ReasoningAmbiguity


class TestLLMPlannerHints:
    """Tests para build_planner_hints"""
    
    def test_planner_hints_basic_structure(self):
        """Test que build_planner_hints parsea JSON simple correctamente"""
        async def run_test():
            # Mock LLM client
            llm_client = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps({
                "sub_goals": [
                    {
                        "sub_goal_index": 1,
                        "sub_goal_text": "Test sub-goal",
                        "suggested_enabled": True,
                        "priority": "high",
                        "risk_level": "low",
                        "rationale": "This is critical"
                    }
                ],
                "profile_suggestion": {
                    "suggested_profile": "fast",
                    "rationale": "Simple task"
                },
                "global_insights": {
                    "summary": "Test summary",
                    "risks": ["Risk 1"],
                    "opportunities": ["Opportunity 1"]
                },
                "llm_raw_notes": "Test notes"
            })
            llm_client.chat.completions.create = AsyncMock(return_value=mock_response)
            
            # Crear execution plan
            execution_plan = ExecutionPlan(
                goal="Test goal",
                execution_profile={"name": "balanced"},
                context_strategies=["wikipedia"],
                sub_goals=[
                    PlannedSubGoal(
                        index=1,
                        sub_goal="Test sub-goal",
                        strategy="wikipedia",
                        expected_actions=["navigate"],
                        documents_needed=[],
                        may_retry=False,
                    )
                ],
            )
            
            # Llamar a build_planner_hints
            hints = await build_planner_hints(
                llm_client=llm_client,
                goal="Test goal",
                execution_plan=execution_plan,
                spotlight=None,
                memory_store=None,
            )
            
            # Verificar estructura
            assert isinstance(hints, PlannerHints)
            assert hints.goal == "Test goal"
            assert len(hints.sub_goals) == 1
            assert hints.sub_goals[0].sub_goal_index == 1
            assert hints.sub_goals[0].priority == "high"
            assert hints.profile_suggestion is not None
            assert hints.profile_suggestion.suggested_profile == "fast"
            assert hints.global_insights is not None
            assert hints.global_insights.summary == "Test summary"
        
        asyncio.run(run_test())
    
    def test_planner_hints_handles_invalid_json(self):
        """Test que build_planner_hints maneja JSON inválido correctamente"""
        async def run_test():
            # Mock LLM client con respuesta no JSON
            llm_client = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "This is not JSON"
            llm_client.chat.completions.create = AsyncMock(return_value=mock_response)
            
            execution_plan = ExecutionPlan(
                goal="Test goal",
                execution_profile={"name": "balanced"},
                context_strategies=[],
                sub_goals=[],
            )
            
            # Llamar a build_planner_hints
            hints = await build_planner_hints(
                llm_client=llm_client,
                goal="Test goal",
                execution_plan=execution_plan,
                spotlight=None,
                memory_store=None,
            )
            
            # Debe devolver PlannerHints vacío pero válido con llm_raw_notes
            assert isinstance(hints, PlannerHints)
            assert hints.goal == "Test goal"
            assert len(hints.sub_goals) == 0
            assert hints.llm_raw_notes is not None
            assert "This is not JSON" in hints.llm_raw_notes or "Error parsing JSON" in hints.llm_raw_notes
        
        asyncio.run(run_test())
    
    def test_planner_hints_ignores_out_of_range_subgoals(self):
        """Test que build_planner_hints ignora sub-goals con índices fuera de rango"""
        async def run_test():
            # Mock LLM client
            llm_client = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = json.dumps({
                "sub_goals": [
                    {
                        "sub_goal_index": 1,
                        "sub_goal_text": "Valid sub-goal",
                        "priority": "high"
                    },
                    {
                        "sub_goal_index": 999,  # Fuera de rango
                        "sub_goal_text": "Invalid sub-goal",
                        "priority": "low"
                    }
                ]
            })
            llm_client.chat.completions.create = AsyncMock(return_value=mock_response)
            
            execution_plan = ExecutionPlan(
                goal="Test goal",
                execution_profile={"name": "balanced"},
                context_strategies=[],
                sub_goals=[
                    PlannedSubGoal(
                        index=1,
                        sub_goal="Valid sub-goal",
                        strategy="wikipedia",
                        expected_actions=[],
                        documents_needed=[],
                        may_retry=False,
                    )
                ],
            )
            
            hints = await build_planner_hints(
                llm_client=llm_client,
                goal="Test goal",
                execution_plan=execution_plan,
                spotlight=None,
                memory_store=None,
            )
            
            # Solo debe incluir el sub-goal válido
            assert len(hints.sub_goals) == 1
            assert hints.sub_goals[0].sub_goal_index == 1
            assert hints.sub_goals[0].sub_goal_text == "Valid sub-goal"
        
        asyncio.run(run_test())
    
    def test_planner_hints_handles_llm_error(self):
        """Test que build_planner_hints maneja errores del LLM correctamente"""
        async def run_test():
            # Mock LLM client que lanza excepción
            llm_client = MagicMock()
            llm_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM error"))
            
            execution_plan = ExecutionPlan(
                goal="Test goal",
                execution_profile={"name": "balanced"},
                context_strategies=[],
                sub_goals=[],
            )
            
            hints = await build_planner_hints(
                llm_client=llm_client,
                goal="Test goal",
                execution_plan=execution_plan,
                spotlight=None,
                memory_store=None,
            )
            
            # Debe devolver PlannerHints vacío pero válido
            assert isinstance(hints, PlannerHints)
            assert hints.goal == "Test goal"
            assert len(hints.sub_goals) == 0
            assert hints.llm_raw_notes is not None
            assert "Error generating hints" in hints.llm_raw_notes or "LLM error" in hints.llm_raw_notes
        
        asyncio.run(run_test())
    
    def test_planner_hints_register_metrics(self):
        """Test que register_planner_hints actualiza las métricas correctamente"""
        from backend.agents.agent_runner import AgentMetrics
        
        metrics = AgentMetrics()
        hints = PlannerHints(
            goal="Test goal",
            sub_goals=[
                PlannerHintSubGoal(
                    sub_goal_index=1,
                    sub_goal_text="Test",
                    suggested_enabled=True,
                    priority="high",
                    risk_level="low",
                ),
                PlannerHintSubGoal(
                    sub_goal_index=2,
                    sub_goal_text="Test 2",
                    suggested_enabled=None,
                    priority=None,
                    risk_level=None,
                ),
            ],
            profile_suggestion=PlannerHintProfileSuggestion(
                suggested_profile="fast",
                rationale="Simple",
            ),
        )
        
        metrics.register_planner_hints(hints)
        
        assert metrics.planner_hints_generated is True
        assert metrics.planner_hints_subgoals_with_suggestions == 1  # Solo el primero tiene sugerencias
        assert metrics.planner_hints_profile_changed_recommendation is True
        
        # Verificar en summary
        summary = metrics.to_summary_dict()
        assert "planner_hints_info" in summary["summary"]
        assert summary["summary"]["planner_hints_info"]["planner_hints_generated"] is True
        assert summary["summary"]["planner_hints_info"]["planner_hints_subgoals_with_suggestions"] == 1
        assert summary["summary"]["planner_hints_info"]["planner_hints_profile_changed_recommendation"] is True

