"""
Tests para endpoint /agent/cae/batch v3.1.0
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.shared.models import (
    CAEBatchRequest,
    CAEWorker,
    CAEBatchResponse,
    BatchAgentResponse,
    BatchAgentGoalResult,
)


class TestCAEBatchEndpoint:
    """Tests para endpoint /agent/cae/batch"""
    
    def test_cae_batch_endpoint_schema_validation(self):
        """El endpoint debe validar el schema de CAEBatchRequest"""
        # Este test verifica que el schema es correcto
        # La validación real se hace en FastAPI
        request = CAEBatchRequest(
            platform="test_platform",
            company_name="EmpresaTest",
            workers=[
                CAEWorker(
                    id="worker_1",
                    full_name="Juan Pérez",
                ),
            ],
        )
        
        # Verificar que el modelo es válido
        assert request.platform == "test_platform"
        assert request.company_name == "EmpresaTest"
        assert len(request.workers) == 1
        assert request.workers[0].id == "worker_1"
    
    def test_cae_batch_request_defaults(self):
        """CAEBatchRequest debe tener valores por defecto correctos"""
        request = CAEBatchRequest(
            platform="test_platform",
            company_name="EmpresaTest",
            workers=[
                CAEWorker(
                    id="worker_1",
                    full_name="Test Worker",
                ),
            ],
        )
        
        # Verificar defaults
        assert request.execution_profile_name == "balanced"
        assert request.max_consecutive_failures == 5
        # context_strategies puede ser None, se maneja en el adaptador
    
    def test_cae_batch_response_structure(self):
        """CAEBatchResponse debe tener la estructura correcta"""
        response = CAEBatchResponse(
            platform="test_platform",
            company_name="EmpresaTest",
            workers=[],
            summary={
                "total_workers": 0,
                "success_count": 0,
                "failure_count": 0,
            },
        )
        
        assert response.platform == "test_platform"
        assert response.company_name == "EmpresaTest"
        assert isinstance(response.workers, list)
        assert isinstance(response.summary, dict)
        assert "total_workers" in response.summary


















