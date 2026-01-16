"""
Tests unitarios para normalize_run_id helper.

Verifica que run_id siempre aparece en top-level y artifacts cuando existe.
"""

from __future__ import annotations

import pytest
from backend.adapters.egestiona.flows import normalize_run_id


def test_normalize_run_id_with_run_id():
    """Test que normalize_run_id añade run_id a top-level y artifacts."""
    payload = {
        "status": "ok",
        "summary": {},
    }
    
    normalize_run_id(payload, "r_test_123")
    
    assert payload["run_id"] == "r_test_123"
    assert payload["artifacts"]["run_id"] == "r_test_123"


def test_normalize_run_id_with_existing_artifacts():
    """Test que normalize_run_id añade run_id sin sobrescribir artifacts existentes."""
    payload = {
        "status": "ok",
        "artifacts": {
            "storage_state_path": "runs/test/storage_state.json"
        }
    }
    
    normalize_run_id(payload, "r_test_456")
    
    assert payload["run_id"] == "r_test_456"
    assert payload["artifacts"]["run_id"] == "r_test_456"
    assert payload["artifacts"]["storage_state_path"] == "runs/test/storage_state.json"


def test_normalize_run_id_with_none():
    """Test que normalize_run_id no modifica payload si run_id es None."""
    payload = {
        "status": "error",
        "error_code": "validation_error",
    }
    
    original_payload = payload.copy()
    normalize_run_id(payload, None)
    
    assert payload == original_payload
    assert "run_id" not in payload
    assert "artifacts" not in payload


def test_normalize_run_id_in_error_response():
    """Test que normalize_run_id funciona en respuestas de error."""
    payload = {
        "status": "error",
        "error_code": "pending_list_not_loaded",
        "message": "Error message",
    }
    
    normalize_run_id(payload, "r_error_789")
    
    assert payload["run_id"] == "r_error_789"
    assert payload["artifacts"]["run_id"] == "r_error_789"
    assert payload["status"] == "error"
    assert payload["error_code"] == "pending_list_not_loaded"


def test_normalize_run_id_overwrites_existing():
    """Test que normalize_run_id sobrescribe run_id existente si es diferente."""
    payload = {
        "status": "ok",
        "run_id": "r_old_123",
        "artifacts": {
            "run_id": "r_old_123"
        }
    }
    
    normalize_run_id(payload, "r_new_456")
    
    assert payload["run_id"] == "r_new_456"
    assert payload["artifacts"]["run_id"] == "r_new_456"
