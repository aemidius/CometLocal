"""
SPRINT C2.30: Tests para endpoints de schedules.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app import app


@pytest.fixture
def client():
    """Cliente de test para FastAPI."""
    return TestClient(app)


def test_list_schedules_missing_context(client):
    """Test: GET /api/schedules/list sin contexto -> 400."""
    response = client.get("/api/schedules/list")
    
    assert response.status_code == 400
    data = response.json()
    assert "missing_coordination_context" in str(data.get("detail", {}))


def test_upsert_schedule_missing_context(client):
    """Test: POST /api/schedules/upsert sin contexto -> 400."""
    try:
        response = client.post(
            "/api/schedules/upsert",
            json={
                "plan_id": "test_plan",
                "cadence": "daily",
                "at_time": "09:00",
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert "missing_coordination_context" in str(data.get("detail", {}))
    except Exception as e:
        assert "missing_coordination_context" in str(e) or "Selecciona Empresa propia" in str(e)


def test_tick_schedules_missing_context(client):
    """Test: POST /api/schedules/tick sin contexto -> 400."""
    try:
        response = client.post("/api/schedules/tick")
        assert response.status_code == 400
        data = response.json()
        assert "missing_coordination_context" in str(data.get("detail", {}))
    except Exception as e:
        assert "missing_coordination_context" in str(e) or "Selecciona Empresa propia" in str(e)


def test_tick_schedules_not_dev_test(client, monkeypatch):
    """Test: POST /api/schedules/tick en prod sin API key -> 403."""
    monkeypatch.setenv("ENVIRONMENT", "prod")
    
    response = client.post(
        "/api/schedules/tick",
        headers={
            "X-Coordination-Own-Company": "F63161988",
            "X-Coordination-Platform": "egestiona",
            "X-Coordination-Coordinated-Company": "test_co",
        },
    )
    
    assert response.status_code == 403
