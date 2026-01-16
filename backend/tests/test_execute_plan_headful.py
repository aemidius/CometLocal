"""
Tests para execute_plan_headful endpoint.
"""

import pytest
from pathlib import Path
from backend.adapters.egestiona.execute_plan_headful_gate import _validate_real_upload_gate
from backend.adapters.egestiona.execute_plan_gate import ExecutePlanRequest
from backend.config import DATA_DIR
from fastapi import Request
from unittest.mock import Mock


def test_validate_gate_missing_header():
    """Test que sin header X-USE-REAL-UPLOADER devuelve error."""
    request = ExecutePlanRequest(
        plan_id="test",
        confirm_token="token",
        allowlist_type_ids=["T001"],
        max_uploads=1,
        min_confidence=0.80,
    )
    
    mock_request = Mock(spec=Request)
    mock_request.headers = {}
    
    result = _validate_real_upload_gate(request, mock_request)
    
    assert result is not None
    assert result["status"] == "error"
    assert result["error_code"] == "real_uploader_not_requested"


def test_validate_gate_max_uploads_violation():
    """Test que max_uploads != 1 devuelve error."""
    request = ExecutePlanRequest(
        plan_id="test",
        confirm_token="token",
        allowlist_type_ids=["T001"],
        max_uploads=2,  # Violación
        min_confidence=0.80,
    )
    
    mock_request = Mock(spec=Request)
    mock_request.headers = {"X-USE-REAL-UPLOADER": "1"}
    
    import os
    original_env = os.getenv("ENVIRONMENT")
    try:
        os.environ["ENVIRONMENT"] = "dev"
        result = _validate_real_upload_gate(request, mock_request)
        
        assert result is not None
        assert result["status"] == "error"
        assert result["error_code"] == "REAL_UPLOAD_GUARDRAIL_VIOLATION"
        assert "max_uploads debe ser 1" in result["message"]
    finally:
        if original_env:
            os.environ["ENVIRONMENT"] = original_env
        elif "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]


def test_validate_gate_allowlist_violation():
    """Test que len(allowlist_type_ids) != 1 devuelve error."""
    request = ExecutePlanRequest(
        plan_id="test",
        confirm_token="token",
        allowlist_type_ids=["T001", "T002"],  # Violación
        max_uploads=1,
        min_confidence=0.80,
    )
    
    mock_request = Mock(spec=Request)
    mock_request.headers = {"X-USE-REAL-UPLOADER": "1"}
    
    import os
    original_env = os.getenv("ENVIRONMENT")
    try:
        os.environ["ENVIRONMENT"] = "dev"
        result = _validate_real_upload_gate(request, mock_request)
        
        assert result is not None
        assert result["status"] == "error"
        assert result["error_code"] == "REAL_UPLOAD_GUARDRAIL_VIOLATION"
        assert "allowlist_type_ids debe tener exactamente 1 tipo" in result["message"]
    finally:
        if original_env:
            os.environ["ENVIRONMENT"] = original_env
        elif "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]


def test_validate_gate_missing_storage_state_error():
    """Test que si falta storage_state devuelve error específico."""
    # Este test valida la lógica del endpoint, no la función de gate
    # Se puede hacer un test de integración más completo
    pass
