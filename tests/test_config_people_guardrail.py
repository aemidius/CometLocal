"""
HOTFIX: Tests para verificar que el guardrail de contexto funciona correctamente para /config/people.

Verifica:
1. POST sin headers devuelve 400 (no 500)
2. POST con headers válidos funciona
3. El mensaje de error es claro
"""

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from backend.executor.config_viewer import create_config_viewer_router
from backend.repository.config_store_v1 import ConfigStoreV1
from backend.shared.people_v1 import PersonV1, PeopleV1
from pathlib import Path


@pytest.fixture
def test_app(tmp_path, monkeypatch):
    """Fixture que crea una app FastAPI con el router de config."""
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    app = FastAPI()
    
    # HOTFIX: Añadir exception handler para HTTPException ANTES del middleware
    # (FastAPI procesa exception handlers en orden de registro)
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail}
        )
    
    router = create_config_viewer_router(base_dir=tmp_path)
    app.include_router(router)
    
    # Añadir middleware de guardrail (simular app.py)
    from backend.shared.context_guardrails import validate_write_request_context
    from fastapi import Request
    
    @app.middleware("http")
    async def context_guardrail_middleware(request: Request, call_next):
        try:
            validate_write_request_context(request)
        except HTTPException as exc:
            # HOTFIX: Devolver respuesta JSON directamente desde el middleware
            # (igual que en app.py)
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail}
            )
        except Exception:
            # Otros errores: continuar sin bloquear
            pass
        response = await call_next(request)
        return response
    
    return app


def test_post_people_without_headers_returns_400_not_500(test_app, tmp_path):
    """Test: POST /config/people sin headers devuelve 400 (no 500)."""
    client = TestClient(test_app, raise_server_exceptions=False)
    
    # Crear datos iniciales
    store = ConfigStoreV1(base_dir=tmp_path)
    initial_people = PeopleV1(people=[
        PersonV1(
            worker_id="test_worker",
            full_name="Test Worker",
            tax_id="12345678A",
            role="worker",
            relation_type="employee"
        )
    ])
    store.save_people(initial_people)
    
    # Simular POST sin headers de contexto
    form_data = {
        "worker_id__0": "test_worker",
        "full_name__0": "Test Worker",
        "tax_id__0": "12345678A",
        "role__0": "worker",
        "relation_type__0": "employee",
        "own_company_key__0": "unassigned"
    }
    
    # Hacer POST sin headers (raise_server_exceptions=False para que no lance excepción)
    response = client.post("/config/people", data=form_data)
    
    # HOTFIX: Debug - ver qué está devolviendo
    if response.status_code != 400:
        print(f"[DEBUG] Status: {response.status_code}, Text: {response.text[:500]}")
    
    # Verificar que devuelve 400 (no 500)
    # Nota: Si el exception handler no funciona, puede devolver 500, pero el test debe fallar claramente
    assert response.status_code == 400, f"Expected 400, got {response.status_code}. Response: {response.text[:500]}"
    
    # Verificar que el mensaje es claro
    error_data = response.json()
    assert "detail" in error_data
    detail = error_data["detail"]
    
    if isinstance(detail, dict):
        assert detail.get("error") == "missing_coordination_context"
        assert "message" in detail
        assert "Selecciona Empresa propia" in detail["message"]
    else:
        # Puede ser string también
        assert "coordination" in str(detail).lower() or "contexto" in str(detail).lower()


def test_post_people_with_headers_works(test_app, tmp_path):
    """Test: POST /config/people con headers válidos funciona."""
    client = TestClient(test_app)
    
    # Crear datos iniciales
    store = ConfigStoreV1(base_dir=tmp_path)
    initial_people = PeopleV1(people=[
        PersonV1(
            worker_id="test_worker",
            full_name="Test Worker",
            tax_id="12345678A",
            role="worker",
            relation_type="employee"
        )
    ])
    store.save_people(initial_people)
    
    # Simular POST con headers de contexto válidos
    form_data = {
        "worker_id__0": "test_worker",
        "full_name__0": "Test Worker",
        "tax_id__0": "12345678A",
        "role__0": "worker",
        "relation_type__0": "employee",
        "own_company_key__0": "COMPANY_A"
    }
    
    # Hacer POST con headers válidos
    response = client.post(
        "/config/people",
        data=form_data,
        headers={
            "X-Coordination-Own-Company": "COMPANY_A",
            "X-Coordination-Platform": "egestiona",
            "X-Coordination-Coordinated-Company": "CLIENT_001"
        },
        follow_redirects=False
    )
    
    # Verificar que funciona (redirección 303 o 302)
    assert response.status_code in (303, 302), f"Expected redirect, got {response.status_code}: {response.text}"
    
    # Verificar que se guardó correctamente
    loaded_people = store.load_people()
    test_person = next((p for p in loaded_people.people if p.worker_id == "test_worker"), None)
    assert test_person is not None
    assert test_person.own_company_key == "COMPANY_A"


def test_post_people_incomplete_headers_returns_400(test_app, tmp_path):
    """Test: POST /config/people con headers incompletos devuelve 400."""
    client = TestClient(test_app, raise_server_exceptions=False)
    
    # Crear datos iniciales
    store = ConfigStoreV1(base_dir=tmp_path)
    initial_people = PeopleV1(people=[
        PersonV1(
            worker_id="test_worker",
            full_name="Test Worker",
            tax_id="12345678A",
            role="worker",
            relation_type="employee"
        )
    ])
    store.save_people(initial_people)
    
    form_data = {
        "worker_id__0": "test_worker",
        "full_name__0": "Test Worker",
        "tax_id__0": "12345678A",
        "role__0": "worker",
        "relation_type__0": "employee",
        "own_company_key__0": "COMPANY_A"
    }
    
    # Hacer POST con solo un header (incompleto)
    response = client.post(
        "/config/people",
        data=form_data,
        headers={
            "X-Coordination-Own-Company": "COMPANY_A"
            # Faltan Platform y Coordinated-Company
        }
    )
    
    # Debe devolver 400
    assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
