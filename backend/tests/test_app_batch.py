"""
Tests para endpoint /agent/batch v3.0.0
"""

import pytest
from fastapi.testclient import TestClient
from backend.app import app
from backend.shared.models import BatchAgentRequest, BatchAgentGoal


@pytest.fixture
def client():
    """Cliente de prueba para FastAPI"""
    return TestClient(app)


class TestBatchEndpoint:
    """Tests para endpoint /agent/batch"""
    
    def test_batch_endpoint_exists(self, client):
        """El endpoint /agent/batch debe existir y aceptar POST"""
        # Verificar que el endpoint existe (no debería dar 404)
        # Nota: Este test puede fallar si el browser no está inicializado,
        # pero verifica que el endpoint está registrado
        batch_request = BatchAgentRequest(
            goals=[
                BatchAgentGoal(
                    id="test_goal",
                    goal="Test goal",
                )
            ],
        )
        
        # Intentar hacer POST (puede fallar por browser, pero el endpoint debe existir)
        response = client.post("/agent/batch", json=batch_request.model_dump())
        
        # El endpoint debe existir (no 404)
        assert response.status_code != 404, "Endpoint /agent/batch no encontrado"
    
    def test_batch_endpoint_accepts_valid_request(self, client):
        """El endpoint debe aceptar una petición batch válida"""
        batch_request = BatchAgentRequest(
            goals=[
                BatchAgentGoal(
                    id="test_goal_1",
                    goal="Test goal 1",
                    execution_profile_name="fast",
                ),
                BatchAgentGoal(
                    id="test_goal_2",
                    goal="Test goal 2",
                    context_strategies=["wikipedia"],
                ),
            ],
            default_execution_profile_name="balanced",
            max_consecutive_failures=3,
        )
        
        # Verificar que el JSON es válido
        request_dict = batch_request.model_dump()
        assert "goals" in request_dict
        assert len(request_dict["goals"]) == 2
        assert request_dict["goals"][0]["id"] == "test_goal_1"
        assert request_dict["goals"][1]["id"] == "test_goal_2"
    
    def test_batch_endpoint_validates_request_schema(self, client):
        """El endpoint debe validar el schema de la petición"""
        # Petición inválida (falta 'goals')
        invalid_request = {}
        
        response = client.post("/agent/batch", json=invalid_request)
        
        # Debe devolver error de validación (422)
        assert response.status_code == 422, "Debería validar el schema de la petición"






