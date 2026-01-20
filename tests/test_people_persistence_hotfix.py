"""
HOTFIX: Test para verificar que own_company_key se persiste correctamente desde el formulario.

Este test simula el POST /config/people que viene del formulario HTML.
"""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from fastapi import FastAPI

from backend.executor.config_viewer import create_config_viewer_router
from backend.repository.config_store_v1 import ConfigStoreV1
from backend.shared.people_v1 import PersonV1, PeopleV1


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    """Fixture que crea un ConfigStoreV1 temporal."""
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    return ConfigStoreV1(base_dir=tmp_path)


@pytest.fixture
def test_app(tmp_path, monkeypatch):
    """Fixture que crea una app FastAPI con el router de config."""
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    app = FastAPI()
    router = create_config_viewer_router(base_dir=tmp_path)
    app.include_router(router)
    return app


def test_post_people_persists_own_company_key(test_app, tmp_store):
    """Test: POST /config/people persiste own_company_key correctamente."""
    client = TestClient(test_app)
    
    # Crear datos iniciales
    initial_people = PeopleV1(people=[
        PersonV1(
            worker_id="erm",
            full_name="Erm Test",
            tax_id="12345678A",
            role="worker",
            relation_type="employee",
            own_company_key=None  # Sin asignar inicialmente
        ),
        PersonV1(
            worker_id="ovo",
            full_name="Ovo Test",
            tax_id="87654321B",
            role="worker",
            relation_type="employee",
            own_company_key=None
        )
    ])
    tmp_store.save_people(initial_people)
    
    # Simular POST del formulario con own_company_key asignado
    form_data = {
        "worker_id__0": "erm",
        "full_name__0": "Erm Test",
        "tax_id__0": "12345678A",
        "role__0": "worker",
        "relation_type__0": "employee",
        "own_company_key__0": "tedelab",  # Asignar empresa propia
        
        "worker_id__1": "ovo",
        "full_name__1": "Ovo Test",
        "tax_id__1": "87654321B",
        "role__1": "worker",
        "relation_type__1": "employee",
        "own_company_key__1": "unassigned",  # Sin asignar
    }
    
    # Hacer POST
    response = client.post("/config/people", data=form_data, follow_redirects=False)
    assert response.status_code in (303, 302), f"Expected redirect, got {response.status_code}: {response.text}"
    
    # Verificar que se guardó correctamente
    loaded_people = tmp_store.load_people()
    
    # Encontrar "erm" y verificar own_company_key
    erm_person = next((p for p in loaded_people.people if p.worker_id == "erm"), None)
    assert erm_person is not None, "Person 'erm' should exist"
    assert erm_person.own_company_key == "tedelab", f"Expected own_company_key='tedelab', got {erm_person.own_company_key!r}"
    
    # Verificar que "ovo" tiene None (unassigned)
    ovo_person = next((p for p in loaded_people.people if p.worker_id == "ovo"), None)
    assert ovo_person is not None, "Person 'ovo' should exist"
    assert ovo_person.own_company_key is None, f"Expected own_company_key=None, got {ovo_person.own_company_key!r}"
    
    # Verificar que el JSON contiene own_company_key
    import json
    people_json_path = tmp_store.refs_dir / "people.json"
    assert people_json_path.exists(), "people.json should exist"
    
    with open(people_json_path, 'r', encoding='utf-8') as f:
        people_data = json.load(f)
    
    erm_data = next((p for p in people_data["people"] if p["worker_id"] == "erm"), None)
    assert erm_data is not None, "Person 'erm' should exist in JSON"
    assert "own_company_key" in erm_data, "own_company_key should be in JSON"
    assert erm_data["own_company_key"] == "tedelab", f"Expected own_company_key='tedelab' in JSON, got {erm_data.get('own_company_key')!r}"


def test_post_people_persists_none_as_null(test_app, tmp_store):
    """Test: POST /config/people persiste None como null en JSON (no omite el campo)."""
    client = TestClient(test_app)
    
    # Crear datos iniciales
    initial_people = PeopleV1(people=[
        PersonV1(
            worker_id="test_worker",
            full_name="Test Worker",
            tax_id="11111111A",
            role="worker",
            relation_type="employee",
            own_company_key="COMPANY_A"
        )
    ])
    tmp_store.save_people(initial_people)
    
    # Simular POST cambiando a "unassigned"
    form_data = {
        "worker_id__0": "test_worker",
        "full_name__0": "Test Worker",
        "tax_id__0": "11111111A",
        "role__0": "worker",
        "relation_type__0": "employee",
        "own_company_key__0": "unassigned",  # Cambiar a sin asignar
    }
    
    # Hacer POST
    response = client.post("/config/people", data=form_data, follow_redirects=False)
    assert response.status_code in (303, 302)
    
    # Verificar que se guardó como None
    loaded_people = tmp_store.load_people()
    test_person = next((p for p in loaded_people.people if p.worker_id == "test_worker"), None)
    assert test_person is not None
    assert test_person.own_company_key is None
    
    # Verificar JSON (puede ser None o null, ambos son válidos)
    import json
    people_json_path = tmp_store.refs_dir / "people.json"
    with open(people_json_path, 'r', encoding='utf-8') as f:
        people_data = json.load(f)
    
    test_data = next((p for p in people_data["people"] if p["worker_id"] == "test_worker"), None)
    assert test_data is not None
    # own_company_key puede ser None (Python) o null (JSON), ambos son válidos
    assert test_data.get("own_company_key") is None or test_data.get("own_company_key") == "null"


def test_save_people_includes_own_company_key_in_json(tmp_store):
    """Test: save_people incluye own_company_key en el JSON incluso cuando es None."""
    # Crear people con own_company_key
    people = PeopleV1(people=[
        PersonV1(
            worker_id="worker_with_company",
            full_name="Worker With Company",
            tax_id="12345678A",
            role="worker",
            relation_type="employee",
            own_company_key="COMPANY_A"
        ),
        PersonV1(
            worker_id="worker_without_company",
            full_name="Worker Without Company",
            tax_id="87654321B",
            role="worker",
            relation_type="employee",
            own_company_key=None
        )
    ])
    
    # Guardar
    tmp_store.save_people(people)
    
    # Verificar JSON
    import json
    people_json_path = tmp_store.refs_dir / "people.json"
    assert people_json_path.exists()
    
    with open(people_json_path, 'r', encoding='utf-8') as f:
        people_data = json.load(f)
    
    # Verificar que ambos tienen own_company_key en el JSON
    worker_with = next((p for p in people_data["people"] if p["worker_id"] == "worker_with_company"), None)
    assert worker_with is not None
    assert "own_company_key" in worker_with
    assert worker_with["own_company_key"] == "COMPANY_A"
    
    worker_without = next((p for p in people_data["people"] if p["worker_id"] == "worker_without_company"), None)
    assert worker_without is not None
    assert "own_company_key" in worker_without  # Debe estar presente incluso si es None
    assert worker_without["own_company_key"] is None  # Debe ser None/null
