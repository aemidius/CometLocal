"""
SPRINT C2.36.1: Tests unitarios para el script de limpieza de datos demo.
"""

import json
import tempfile
from pathlib import Path
import pytest
import sys

# Añadir scripts al path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from cleanup_demo_data import (
    is_demo_type,
    is_demo_doc,
    identify_demo_types,
    identify_demo_docs,
    remove_demo_types,
    load_json_file,
    save_json_file,
    DEMO_TYPE_PATTERNS,
    DEMO_NAME_PATTERNS,
)


def test_is_demo_type():
    """Test: is_demo_type identifica correctamente tipos demo."""
    # Casos positivos
    assert is_demo_type("TEST_TYPE", "Test Type", set()) is True
    assert is_demo_type("T999_SOMETHING", "Otro documento", set()) is True
    assert is_demo_type("E2E_TYPE_123", "E2E Test", set()) is True
    assert is_demo_type("DEMO_TYPE", "Demo Type", set()) is True
    assert is_demo_type("REAL_TYPE", "Test Type", set()) is True  # Nombre contiene "Test Type"
    
    # Casos negativos
    assert is_demo_type("T104_AUTONOMOS_RECEIPT", "Recibo autónomos", set()) is False
    assert is_demo_type("T202_CERTIFICADO", "Certificado", set()) is False
    
    # Allowlist
    assert is_demo_type("TEST_TYPE", "Test Type", {"TEST_TYPE"}) is False


def test_is_demo_doc():
    """Test: is_demo_doc identifica correctamente documentos demo."""
    keep_list = set()
    
    # Casos positivos
    assert is_demo_doc("TEST_DOC_1", "test.pdf", "TEST_TYPE", "TEST_COMPANY", "TEST_WORKER", keep_list) is True
    assert is_demo_doc("E2E_DOC_123", "e2e_test.pdf", "E2E_TYPE", "E2E_COMPANY", None, keep_list) is True
    assert is_demo_doc("REAL_DOC", "real_doc_001.pdf", "T104", "COMPANY", "WORKER", keep_list) is True  # file_name demo
    assert is_demo_doc("REAL_DOC", "test.pdf", "T104", "COMPANY", "worker_real_001", keep_list) is True  # person_key demo
    
    # Casos negativos
    assert is_demo_doc("DOC_123", "documento.pdf", "T104", "COMPANY", "WORKER", keep_list) is False
    
    # Allowlist
    assert is_demo_doc("TEST_DOC_1", "test.pdf", "TEST_TYPE", "TEST_COMPANY", None, {"TEST_DOC_1"}) is False


def test_identify_demo_types():
    """Test: identify_demo_types identifica tipos demo correctamente."""
    types_data = {
        "schema_version": "v1",
        "types": [
            {
                "type_id": "TEST_TYPE",
                "name": "Test Type",
                "description": "",
                "scope": "company",
                "active": True,
            },
            {
                "type_id": "T104_AUTONOMOS_RECEIPT",
                "name": "Recibo autónomos",
                "description": "Recibo de autónomos mensual",
                "scope": "worker",
                "active": True,
            },
            {
                "type_id": "E2E_TYPE_123",
                "name": "E2E Test Type",
                "description": "",
                "scope": "company",
                "active": True,
            },
        ]
    }
    
    candidates = identify_demo_types(types_data, set())
    
    # Debe identificar TEST_TYPE y E2E_TYPE_123 como demo
    candidate_ids = {c["type_id"] for c in candidates}
    assert "TEST_TYPE" in candidate_ids
    assert "E2E_TYPE_123" in candidate_ids
    assert "T104_AUTONOMOS_RECEIPT" not in candidate_ids


def test_remove_demo_types():
    """Test: remove_demo_types elimina tipos demo correctamente."""
    types_data = {
        "schema_version": "v1",
        "types": [
            {"type_id": "TEST_TYPE", "name": "Test Type"},
            {"type_id": "T104_AUTONOMOS_RECEIPT", "name": "Recibo autónomos"},
            {"type_id": "E2E_TYPE_123", "name": "E2E Test"},
        ]
    }
    
    candidates = [
        {"type_id": "TEST_TYPE", "name": "Test Type", "action": "remove"},
        {"type_id": "E2E_TYPE_123", "name": "E2E Test", "action": "remove"},
    ]
    
    result = remove_demo_types(types_data, candidates)
    
    remaining_ids = {t["type_id"] for t in result["types"]}
    assert "TEST_TYPE" not in remaining_ids
    assert "E2E_TYPE_123" not in remaining_ids
    assert "T104_AUTONOMOS_RECEIPT" in remaining_ids


def test_cleanup_respects_allowlist():
    """Test: la limpieza respeta la allowlist."""
    types_data = {
        "schema_version": "v1",
        "types": [
            {"type_id": "TEST_TYPE", "name": "Test Type"},
            {"type_id": "TEST_TYPE_KEEP", "name": "Test Type Keep"},
        ]
    }
    
    # Con allowlist, TEST_TYPE_KEEP no debe ser candidato
    candidates = identify_demo_types(types_data, {"TEST_TYPE_KEEP"})
    candidate_ids = {c["type_id"] for c in candidates}
    assert "TEST_TYPE" in candidate_ids
    assert "TEST_TYPE_KEEP" not in candidate_ids


def test_dry_run_no_modification(tmp_path):
    """Test: dry-run no modifica archivos."""
    types_file = tmp_path / "types.json"
    original_data = {
        "schema_version": "v1",
        "types": [
            {"type_id": "TEST_TYPE", "name": "Test Type"},
            {"type_id": "T104_AUTONOMOS_RECEIPT", "name": "Recibo autónomos"},
        ]
    }
    
    save_json_file(types_file, original_data)
    
    # Simular dry-run: identificar pero no eliminar
    candidates = identify_demo_types(original_data, set())
    remove_candidates = [c for c in candidates if c.get("action") == "remove"]
    
    # Verificar que el archivo original no cambió
    loaded = load_json_file(types_file)
    assert len(loaded["types"]) == 2
    
    # Si aplicáramos, debería quedar 1
    if remove_candidates:
        cleaned = remove_demo_types(original_data, remove_candidates)
        assert len(cleaned["types"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
