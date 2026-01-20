"""
Tests E2E para /config/people según requisitos del fix.

Verifica:
1. GET /config/people siempre devuelve 200 (nunca 500)
2. POST sin contexto devuelve 400 JSON (no 500)
3. POST con contexto persiste own_company_key correctamente
4. own_company_key nunca se guarda como "-- Todas --" (solo es filtro)
5. "Sin asignar" se guarda como null
"""

import pytest
import json
from fastapi.testclient import TestClient
from fastapi import FastAPI
from pathlib import Path

from backend.executor.config_viewer import create_config_viewer_router
from backend.repository.config_store_v1 import ConfigStoreV1
from backend.shared.people_v1 import PersonV1, PeopleV1
from backend.shared.org_v1 import OrgV1


@pytest.fixture
def test_app(tmp_path, monkeypatch):
    """Fixture que crea una app FastAPI con el router de config y middleware."""
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    app = FastAPI()
    
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
    
    # Añadir middleware de guardrail (igual que app.py)
    from backend.shared.context_guardrails import validate_write_request_context
    from fastapi import Request
    
    @app.middleware("http")
    async def context_guardrail_middleware(request: Request, call_next):
        try:
            validate_write_request_context(request)
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail}
            )
        except Exception:
            pass
        response = await call_next(request)
        return response
    
    return app


def test_get_config_people_renders_200(test_app, tmp_path):
    """
    Test: GET /config/people siempre devuelve 200 y contiene texto "Config — People".
    
    Criterio de aceptación A: curl devuelve 200 y la página renderiza.
    """
    client = TestClient(test_app)
    
    # Inicializar datos mínimos
    store = ConfigStoreV1(base_dir=tmp_path)
    store.save_org(OrgV1(legal_name="Test Org", tax_id="TEST123", org_type="SCCL", notes=""))
    store.save_people(PeopleV1(people=[]))
    
    # Hacer GET
    response = client.get("/config/people")
    
    # CRÍTICO: Debe devolver 200, nunca 500
    assert response.status_code == 200, f"GET /config/people debe devolver 200, pero devolvió {response.status_code}. Response: {response.text[:500]}"
    
    # Verificar que contiene texto esperado
    assert "Config" in response.text or "People" in response.text or "Trabajadores" in response.text, \
        f"La respuesta debe contener 'Config' o 'People' o 'Trabajadores'. Response: {response.text[:500]}"
    
    # Verificar que es HTML
    assert "text/html" in response.headers.get("content-type", ""), \
        f"Debe ser HTML, pero content-type es: {response.headers.get('content-type')}"


def test_post_people_without_context_returns_400(test_app, tmp_path):
    """
    Test: POST /config/people sin headers devuelve 400 JSON con error missing_coordination_context.
    
    Criterio de aceptación B: Guardrail devuelve 400 JSON (no 500).
    """
    client = TestClient(test_app, raise_server_exceptions=False)
    
    # Inicializar datos
    store = ConfigStoreV1(base_dir=tmp_path)
    store.save_org(OrgV1(legal_name="Test Org", tax_id="TEST123", org_type="SCCL", notes=""))
    store.save_people(PeopleV1(people=[]))
    
    # POST sin headers de contexto
    form_data = {
        "worker_id__0": "worker1",
        "full_name__0": "Worker One",
        "tax_id__0": "12345678A",
        "role__0": "worker",
        "relation_type__0": "employee",
        "own_company_key__0": "unassigned"
    }
    
    response = client.post("/config/people", data=form_data)
    
    # Debe devolver 400 (no 500)
    assert response.status_code == 400, \
        f"POST sin contexto debe devolver 400, pero devolvió {response.status_code}. Response: {response.text[:500]}"
    
    # Debe ser JSON
    assert "application/json" in response.headers.get("content-type", ""), \
        f"Debe ser JSON, pero content-type es: {response.headers.get('content-type')}"
    
    # Verificar estructura del error
    error_data = response.json()
    assert "detail" in error_data, f"Error debe tener 'detail'. Response: {error_data}"
    
    detail = error_data["detail"]
    if isinstance(detail, dict):
        assert detail.get("error") == "missing_coordination_context", \
            f"Error debe ser 'missing_coordination_context'. Detail: {detail}"
        assert "message" in detail, f"Error debe tener 'message'. Detail: {detail}"
    else:
        # Puede ser string también
        assert "coordination" in str(detail).lower() or "contexto" in str(detail).lower(), \
            f"Error debe mencionar 'coordination' o 'contexto'. Detail: {detail}"


