"""
Tests para outcome_judge v4.1.0
"""

import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from backend.agents.outcome_judge import build_outcome_judge_report
from backend.shared.models import (
    OutcomeJudgeReport,
    OutcomeSubGoalReview,
    OutcomeGlobalReview,
)
from backend.agents.execution_plan import ExecutionPlan, PlannedSubGoal
from backend.shared.models import StepResult, BrowserObservation, BrowserAction


class TestOutcomeJudge:
    """Tests para build_outcome_judge_report"""
    
    def test_outcome_judge_basic_structure(self):
        """Test que build_outcome_judge_report parsea JSON simple correctamente"""
        async def run_test():
            # Mock LLM client
            llm_client = MagicMock()
            # Crear un OutcomeJudgeReport real para el mock
            mock_report = OutcomeJudgeReport(
                goal="Test goal",
                execution_profile_name="balanced",
                context_strategies=["wikipedia"],
                global_review=OutcomeGlobalReview(
                    overall_success=True,
                    global_score=0.85,
                    main_issues=["Issue 1"],
                    main_strengths=["Strength 1"],
                    recommendations=["Recommendation 1"]
                ),
                sub_goals=[
                    OutcomeSubGoalReview(
                        sub_goal_index=1,
                        sub_goal_text="Test sub-goal",
                        success=True,
                        score=0.9,
                        issues=[],
                        warnings=[],
                        strengths=["Good execution"]
                    )
                ],
                next_run_profile_suggestion=None,
                next_run_notes=None,
                llm_raw_notes="Test notes"
            )
            
            llm_client.chat.completions.create = AsyncMock(return_value=mock_report)
            
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
                        may_retry=False
                    )
                ]
            )
            
            # Crear steps
            steps = [
                StepResult(
                    observation=BrowserObservation(
                        url="https://example.com",
                        title="Example",
                        visible_text_excerpt="Test",
                        clickable_texts=[],
                        input_hints=[]
                    ),
                    last_action=BrowserAction(type="open_url", args={"url": "https://example.com"}),
                    error=None,
                    info={}
                )
            ]
            
            # Llamar a build_outcome_judge_report
            result = await build_outcome_judge_report(
                llm_client=llm_client,
                goal="Test goal",
                execution_plan=execution_plan,
                steps=steps,
                final_answer="Test answer",
                metrics_summary={"summary": {}},
                planner_hints=None,
                spotlight=None,
                memory_store=None,
            )
            
            # Verificar estructura básica
            assert isinstance(result, OutcomeJudgeReport)
            assert result.goal == "Test goal"
            assert result.global_review is not None
            assert result.global_review.global_score == 0.85
            assert len(result.sub_goals) == 1
            assert result.sub_goals[0].sub_goal_index == 1
        
        asyncio.run(run_test())
    
    def test_outcome_judge_handles_invalid_json(self):
        """Test que build_outcome_judge_report maneja JSON inválido correctamente"""
        async def run_test():
            # Mock LLM client que lanza ValidationError
            llm_client = MagicMock()
            from pydantic import ValidationError
            
            # Simular ValidationError
            llm_client.chat.completions.create = AsyncMock(side_effect=ValidationError.from_exception_data(
                "OutcomeJudgeReport",
                [{"type": "missing", "loc": ("global_review",), "msg": "Field required"}]
            ))
            
            execution_plan = ExecutionPlan(
                goal="Test goal",
                execution_profile={"name": "balanced"},
                context_strategies=[],
                sub_goals=[]
            )
            
            result = await build_outcome_judge_report(
                llm_client=llm_client,
                goal="Test goal",
                execution_plan=execution_plan,
                steps=[],
                final_answer="Test answer",
                metrics_summary=None,
                planner_hints=None,
                spotlight=None,
                memory_store=None,
            )
            
            # Debe devolver un OutcomeJudgeReport mínimo con llm_raw_notes
            assert isinstance(result, OutcomeJudgeReport)
            assert result.goal == "Test goal"
            assert result.llm_raw_notes is not None
        
        asyncio.run(run_test())
    
    def test_outcome_judge_ignores_out_of_range_subgoals(self):
        """Test que build_outcome_judge_report ignora sub-goals con índices fuera de rango"""
        async def run_test():
            # Mock LLM client
            llm_client = MagicMock()
            mock_response = MagicMock()
            mock_response.goal = "Test goal"
            mock_response.execution_profile_name = "balanced"
            mock_response.context_strategies = []
            mock_response.global_review = None
            # Sub-goal con índice 99 que no existe en el plan
            mock_response.sub_goals = [
                OutcomeSubGoalReview(
                    sub_goal_index=99,
                    sub_goal_text="Invalid sub-goal",
                    success=None,
                    score=None,
                    issues=[],
                    warnings=[],
                    strengths=[]
                )
            ]
            mock_response.next_run_profile_suggestion = None
            mock_response.next_run_notes = None
            mock_response.llm_raw_notes = None
            
            llm_client.chat.completions.create = AsyncMock(return_value=mock_response)
            
            # Crear execution plan con solo índice 1
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
                        may_retry=False
                    )
                ]
            )
            
            result = await build_outcome_judge_report(
                llm_client=llm_client,
                goal="Test goal",
                execution_plan=execution_plan,
                steps=[],
                final_answer="Test answer",
                metrics_summary=None,
                planner_hints=None,
                spotlight=None,
                memory_store=None,
            )
            
            # El sub-goal con índice 99 debe ser filtrado
            assert len(result.sub_goals) == 0
        
        asyncio.run(run_test())
    
    def test_outcome_judge_handles_llm_error(self):
        """Test que build_outcome_judge_report maneja errores del LLM correctamente"""
        async def run_test():
            # Mock LLM client que lanza excepción
            llm_client = MagicMock()
            llm_client.chat.completions.create = AsyncMock(side_effect=Exception("LLM API error"))
            
            execution_plan = ExecutionPlan(
                goal="Test goal",
                execution_profile={"name": "balanced"},
                context_strategies=[],
                sub_goals=[]
            )
            
            result = await build_outcome_judge_report(
                llm_client=llm_client,
                goal="Test goal",
                execution_plan=execution_plan,
                steps=[],
                final_answer="Test answer",
                metrics_summary=None,
                planner_hints=None,
                spotlight=None,
                memory_store=None,
            )
            
            # Debe devolver un OutcomeJudgeReport mínimo con llm_raw_notes
            assert isinstance(result, OutcomeJudgeReport)
            assert result.goal == "Test goal"
            assert result.llm_raw_notes is not None
            assert "Fallo" in result.llm_raw_notes or "error" in result.llm_raw_notes.lower()
        
        asyncio.run(run_test())
    
    def test_outcome_judge_register_metrics(self):
        """Test que register_outcome_judge actualiza las métricas correctamente"""
        from backend.agents.agent_runner import AgentMetrics
        
        metrics = AgentMetrics()
        metrics.start()
        
        # Crear un OutcomeJudgeReport de prueba
        report = OutcomeJudgeReport(
            goal="Test goal",
            execution_profile_name="balanced",
            context_strategies=[],
            global_review=OutcomeGlobalReview(
                overall_success=True,
                global_score=0.75,
                main_issues=["Issue 1", "Issue 2"],
                main_strengths=["Strength 1"],
                recommendations=[]
            ),
            sub_goals=[
                OutcomeSubGoalReview(
                    sub_goal_index=1,
                    sub_goal_text="Test sub-goal",
                    success=True,
                    score=0.8,
                    issues=["Issue 1"],
                    warnings=["Warning 1"],
                    strengths=[]
                )
            ],
            next_run_profile_suggestion=None,
            next_run_notes=None,
            llm_raw_notes=None
        )
        
        # Registrar outcome judge
        metrics.register_outcome_judge(report)
        metrics.finish()
        
        # Verificar métricas
        summary = metrics.to_summary_dict()
        assert summary["summary"]["outcome_judge_info"]["outcome_judge_generated"] is True
        assert summary["summary"]["outcome_judge_info"]["outcome_global_score"] == 0.75
        assert summary["summary"]["outcome_judge_info"]["outcome_subgoals_reviewed"] == 1
        # Issues total: solo cuenta issues y warnings de sub_goals (no main_issues)
        # 1 (sub-goal issue) + 1 (sub-goal warning) = 2
        assert summary["summary"]["outcome_judge_info"]["outcome_issues_total"] == 2

