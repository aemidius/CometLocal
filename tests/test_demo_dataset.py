"""
SPRINT C2.31: Tests para dataset demo.
"""

import pytest
import os
from pathlib import Path

from backend.shared.demo_dataset import (
    ensure_demo_dataset,
    is_demo_mode,
    get_demo_context,
    DEMO_OWN_COMPANY_KEY,
    DEMO_PLATFORM_KEY,
    DEMO_COORDINATED_COMPANY_KEY,
)
from backend.repository.config_store_v1 import ConfigStoreV1
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.shared.schedule_models import ScheduleStore
from backend.config import DATA_DIR


def test_is_demo_mode(monkeypatch):
    """Test: is_demo_mode detecta correctamente ENVIRONMENT=demo."""
    monkeypatch.setenv("ENVIRONMENT", "demo")
    assert is_demo_mode() is True
    
    monkeypatch.setenv("ENVIRONMENT", "dev")
    assert is_demo_mode() is False
    
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert is_demo_mode() is False


def test_get_demo_context():
    """Test: get_demo_context retorna contexto demo correcto."""
    context = get_demo_context()
    
    assert context["own_company_key"] == DEMO_OWN_COMPANY_KEY
    assert context["platform_key"] == DEMO_PLATFORM_KEY
    assert context["coordinated_company_key"] == DEMO_COORDINATED_COMPANY_KEY


def test_ensure_demo_dataset(tmp_path, monkeypatch):
    """Test: ensure_demo_dataset crea dataset demo completo."""
    # Usar tmp_path como DATA_DIR
    monkeypatch.setattr("backend.config.DATA_DIR", tmp_path)
    monkeypatch.setattr("backend.shared.demo_dataset.DATA_DIR", tmp_path)
    
    # Ejecutar ensure_demo_dataset
    result = ensure_demo_dataset()
    
    # Verificar que se creó
    assert result["created"] or result["tenant_id"] is not None
    
    # Verificar org
    store = ConfigStoreV1(base_dir=tmp_path)
    org = store.load_org()
    assert org.tax_id == DEMO_OWN_COMPANY_KEY
    assert "Demo" in org.legal_name
    
    # Verificar platform
    platforms = store.load_platforms()
    demo_platform = next((p for p in platforms.platforms if p.key == DEMO_PLATFORM_KEY), None)
    assert demo_platform is not None
    assert "Demo" in demo_platform.name
    
    # Verificar coordinated company
    demo_coord = next(
        (c for c in demo_platform.coordinations if c.client_code == DEMO_COORDINATED_COMPANY_KEY),
        None
    )
    assert demo_coord is not None
    assert "Demo" in demo_coord.label
    
    # Verificar tipos de documentos
    repo_store = DocumentRepositoryStoreV1(base_dir=tmp_path)
    types = repo_store.list_types()
    demo_types = [t for t in types if t.type_id.startswith("demo_")]
    assert len(demo_types) >= 3  # Al menos 3 tipos demo
    
    # Verificar documentos
    docs = repo_store.list_documents()
    demo_docs = [d for d in docs if d.doc_id.startswith("demo_")]
    assert len(demo_docs) >= 3  # Al menos 3 documentos demo
    
    # Verificar schedule
    tenant_id = result["tenant_id"]
    schedule_store = ScheduleStore(tmp_path, tenant_id)
    schedules = schedule_store.list_schedules()
    demo_schedules = [s for s in schedules if s.schedule_id.startswith("demo_")]
    assert len(demo_schedules) >= 1  # Al menos 1 schedule demo
