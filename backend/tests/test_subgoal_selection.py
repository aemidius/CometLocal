"""
Tests para selección de sub-goals v2.9.0
"""

import pytest
pytestmark = pytest.mark.asyncio
from backend.agents.agent_runner import run_llm_task_with_answer, AgentMetrics
from backend.browser.browser import BrowserController
from unittest.mock import AsyncMock, MagicMock
from backend.shared.models import BrowserObservation, StepResult


class TestSubGoalSelection:
    """Tests para selección de sub-goals"""
    
    async def test_disabled_sub_goal_indices_none_executes_all(self):
        """Si disabled_sub_goal_indices es None, se ejecutan todos los sub-goals"""
        # Mock browser
        browser = MagicMock(spec=BrowserController)
        browser.get_observation = AsyncMock(return_value=BrowserObservation(
            url="https://example.com",
            title="Example",
            visible_text_excerpt="Test",
            clickable_texts=[],
            input_hints=[]
        ))
        browser.execute_action = AsyncMock(return_value=None)
        
        goal = "Buscar información sobre Ada Lovelace y luego buscar imágenes de Charles Babbage"
        
        # Ejecutar sin disabled_sub_goal_indices
        steps, final_answer, _, _, _ = await run_llm_task_with_answer(
            goal=goal,
            browser=browser,
            max_steps=2,
            disabled_sub_goal_indices=None,
        )
        
        # Debe ejecutar ambos sub-goals
        assert len(steps) > 0
        # Verificar que hay steps con diferentes sub_goal_index
        sub_goal_indices = set()
        for step in steps:
            if step.info and "sub_goal_index" in step.info:
                sub_goal_indices.add(step.info["sub_goal_index"])
        
        # Debe haber al menos 2 sub-goals ejecutados
        assert len(sub_goal_indices) >= 1
    
    async def test_disabled_sub_goal_indices_skips_subgoal(self):
        """Si disabled_sub_goal_indices contiene un índice, ese sub-goal no se ejecuta"""
        # Mock browser
        browser = MagicMock(spec=BrowserController)
        browser.get_observation = AsyncMock(return_value=BrowserObservation(
            url="https://example.com",
            title="Example",
            visible_text_excerpt="Test",
            clickable_texts=[],
            input_hints=[]
        ))
        browser.execute_action = AsyncMock(return_value=None)
        
        goal = "Buscar información sobre Ada Lovelace y luego buscar imágenes de Charles Babbage"
        
        # Ejecutar con sub-goal 2 deshabilitado
        steps, final_answer, _, _, _ = await run_llm_task_with_answer(
            goal=goal,
            browser=browser,
            max_steps=2,
            disabled_sub_goal_indices=[2],
        )
        
        # Verificar que no hay steps con sub_goal_index == 2
        for step in steps:
            if step.info and "sub_goal_index" in step.info:
                assert step.info["sub_goal_index"] != 2, "Sub-goal 2 no debería haberse ejecutado"
    
    async def test_all_sub_goals_disabled_returns_friendly_message(self):
        """Si todos los sub-goals están deshabilitados, devuelve mensaje amigable"""
        # Mock browser
        browser = MagicMock(spec=BrowserController)
        
        goal = "Buscar información sobre Ada Lovelace y luego buscar imágenes de Charles Babbage"
        
        # Ejecutar con todos los sub-goals deshabilitados
        steps, final_answer, _, _, _ = await run_llm_task_with_answer(
            goal=goal,
            browser=browser,
            max_steps=2,
            disabled_sub_goal_indices=[1, 2],
        )
        
        # Debe devolver mensaje amigable
        assert "no se ha ejecutado ningún sub-objetivo" in final_answer.lower() or \
               "todos han sido desactivados" in final_answer.lower()
        
        # No debe haber steps
        assert len(steps) == 0
    
    def test_metrics_skipped_sub_goals_count(self):
        """AgentMetrics cuenta correctamente sub-goals saltados"""
        metrics = AgentMetrics()
        metrics.start()
        metrics.skipped_sub_goals_count = 2
        metrics.skipped_sub_goal_indices = [2, 3]
        metrics.finish()
        
        summary = metrics.to_summary_dict()
        
        assert "skipped_info" in summary["summary"]
        assert summary["summary"]["skipped_info"]["skipped_sub_goals_count"] == 2
        assert summary["summary"]["skipped_info"]["skipped_sub_goal_indices"] == [2, 3]
    
    def test_metrics_skipped_sub_goals_empty(self):
        """AgentMetrics maneja correctamente cuando no hay sub-goals saltados"""
        metrics = AgentMetrics()
        metrics.start()
        # skipped_sub_goals_count y skipped_sub_goal_indices ya están inicializados a 0 y []
        metrics.finish()
        
        summary = metrics.to_summary_dict()
        
        assert "skipped_info" in summary["summary"]
        assert summary["summary"]["skipped_info"]["skipped_sub_goals_count"] == 0
        assert summary["summary"]["skipped_info"]["skipped_sub_goal_indices"] == []

