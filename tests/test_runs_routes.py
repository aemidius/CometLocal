"""
SPRINT C2.29: Tests para endpoints de runs.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.shared.context_guardrails import has_human_coordination_context


@pytest.fixture
def client():
    """Cliente de test para FastAPI."""
    return TestClient(app)


def test_start_run_missing_context(client):
    """Test: POST /api/runs/start sin contexto humano -> 400."""
    # El middleware de guardrail bloquea antes de llegar al endpoint
    # TestClient puede lanzar la excepción directamente, así que capturamos ambos casos
    try:
        response = client.post(
            "/api/runs/start",
            json={"plan_id": "test_plan"},
        )
        # Si llega aquí, debe ser 400
        assert response.status_code == 400
        data = response.json()
        assert "missing_coordination_context" in str(data.get("detail", {}))
    except Exception as e:
        # Si el middleware lanza excepción directamente, verificar que es HTTPException con el mensaje correcto
        assert "missing_coordination_context" in str(e) or "Selecciona Empresa propia" in str(e)


def test_start_run_with_context(client):
    """Test: POST /api/runs/start con contexto humano válido."""
    # Este test requiere un plan real, así que lo marcamos como skip si no hay datos
    # En un entorno real, se necesitaría seed de datos
    
    response = client.post(
        "/api/runs/start",
        json={"plan_id": "nonexistent_plan", "dry_run": True},
        headers={
            "X-Coordination-Own-Company": "F63161988",
            "X-Coordination-Platform": "egestiona",
            "X-Coordination-Coordinated-Company": "test_co",
        },
    )
    
    # Debe fallar porque el plan no existe, pero no por falta de contexto
    assert response.status_code in [404, 400]  # 404 si plan no existe, 400 si validación falla
    data = response.json()
    # No debe ser error de contexto
    assert "missing_coordination_context" not in str(data.get("detail", {}))


def test_get_latest_run_missing_context(client):
    """Test: GET /api/runs/latest sin contexto -> 400."""
    response = client.get("/api/runs/latest")
    
    assert response.status_code == 400
    data = response.json()
    assert "missing_coordination_context" in str(data.get("detail", {}))


def test_get_run_missing_context(client):
    """Test: GET /api/runs/<run_id> sin contexto -> 400."""
    response = client.get("/api/runs/test_run_id")
    
    assert response.status_code == 400
    data = response.json()
    assert "missing_coordination_context" in str(data.get("detail", {}))
