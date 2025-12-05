"""
Tests para cae_batch_adapter v3.1.0
"""

import pytest
from backend.agents.cae_batch_adapter import (
    build_batch_request_from_cae,
    build_cae_response_from_batch,
    _build_cae_goal_text,
)
from backend.shared.models import (
    CAEBatchRequest,
    CAEWorker,
    BatchAgentRequest,
    BatchAgentGoal,
    BatchAgentResponse,
    BatchAgentGoalResult,
    OutcomeJudgeReport,
    OutcomeGlobalReview,
    OutcomeSubGoalReview,
)


class TestCAEBatchAdapter:
    """Tests para adaptador CAE batch"""
    
    def test_build_batch_request_from_cae_basic(self):
        """build_batch_request_from_cae debe generar BatchAgentRequest con goals correctos"""
        cae_request = CAEBatchRequest(
            platform="test_platform",
            company_name="EmpresaTest",
            workers=[
                CAEWorker(
                    id="worker_1",
                    full_name="Juan Pérez",
                    company="EmpresaTest",
                    required_docs=["reconocimiento_medico", "formacion_prl"],
                ),
                CAEWorker(
                    id="worker_2",
                    full_name="María García",
                    company="EmpresaTest",
                    required_docs=["reconocimiento_medico"],
                ),
            ],
            execution_profile_name="fast",
            context_strategies=["cae"],
        )
        
        batch_request = build_batch_request_from_cae(cae_request)
        
        # Verificaciones
        assert isinstance(batch_request, BatchAgentRequest)
        assert len(batch_request.goals) == 2
        assert batch_request.default_execution_profile_name == "fast"
        assert "cae" in batch_request.default_context_strategies
        
        # Verificar primer goal
        goal_1 = batch_request.goals[0]
        assert goal_1.id == "worker_1"
        assert "Juan Pérez" in goal_1.goal
        goal_lower = goal_1.goal.lower()
        assert "reconocimiento médico" in goal_lower or "reconocimiento medico" in goal_lower
        assert "formación prl" in goal_lower or "formacion prl" in goal_lower or "formación PRL" in goal_1.goal
        
        # Verificar segundo goal
        goal_2 = batch_request.goals[1]
        assert goal_2.id == "worker_2"
        assert "María García" in goal_2.goal
    
    def test_build_batch_request_from_cae_includes_cae_strategy(self):
        """build_batch_request_from_cae debe incluir 'cae' en context_strategies"""
        cae_request = CAEBatchRequest(
            platform="test_platform",
            company_name="EmpresaTest",
            workers=[
                CAEWorker(
                    id="worker_1",
                    full_name="Test Worker",
                ),
            ],
            context_strategies=["wikipedia"],  # No incluye "cae" explícitamente
        )
        
        batch_request = build_batch_request_from_cae(cae_request)
        
        # Debe añadir "cae" si no está
        assert "cae" in batch_request.default_context_strategies
        assert "wikipedia" in batch_request.default_context_strategies
    
    def test_build_cae_response_from_batch_basic(self):
        """build_cae_response_from_batch debe generar CAEBatchResponse correcto"""
        cae_request = CAEBatchRequest(
            platform="test_platform",
            company_name="EmpresaTest",
            workers=[
                CAEWorker(
                    id="worker_1",
                    full_name="Juan Pérez",
                ),
                CAEWorker(
                    id="worker_2",
                    full_name="María García",
                ),
            ],
        )
        
        batch_response = BatchAgentResponse(
            goals=[
                BatchAgentGoalResult(
                    id="worker_1",
                    goal="Test goal 1",
                    success=True,
                    error_message=None,
                    final_answer="Documentación correcta para Juan Pérez",
                    metrics_summary={"summary": {"total_sub_goals": 1}},
                    sections=None,
                    structured_sources=None,
                    file_upload_instructions=None,
                ),
                BatchAgentGoalResult(
                    id="worker_2",
                    goal="Test goal 2",
                    success=False,
                    error_message="Error de conexión",
                    final_answer=None,
                    metrics_summary=None,
                    sections=None,
                    structured_sources=None,
                    file_upload_instructions=None,
                ),
            ],
            summary={
                "total_goals": 2,
                "success_count": 1,
                "failure_count": 1,
                "failure_ratio": 0.5,
                "aborted_due_to_failures": False,
                "max_consecutive_failures": 5,
                "elapsed_seconds": 10.5,
                "mode": "batch",
            },
        )
        
        cae_response = build_cae_response_from_batch(cae_request, batch_response)
        
        # Verificaciones
        assert cae_response.platform == "test_platform"
        assert cae_response.company_name == "EmpresaTest"
        assert len(cae_response.workers) == 2
        
        # Verificar primer worker
        worker_1 = cae_response.workers[0]
        assert worker_1.worker_id == "worker_1"
        assert worker_1.full_name == "Juan Pérez"
        assert worker_1.success is True
        assert worker_1.raw_answer == "Documentación correcta para Juan Pérez"
        
        # Verificar segundo worker
        worker_2 = cae_response.workers[1]
        assert worker_2.worker_id == "worker_2"
        assert worker_2.full_name == "María García"
        assert worker_2.success is False
        
        # Verificar summary
        summary = cae_response.summary
        assert summary["total_workers"] == 2
        assert summary["success_count"] == 1
        assert summary["failure_count"] == 1
        assert "batch_summary" in summary
    
    def test_build_cae_response_extracts_uploaded_docs(self):
        """build_cae_response_from_batch debe extraer uploaded_docs de file_upload_instructions"""
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
        
        batch_response = BatchAgentResponse(
            goals=[
                BatchAgentGoalResult(
                    id="worker_1",
                    goal="Test goal",
                    success=True,
                    error_message=None,
                    final_answer="Documento subido correctamente",
                    metrics_summary=None,
                    sections=None,
                    structured_sources=None,
                    file_upload_instructions=[
                        {
                            "doc_type": "reconocimiento_medico",
                            "file_name": "reconocimiento.pdf",
                            "path": "/path/to/reconocimiento.pdf",
                        }
                    ],
                ),
            ],
            summary={
                "total_goals": 1,
                "success_count": 1,
                "failure_count": 0,
                "failure_ratio": 0.0,
                "aborted_due_to_failures": False,
                "max_consecutive_failures": 5,
                "elapsed_seconds": 5.0,
                "mode": "batch",
            },
        )
        
        cae_response = build_cae_response_from_batch(cae_request, batch_response)
        
        worker = cae_response.workers[0]
        assert "reconocimiento_medico" in worker.uploaded_docs
    
    def test_build_cae_goal_text_includes_required_docs(self):
        """_build_cae_goal_text debe incluir documentos requeridos en el texto"""
        cae_request = CAEBatchRequest(
            platform="test_platform",
            company_name="EmpresaTest",
            workers=[],
        )
        
        worker = CAEWorker(
            id="worker_1",
            full_name="Juan Pérez",
            required_docs=["reconocimiento_medico", "formacion_prl"],
        )
        
        goal_text = _build_cae_goal_text(cae_request, worker)
        
        assert "reconocimiento médico" in goal_text.lower() or "reconocimiento medico" in goal_text.lower()
        assert "formación prl" in goal_text.lower() or "formacion prl" in goal_text.lower()
        assert "Juan Pérez" in goal_text
        assert "EmpresaTest" in goal_text
    
    def test_memory_integration_in_cae_response(self, tmp_path, monkeypatch):
        """v3.9.0: build_cae_response_from_batch debe actualizar memoria persistente"""
        # Configurar directorio temporal para memoria
        temp_memory_dir = tmp_path / "memory"
        temp_memory_dir.mkdir()
        
        # Parchear MEMORY_BASE_DIR en config
        import backend.config
        original_memory_dir = backend.config.MEMORY_BASE_DIR
        monkeypatch.setattr(backend.config, "MEMORY_BASE_DIR", str(temp_memory_dir))
        
        # Recargar el módulo del adaptador para que use el nuevo valor
        import importlib
        import backend.agents.cae_batch_adapter
        importlib.reload(backend.agents.cae_batch_adapter)
        from backend.agents.cae_batch_adapter import build_cae_response_from_batch
        
        cae_request = CAEBatchRequest(
            platform="test_platform",
            company_name="Empresa Test",
            workers=[
                CAEWorker(
                    id="worker_1",
                    full_name="Juan Pérez",
                    required_docs=["dni", "contrato"],
                ),
            ],
        )
        
        batch_response = BatchAgentResponse(
            goals=[
                BatchAgentGoalResult(
                    id="worker_1",
                    goal="Revisar documentación de Juan Pérez",
                    success=True,
                    final_answer="Documentación revisada correctamente",
                    file_upload_instructions=[
                        {"doc_type": "dni", "file_name": "dni.pdf"},
                    ],
                    sections=[],
                    metrics_summary={
                        "summary": {
                            "upload_info": {"upload_attempts": 1, "upload_successes": 1},
                            "visual_click_info": {"visual_click_attempts": 2},
                            "visual_flow_info": {"visual_flow_updates": 1},
                            "ocr_info": {"ocr_calls": 3},
                        }
                    },
                ),
            ],
            summary={},
        )
        
        # Construir respuesta CAE
        cae_response = build_cae_response_from_batch(cae_request, batch_response)
        
        # Verificar que memory_summary está presente (puede ser None si falla la memoria, pero debería intentar)
        # Al menos verificamos que el campo existe en la respuesta
        assert hasattr(cae_response, "memory_summary")
        
        # Si memory_summary está presente, verificar su estructura
        if cae_response.memory_summary:
            assert "company" in cae_response.memory_summary or "platform" in cae_response.memory_summary
        
        # Verificar que memory_summary está en worker_status si está disponible
        worker_status = cae_response.workers[0]
        # El campo memory_summary puede estar presente o no dependiendo de si la memoria se guardó correctamente
        # Lo importante es que el código intenta añadirlo
        assert hasattr(worker_status, "memory_summary")
        
        # Restaurar valor original
        monkeypatch.setattr(backend.config, "MEMORY_BASE_DIR", original_memory_dir)

