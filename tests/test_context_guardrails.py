"""
SPRINT C2.27: Tests para guardrails de contexto.
"""
import pytest
import os
from unittest.mock import Mock, patch
from fastapi import Request, HTTPException

from backend.shared.context_guardrails import (
    is_write_request,
    has_human_coordination_context,
    has_legacy_tenant_header,
    is_dev_or_test_environment,
    validate_write_request_context,
)


def test_is_write_request():
    """Test: detecta operaciones WRITE."""
    # POST es WRITE
    request = Mock(spec=Request)
    request.method = "POST"
    assert is_write_request(request) is True
    
    # PUT es WRITE
    request.method = "PUT"
    assert is_write_request(request) is True
    
    # DELETE es WRITE
    request.method = "DELETE"
    assert is_write_request(request) is True
    
    # GET no es WRITE
    request.method = "GET"
    assert is_write_request(request) is False
    
    # HEAD no es WRITE
    request.method = "HEAD"
    assert is_write_request(request) is False


def test_has_human_coordination_context():
    """Test: verifica contexto humano completo."""
    request = Mock(spec=Request)
    
    # Sin headers
    request.headers = {}
    assert has_human_coordination_context(request) is False
    
    # Con los 3 headers
    request.headers = {
        "X-Coordination-Own-Company": "F63161988",
        "X-Coordination-Platform": "egestiona",
        "X-Coordination-Coordinated-Company": "aiguesdemanresa"
    }
    assert has_human_coordination_context(request) is True
    
    # Con solo 2 headers
    request.headers = {
        "X-Coordination-Own-Company": "F63161988",
        "X-Coordination-Platform": "egestiona"
    }
    assert has_human_coordination_context(request) is False


def test_has_legacy_tenant_header():
    """Test: verifica header legacy."""
    request = Mock(spec=Request)
    
    # Sin header
    request.headers = {}
    assert has_legacy_tenant_header(request) is False
    
    # Con header legacy
    request.headers = {"X-Tenant-ID": "tenantA"}
    assert has_legacy_tenant_header(request) is True


def test_is_dev_or_test_environment():
    """Test: verifica entorno dev/test."""
    # Sin ENVIRONMENT
    with patch.dict(os.environ, {}, clear=True):
        assert is_dev_or_test_environment() is False
    
    # Con ENVIRONMENT=dev
    with patch.dict(os.environ, {"ENVIRONMENT": "dev"}, clear=False):
        assert is_dev_or_test_environment() is True
    
    # Con ENVIRONMENT=test
    with patch.dict(os.environ, {"ENVIRONMENT": "test"}, clear=False):
        assert is_dev_or_test_environment() is True
    
    # Con ENVIRONMENT=prod
    with patch.dict(os.environ, {"ENVIRONMENT": "prod"}, clear=False):
        assert is_dev_or_test_environment() is False


def test_validate_write_request_context_with_human_context():
    """Test: WRITE con contexto humano -> OK (no bloquea)."""
    request = Mock(spec=Request)
    request.method = "POST"
    request.headers = {
        "X-Coordination-Own-Company": "F63161988",
        "X-Coordination-Platform": "egestiona",
        "X-Coordination-Coordinated-Company": "aiguesdemanresa"
    }
    
    # No debe lanzar excepción
    validate_write_request_context(request)


def test_validate_write_request_context_without_context():
    """Test: WRITE sin contexto -> 400."""
    request = Mock(spec=Request)
    request.method = "POST"
    request.headers = {}
    
    with pytest.raises(HTTPException) as exc_info:
        validate_write_request_context(request)
    
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["error"] == "missing_coordination_context"
    assert "Selecciona Empresa propia" in exc_info.value.detail["message"]


def test_validate_write_request_context_with_legacy_in_dev():
    """Test: WRITE con legacy + dev -> OK."""
    request = Mock(spec=Request)
    request.method = "POST"
    request.headers = {"X-Tenant-ID": "tenantA"}
    
    with patch.dict(os.environ, {"ENVIRONMENT": "dev"}, clear=False):
        # No debe lanzar excepción
        validate_write_request_context(request)


def test_validate_write_request_context_with_legacy_in_test():
    """Test: WRITE con legacy + test -> OK."""
    request = Mock(spec=Request)
    request.method = "POST"
    request.headers = {"X-Tenant-ID": "tenantA"}
    
    with patch.dict(os.environ, {"ENVIRONMENT": "test"}, clear=False):
        # No debe lanzar excepción
        validate_write_request_context(request)


def test_validate_write_request_context_with_legacy_in_prod():
    """Test: WRITE con legacy + prod -> 400."""
    request = Mock(spec=Request)
    request.method = "POST"
    request.headers = {"X-Tenant-ID": "tenantA"}
    
    with patch.dict(os.environ, {"ENVIRONMENT": "prod"}, clear=False):
        with pytest.raises(HTTPException) as exc_info:
            validate_write_request_context(request)
        
        assert exc_info.value.status_code == 400


def test_validate_write_request_context_read_operation():
    """Test: READ sin contexto -> OK (se mantiene comportamiento)."""
    request = Mock(spec=Request)
    request.method = "GET"
    request.headers = {}
    
    # No debe lanzar excepción (READ no requiere contexto)
    validate_write_request_context(request)