def test_post_people_with_context_persists_own_company_key(test_app, tmp_path):
    """
    Test: POST con headers completos y payload que ponga un worker con own_company_key="tedelab" 
    y otro None. Verificar que el archivo data/refs/people.json contiene el campo en ambos.
    
    Criterio de aceptación C: tras guardar, recargar muestra lo mismo y data/refs/people.json coincide.
    """
    client = TestClient(test_app)
    
    # Inicializar datos
    store = ConfigStoreV1(base_dir=tmp_path)
    store.save_org(OrgV1(legal_name="Tedelab", tax_id="tedelab", org_type="SCCL", notes=""))
    store.save_people(PeopleV1(people=[]))
    
    # POST con headers válidos y dos workers: uno con own_company_key y otro sin asignar
    form_data = {
        "worker_id__0": "worker1",
        "full_name__0": "Worker One",
        "tax_id__0": "12345678A",
        "role__0": "worker",
        "relation_type__0": "employee",
        "own_company_key__0": "tedelab",  # Con empresa propia
        
        "worker_id__1": "worker2",
        "full_name__1": "Worker Two",
        "tax_id__1": "87654321B",
        "role__1": "admin",
        "relation_type__1": "employee",
        "own_company_key__1": "unassigned",  # Sin asignar (debe ser None)
    }
    
    headers = {
        "X-Coordination-Own-Company": "tedelab",
        "X-Coordination-Platform": "egestiona",
        "X-Coordination-Coordinated-Company": "client001"
    }
    
    # Hacer POST
    response = client.post("/config/people", data=form_data, headers=headers, follow_redirects=False)
    
    # Debe redirigir (303 o 302)
    assert response.status_code in (303, 302), \
        f"POST con contexto válido debe redirigir, pero devolvió {response.status_code}. Response: {response.text[:500]}"
    
    # Verificar que se guardó correctamente leyendo el archivo JSON directamente
    people_file = tmp_path / "refs" / "people.json"
    assert people_file.exists(), f"people.json debe existir en {people_file}"
    
    with open(people_file, "r", encoding="utf-8") as f:
        people_data = json.load(f)
    
    assert "people" in people_data, f"people.json debe tener 'people'. Data: {people_data}"
    people_list = people_data["people"]
    assert len(people_list) == 2, f"Debe haber 2 workers, pero hay {len(people_list)}"
    
    # Verificar worker1 tiene own_company_key="tedelab"
    worker1 = next((p for p in people_list if p.get("worker_id") == "worker1"), None)
    assert worker1 is not None, "worker1 debe existir"
    assert worker1.get("own_company_key") == "tedelab", \
        f"worker1 debe tener own_company_key='tedelab', pero tiene: {worker1.get('own_company_key')}"
    
    # Verificar worker2 tiene own_company_key=None (o no está presente)
    worker2 = next((p for p in people_list if p.get("worker_id") == "worker2"), None)
    assert worker2 is not None, "worker2 debe existir"
    assert worker2.get("own_company_key") is None, \
        f"worker2 debe tener own_company_key=None (o ausente), pero tiene: {worker2.get('own_company_key')}"
    
    # Verificar que al recargar (GET) se muestran los mismos valores
    get_response = client.get("/config/people")
    assert get_response.status_code == 200, f"GET después de POST debe devolver 200, pero devolvió {get_response.status_code}"
    
    # Verificar que los valores se muestran en el HTML
    assert "worker1" in get_response.text, "worker1 debe aparecer en el HTML"
    assert "worker2" in get_response.text, "worker2 debe aparecer en el HTML"
    
    # Verificar que al cargar con ConfigStore también coincide
    loaded_people = store.load_people()
    loaded_worker1 = next((p for p in loaded_people.people if p.worker_id == "worker1"), None)
    loaded_worker2 = next((p for p in loaded_people.people if p.worker_id == "worker2"), None)
    
    assert loaded_worker1 is not None, "loaded_worker1 debe existir"
    assert loaded_worker1.own_company_key == "tedelab", \
        f"loaded_worker1 debe tener own_company_key='tedelab', pero tiene: {loaded_worker1.own_company_key}"
    
    assert loaded_worker2 is not None, "loaded_worker2 debe existir"
    assert loaded_worker2.own_company_key is None, \
        f"loaded_worker2 debe tener own_company_key=None, pero tiene: {loaded_worker2.own_company_key}"


def test_post_people_never_saves_todas_as_value(test_app, tmp_path):
    """
    Test: Verificar que "-- Todas --" nunca se guarda como valor de own_company_key.
    Solo es para filtro, no para valor de fila.
    """
    client = TestClient(test_app)
    
    # Inicializar datos
    store = ConfigStoreV1(base_dir=tmp_path)
    store.save_org(OrgV1(legal_name="Test Org", tax_id="TEST123", org_type="SCCL", notes=""))
    store.save_people(PeopleV1(people=[]))
    
    # POST intentando guardar "-- Todas --" como valor (no debería ser posible desde UI, pero por si acaso)
    form_data = {
        "worker_id__0": "worker1",
        "full_name__0": "Worker One",
        "tax_id__0": "12345678A",
        "role__0": "worker",
        "relation_type__0": "employee",
        "own_company_key__0": "-- Todas --",  # Intentar guardar esto (debe convertirse a None)
    }
    
    headers = {
        "X-Coordination-Own-Company": "TEST123",
        "X-Coordination-Platform": "egestiona",
        "X-Coordination-Coordinated-Company": "client001"
    }
    
    response = client.post("/config/people", data=form_data, headers=headers, follow_redirects=False)
    assert response.status_code in (303, 302), f"POST debe redirigir, pero devolvió {response.status_code}"
    
    # Verificar que NO se guardó "-- Todas --"
    loaded_people = store.load_people()
    worker1 = next((p for p in loaded_people.people if p.worker_id == "worker1"), None)
    assert worker1 is not None, "worker1 debe existir"
    assert worker1.own_company_key != "-- Todas --", \
        f"own_company_key nunca debe ser '-- Todas --', pero es: {worker1.own_company_key}"
    assert worker1.own_company_key is None, \
        f"own_company_key debe ser None cuando se envía '-- Todas --', pero es: {worker1.own_company_key}"
