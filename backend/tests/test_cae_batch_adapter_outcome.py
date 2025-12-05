"""
Tests para integración de OutcomeJudge y memoria en cae_batch_adapter v4.2.0
"""

import pytest
import tempfile
import shutil
from datetime import datetime
from unittest.mock import patch, MagicMock

from backend.agents.cae_batch_adapter import build_cae_response_from_batch
from backend.shared.models import (
    CAEBatchRequest,
    CAEWorker,
    BatchAgentResponse,
    BatchAgentGoalResult,
    OutcomeJudgeReport,
    OutcomeGlobalReview,
    OutcomeSubGoalReview,
)
from backend.memory.memory_store import MemoryStore
from backend.config import MEMORY_BASE_DIR


class TestCAEBatchAdapterOutcome:
    """Tests para integración de OutcomeJudge y memoria en CAE batch"""
    
    @pytest.fixture
    def temp_dir(self):
        """Crea un directorio temporal para tests"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    def test_cae_batch_adapter_updates_memory_with_outcome(self, temp_dir):
        """build_cae_response_from_batch debe actualizar memoria con OutcomeJudge"""
        # Mock MemoryStore para usar directorio temporal
        with patch('backend.agents.cae_batch_adapter.MEMORY_BASE_DIR', temp_dir):
            cae_request = CAEBatchRequest(
                platform="test_platform",
                company_name="EmpresaTest",
                workers=[
                    CAEWorker(
                        id="worker_1",
                        full_name="Juan Pérez",
                    ),
                ],
            )
            
            # Crear OutcomeJudgeReport de prueba
            outcome_judge = OutcomeJudgeReport(
                goal="Test goal",
                execution_profile_name="balanced",
                context_strategies=[],
                global_review=OutcomeGlobalReview(
                    overall_success=True,
                    global_score=0.85,
                    main_issues=["Issue 1", "Issue 2"],
                    main_strengths=["Strength 1"],
                    recommendations=[]
                ),
                sub_goals=[],
                next_run_profile_suggestion=None,
                next_run_notes=None,
                llm_raw_notes=None
            )
            
            batch_response = BatchAgentResponse(
                goals=[
                    BatchAgentGoalResult(
                        id="worker_1",
                        goal="Test goal",
                        success=True,
                        final_answer="Test answer",
                        metrics_summary={},
                        outcome_judge=outcome_judge,
                    )
                ],
                summary={}
            )
            
            # Construir respuesta CAE
            cae_response = build_cae_response_from_batch(cae_request, batch_response)
            
            # Verificar que se actualizó la memoria
            memory_store = MemoryStore(temp_dir)
            worker_memory = memory_store.load_worker("worker_1")
            
            assert worker_memory is not None
            assert worker_memory.last_outcome_score == 0.85
            assert worker_memory.outcome_run_count == 1
            assert worker_memory.last_outcome_issues is not None
            assert len(worker_memory.last_outcome_issues) > 0
    
    def test_cae_batch_adapter_detects_regression(self, temp_dir):
        """build_cae_response_from_batch debe detectar regresiones cuando el score baja"""
        with patch('backend.agents.cae_batch_adapter.MEMORY_BASE_DIR', temp_dir):
            # Preparar memoria previa con score alto
            memory_store = MemoryStore(temp_dir)
            memory_store.update_worker_outcome(
                worker_id="worker_1",
                new_score=0.90,
                issues=[],
                timestamp=datetime.now()
            )
            
            cae_request = CAEBatchRequest(
                platform="test_platform",
                company_name="EmpresaTest",
                workers=[
                    CAEWorker(
                        id="worker_1",
                        full_name="Juan Pérez",
                    ),
                ],
            )
            
            # Crear OutcomeJudgeReport con score bajo (regresión)
            outcome_judge = OutcomeJudgeReport(
                goal="Test goal",
                execution_profile_name="balanced",
                context_strategies=[],
                global_review=OutcomeGlobalReview(
                    overall_success=False,
                    global_score=0.60,  # Baja de 0.90 a 0.60 (delta = -30)
                    main_issues=["Issue 1"],
                    main_strengths=[],
                    recommendations=[]
                ),
                sub_goals=[],
                next_run_profile_suggestion=None,
                next_run_notes=None,
                llm_raw_notes=None
            )
            
            batch_response = BatchAgentResponse(
                goals=[
                    BatchAgentGoalResult(
                        id="worker_1",
                        goal="Test goal",
                        success=True,
                        final_answer="Test answer",
                        metrics_summary={},
                        outcome_judge=outcome_judge,
                    )
                ],
                summary={}
            )
            
            # Construir respuesta CAE
            cae_response = build_cae_response_from_batch(cae_request, batch_response)
            
            # Verificar que se detectó la regresión
            worker_status = cae_response.workers[0]
            assert worker_status.regression_flag is not None
            assert worker_status.regression_flag["type"] == "strong_regression"
            assert worker_status.regression_flag["previous_score"] == 0.90
            assert worker_status.regression_flag["current_score"] == 0.60
            assert abs(worker_status.regression_flag["delta"] - (-0.30)) < 0.01
            assert "regresión" in worker_status.notes.lower()
            
            # Verificar que summary incluye regressions_detected
            assert cae_response.summary.get("regressions_detected") == 1
    
    def test_cae_batch_adapter_enriches_memory_summary_outcome(self, temp_dir):
        """build_cae_response_from_batch debe enriquecer memory_summary_outcome"""
        with patch('backend.agents.cae_batch_adapter.MEMORY_BASE_DIR', temp_dir):
            # Preparar memoria previa
            memory_store = MemoryStore(temp_dir)
            memory_store.update_worker_outcome(
                worker_id="worker_1",
                new_score=0.80,
                issues=["Issue A"],
                timestamp=datetime.now()
            )
            memory_store.update_worker_outcome(
                worker_id="worker_1",
                new_score=0.85,
                issues=["Issue B"],
                timestamp=datetime.now()
            )
            
            cae_request = CAEBatchRequest(
                platform="test_platform",
                company_name="EmpresaTest",
                workers=[
                    CAEWorker(
                        id="worker_1",
                        full_name="Juan Pérez",
                    ),
                ],
            )
            
            outcome_judge = OutcomeJudgeReport(
                goal="Test goal",
                execution_profile_name="balanced",
                context_strategies=[],
                global_review=OutcomeGlobalReview(
                    overall_success=True,
                    global_score=0.90,
                    main_issues=[],
                    main_strengths=[],
                    recommendations=[]
                ),
                sub_goals=[],
                next_run_profile_suggestion=None,
                next_run_notes=None,
                llm_raw_notes=None
            )
            
            batch_response = BatchAgentResponse(
                goals=[
                    BatchAgentGoalResult(
                        id="worker_1",
                        goal="Test goal",
                        success=True,
                        final_answer="Test answer",
                        metrics_summary={},
                        outcome_judge=outcome_judge,
                    )
                ],
                summary={}
            )
            
            cae_response = build_cae_response_from_batch(cae_request, batch_response)
            
            # Verificar memory_summary_outcome
            worker_status = cae_response.workers[0]
            assert worker_status.memory_summary_outcome is not None
            assert worker_status.memory_summary_outcome["last_outcome_score"] == 0.90
            assert worker_status.memory_summary_outcome["best_outcome_score"] == 0.90
            assert worker_status.memory_summary_outcome["worst_outcome_score"] == 0.80
            assert worker_status.memory_summary_outcome["outcome_run_count"] == 3
            assert "Históricamente" in worker_status.notes
    
    def test_cae_batch_adapter_summary_includes_outcome_info(self, temp_dir):
        """CAEBatchResponse.summary debe incluir información de outcome"""
        with patch('backend.agents.cae_batch_adapter.MEMORY_BASE_DIR', temp_dir):
            cae_request = CAEBatchRequest(
                platform="test_platform",
                company_name="EmpresaTest",
                workers=[
                    CAEWorker(id="worker_1", full_name="Juan Pérez"),
                    CAEWorker(id="worker_2", full_name="María García"),
                ],
            )
            
            batch_response = BatchAgentResponse(
                goals=[
                    BatchAgentGoalResult(
                        id="worker_1",
                        goal="Test goal 1",
                        success=True,
                        final_answer="Test answer",
                        metrics_summary={},
                        outcome_judge=OutcomeJudgeReport(
                            goal="Test goal 1",
                            execution_profile_name="balanced",
                            context_strategies=[],
                            global_review=OutcomeGlobalReview(
                                overall_success=True,
                                global_score=0.85,
                                main_issues=[],
                                main_strengths=[],
                                recommendations=[]
                            ),
                            sub_goals=[],
                            next_run_profile_suggestion=None,
                            next_run_notes=None,
                            llm_raw_notes=None
                        ),
                    ),
                    BatchAgentGoalResult(
                        id="worker_2",
                        goal="Test goal 2",
                        success=True,
                        final_answer="Test answer",
                        metrics_summary={},
                        outcome_judge=OutcomeJudgeReport(
                            goal="Test goal 2",
                            execution_profile_name="balanced",
                            context_strategies=[],
                            global_review=OutcomeGlobalReview(
                                overall_success=True,
                                global_score=0.55,  # Score bajo
                                main_issues=[],
                                main_strengths=[],
                                recommendations=[]
                            ),
                            sub_goals=[],
                            next_run_profile_suggestion=None,
                            next_run_notes=None,
                            llm_raw_notes=None
                        ),
                    ),
                ],
                summary={}
            )
            
            cae_response = build_cae_response_from_batch(cae_request, batch_response)
            
            # Verificar información de outcome en summary
            summary = cae_response.summary
            assert "avg_outcome_score_workers" in summary
            # Media: (0.85 + 0.55) / 2 = 0.70
            assert abs(summary["avg_outcome_score_workers"] - 0.70) < 0.01
            assert summary["workers_with_low_score"] == 1  # worker_2 tiene score < 0.6
            assert "regressions_detected" in summary
            assert "regression_threshold" in summary

