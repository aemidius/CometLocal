"""
Tests para batch_runner v3.0.0
"""

import pytest
pytestmark = pytest.mark.asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from backend.agents.batch_runner import run_batch_agent
from backend.shared.models import (
    BatchAgentRequest,
    BatchAgentGoal,
    BatchAgentGoalResult,
)
from backend.browser.browser import BrowserController
from backend.shared.models import StepResult, BrowserObservation


class TestBatchRunner:
    """Tests para run_batch_agent"""
    
    async def test_batch_single_goal_success(self):
        """Batch con 1 objetivo sencillo debe completarse exitosamente"""
        # Mock browser
        browser = MagicMock(spec=BrowserController)
        
        # Mock run_llm_task_with_answer para éxito
        mock_steps = [
            StepResult(
                observation=BrowserObservation(
                    url="https://example.com",
                    title="Example",
                    visible_text_excerpt="Test",
                    clickable_texts=[],
                    input_hints=[],
                ),
                last_action=None,
                error=None,
                info={
                    "metrics": {
                        "summary": {
                            "total_sub_goals": 1,
                            "mode": "batch",
                        }
                    },
                    "structured_answer": {
                        "sections": [],
                        "sources": [],
                    }
                },
            )
        ]
        
        with patch(
            "backend.agents.batch_runner.run_llm_task_with_answer",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (
                mock_steps,
                "Respuesta de prueba",
                "https://example.com",
                "Example",
                [],
            )
            
            batch_request = BatchAgentRequest(
                goals=[
                    BatchAgentGoal(
                        id="goal_1",
                        goal="Buscar información sobre Ada Lovelace",
                    )
                ],
            )
            
            response = await run_batch_agent(
                batch_request=batch_request,
                browser=browser,
            )
            
            # Verificaciones
            assert response.summary["total_goals"] == 1
            assert response.summary["success_count"] == 1
            assert response.summary["failure_count"] == 0
            assert response.summary["failure_ratio"] == 0.0
            assert response.summary["aborted_due_to_failures"] is False
            assert len(response.goals) == 1
            
            goal_result = response.goals[0]
            assert goal_result.id == "goal_1"
            assert goal_result.success is True
            assert goal_result.error_message is None
            assert goal_result.final_answer == "Respuesta de prueba"
    
    async def test_batch_multiple_goals_mixed_results(self):
        """Batch con múltiples objetivos, algunos exitosos y otros fallidos"""
        browser = MagicMock(spec=BrowserController)
        
        call_count = 0
        
        async def mock_run_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                # Primer objetivo: éxito
                return (
                    [
                        StepResult(
                            observation=BrowserObservation(
                                url="https://example.com",
                                title="Example",
                                visible_text_excerpt="Test",
                                clickable_texts=[],
                                input_hints=[],
                            ),
                            last_action=None,
                            error=None,
                            info={},
                        )
                    ],
                    "Respuesta exitosa",
                    "https://example.com",
                    "Example",
                    [],
                )
            else:
                # Segundo objetivo: fallo
                raise Exception("Error simulado en segundo objetivo")
        
        with patch(
            "backend.agents.batch_runner.run_llm_task_with_answer",
            side_effect=mock_run_side_effect,
        ):
            batch_request = BatchAgentRequest(
                goals=[
                    BatchAgentGoal(
                        id="goal_1",
                        goal="Objetivo exitoso",
                    ),
                    BatchAgentGoal(
                        id="goal_2",
                        goal="Objetivo que falla",
                    ),
                ],
            )
            
            response = await run_batch_agent(
                batch_request=batch_request,
                browser=browser,
            )
            
            # Verificaciones
            assert response.summary["total_goals"] == 2
            assert response.summary["success_count"] == 1
            assert response.summary["failure_count"] == 1
            assert response.summary["failure_ratio"] == 0.5
            assert len(response.goals) == 2
            
            # Primer objetivo exitoso
            assert response.goals[0].success is True
            assert response.goals[0].error_message is None
            
            # Segundo objetivo fallido
            assert response.goals[1].success is False
            assert response.goals[1].error_message == "Error simulado en segundo objetivo"
    
    async def test_batch_aborts_on_max_consecutive_failures(self):
        """Batch debe abortar cuando se alcanza max_consecutive_failures"""
        browser = MagicMock(spec=BrowserController)
        
        with patch(
            "backend.agents.batch_runner.run_llm_task_with_answer",
            new_callable=AsyncMock,
        ) as mock_run:
            # Todos los objetivos fallan
            mock_run.side_effect = Exception("Error simulado")
            
            batch_request = BatchAgentRequest(
                goals=[
                    BatchAgentGoal(
                        id="goal_1",
                        goal="Primer objetivo que falla",
                    ),
                    BatchAgentGoal(
                        id="goal_2",
                        goal="Segundo objetivo (no debería ejecutarse)",
                    ),
                ],
                max_consecutive_failures=1,
            )
            
            response = await run_batch_agent(
                batch_request=batch_request,
                browser=browser,
            )
            
            # Verificaciones
            assert response.summary["aborted_due_to_failures"] is True
            assert response.summary["failure_count"] == 2  # Ambos marcados como fallidos
            assert len(response.goals) == 2
            
            # Primer objetivo falló
            assert response.goals[0].success is False
            
            # Segundo objetivo no se ejecutó (marcado como fallido por aborto)
            assert response.goals[1].success is False
            assert "aborted" in response.goals[1].error_message.lower()
            
            # Verificar que solo se llamó una vez (el segundo no se ejecutó)
            assert mock_run.call_count == 1
    
    async def test_batch_uses_default_configuration(self):
        """Batch debe usar configuración por defecto cuando no se especifica por objetivo"""
        browser = MagicMock(spec=BrowserController)
        
        mock_steps = [
            StepResult(
                observation=BrowserObservation(
                    url="https://example.com",
                    title="Example",
                    visible_text_excerpt="Test",
                    clickable_texts=[],
                    input_hints=[],
                ),
                last_action=None,
                error=None,
                info={},
            )
        ]
        
        with patch(
            "backend.agents.batch_runner.run_llm_task_with_answer",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (
                mock_steps,
                "Respuesta",
                "https://example.com",
                "Example",
                [],
            )
            
            batch_request = BatchAgentRequest(
                goals=[
                    BatchAgentGoal(
                        id="goal_1",
                        goal="Objetivo sin configuración específica",
                    )
                ],
                default_execution_profile_name="fast",
                default_context_strategies=["wikipedia"],
            )
            
            await run_batch_agent(
                batch_request=batch_request,
                browser=browser,
            )
            
            # Verificar que se llamó con la configuración por defecto
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["execution_profile_name"] == "fast"
            assert call_kwargs["context_strategies"] == ["wikipedia"]
    
    async def test_batch_goal_specific_config_overrides_default(self):
        """La configuración específica de un objetivo debe sobrescribir los defaults"""
        browser = MagicMock(spec=BrowserController)
        
        mock_steps = [
            StepResult(
                observation=BrowserObservation(
                    url="https://example.com",
                    title="Example",
                    visible_text_excerpt="Test",
                    clickable_texts=[],
                    input_hints=[],
                ),
                last_action=None,
                error=None,
                info={},
            )
        ]
        
        with patch(
            "backend.agents.batch_runner.run_llm_task_with_answer",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = (
                mock_steps,
                "Respuesta",
                "https://example.com",
                "Example",
                [],
            )
            
            batch_request = BatchAgentRequest(
                goals=[
                    BatchAgentGoal(
                        id="goal_1",
                        goal="Objetivo con configuración específica",
                        execution_profile_name="thorough",
                        context_strategies=["images"],
                    )
                ],
                default_execution_profile_name="fast",
                default_context_strategies=["wikipedia"],
            )
            
            await run_batch_agent(
                batch_request=batch_request,
                browser=browser,
            )
            
            # Verificar que se usó la configuración específica del objetivo
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["execution_profile_name"] == "thorough"
            assert call_kwargs["context_strategies"] == ["images"]

