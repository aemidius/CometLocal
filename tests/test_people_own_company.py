"""
Tests para verificar que people está asociado a empresa propia (SPRINT C2.32A).

Verifica:
1. Migración suave: personas sin own_company_key siguen funcionando
2. Filtrado por own_company_key funciona correctamente
3. Helper get_people_for_own_company funciona
"""

import pytest
from pathlib import Path

from backend.shared.people_v1 import PersonV1, PeopleV1
from backend.repository.config_store_v1 import ConfigStoreV1
from backend.repository.config_routes import get_people_for_own_company


def test_person_without_own_company_key_is_valid():
    """Test: PersonV1 sin own_company_key es válido (migración suave)."""
    person = PersonV1(
        worker_id="worker_001",
        full_name="Juan Pérez",
        tax_id="12345678A",
        role="worker",
        relation_type="employee"
    )
    
    assert person.worker_id == "worker_001"
    assert person.own_company_key is None  # Por defecto None


def test_person_with_own_company_key():
    """Test: PersonV1 con own_company_key funciona correctamente."""
    person = PersonV1(
        worker_id="worker_001",
        full_name="Juan Pérez",
        tax_id="12345678A",
        role="worker",
        relation_type="employee",
        own_company_key="COMPANY_A"
    )
    
    assert person.own_company_key == "COMPANY_A"


def test_migration_smooth_loading(tmp_path, monkeypatch):
    """Test: Cargar people.json sin own_company_key no rompe nada."""
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    
    # Crear people.json sin own_company_key (formato antiguo)
    people_data = {
        "schema_version": "v1",
        "people": [
            {
                "worker_id": "worker_001",
                "full_name": "Juan Pérez",
                "tax_id": "12345678A",
                "role": "worker",
                "relation_type": "employee"
                # Sin own_company_key
            }
        ]
    }
    
    import json
    refs_dir = tmp_path / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "people.json").write_text(json.dumps(people_data, ensure_ascii=False), encoding="utf-8")
    
    # Cargar debe funcionar sin errores
    store = ConfigStoreV1(base_dir=tmp_path)
    people = store.load_people()
    
    assert len(people.people) == 1
    assert people.people[0].worker_id == "worker_001"
    assert people.people[0].own_company_key is None  # Debe ser None, no error


def test_filter_by_own_company_key(tmp_path, monkeypatch):
    """Test: Filtrado por own_company_key funciona correctamente."""
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    
    # Crear people con diferentes own_company_key
    people_data = {
        "schema_version": "v1",
        "people": [
            {
                "worker_id": "worker_a_1",
                "full_name": "Trabajador A1",
                "tax_id": "11111111A",
                "role": "worker",
                "relation_type": "employee",
                "own_company_key": "COMPANY_A"
            },
            {
                "worker_id": "worker_a_2",
                "full_name": "Trabajador A2",
                "tax_id": "22222222B",
                "role": "worker",
                "relation_type": "employee",
                "own_company_key": "COMPANY_A"
            },
            {
                "worker_id": "worker_b_1",
                "full_name": "Trabajador B1",
                "tax_id": "33333333C",
                "role": "worker",
                "relation_type": "employee",
                "own_company_key": "COMPANY_B"
            },
            {
                "worker_id": "worker_unassigned",
                "full_name": "Trabajador Sin Asignar",
                "tax_id": "44444444D",
                "role": "worker",
                "relation_type": "employee"
                # Sin own_company_key
            }
        ]
    }
    
    import json
    refs_dir = tmp_path / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "people.json").write_text(json.dumps(people_data, ensure_ascii=False), encoding="utf-8")
    
    store = ConfigStoreV1(base_dir=tmp_path)
    people = store.load_people()
    
    # Filtrar por COMPANY_A
    company_a_people = [p for p in people.people if p.own_company_key == "COMPANY_A"]
    assert len(company_a_people) == 2
    assert all(p.own_company_key == "COMPANY_A" for p in company_a_people)
    
    # Filtrar por COMPANY_B
    company_b_people = [p for p in people.people if p.own_company_key == "COMPANY_B"]
    assert len(company_b_people) == 1
    assert company_b_people[0].worker_id == "worker_b_1"
    
    # Filtrar sin asignar (own_company_key es None)
    unassigned_people = [p for p in people.people if p.own_company_key is None]
    assert len(unassigned_people) == 1
    assert unassigned_people[0].worker_id == "worker_unassigned"


def test_get_people_for_own_company_helper(tmp_path, monkeypatch):
    """Test: Helper get_people_for_own_company funciona correctamente."""
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    
    # Crear people con diferentes own_company_key
    people_data = {
        "schema_version": "v1",
        "people": [
            {
                "worker_id": "worker_a_1",
                "full_name": "Trabajador A1",
                "tax_id": "11111111A",
                "role": "worker",
                "relation_type": "employee",
                "own_company_key": "COMPANY_A"
            },
            {
                "worker_id": "worker_b_1",
                "full_name": "Trabajador B1",
                "tax_id": "22222222B",
                "role": "worker",
                "relation_type": "employee",
                "own_company_key": "COMPANY_B"
            }
        ]
    }
    
    import json
    refs_dir = tmp_path / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / "people.json").write_text(json.dumps(people_data, ensure_ascii=False), encoding="utf-8")
    
    # Usar helper
    company_a_people = get_people_for_own_company("COMPANY_A", base_dir=str(tmp_path))
    
    assert len(company_a_people) == 1
    assert company_a_people[0].worker_id == "worker_a_1"
    assert company_a_people[0].own_company_key == "COMPANY_A"
    
    # Verificar que COMPANY_B no está incluido
    company_b_people = get_people_for_own_company("COMPANY_B", base_dir=str(tmp_path))
    assert len(company_b_people) == 1
    assert company_b_people[0].worker_id == "worker_b_1"


def test_save_and_load_with_own_company_key(tmp_path, monkeypatch):
    """Test: Guardar y cargar people con own_company_key funciona."""
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    
    store = ConfigStoreV1(base_dir=tmp_path)
    
    # Crear people con own_company_key
    people = PeopleV1(people=[
        PersonV1(
            worker_id="worker_001",
            full_name="Juan Pérez",
            tax_id="12345678A",
            role="worker",
            relation_type="employee",
            own_company_key="COMPANY_A"
        )
    ])
    
    # Guardar
    store.save_people(people)
    
    # Cargar
    loaded_people = store.load_people()
    
    assert len(loaded_people.people) == 1
    assert loaded_people.people[0].worker_id == "worker_001"
    assert loaded_people.people[0].own_company_key == "COMPANY_A"
