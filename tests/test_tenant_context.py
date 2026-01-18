"""
SPRINT C2.22A: Tests para tenant context.
"""
import pytest
from fastapi import Request
from unittest.mock import Mock

from backend.shared.tenant_context import (
    TenantContext,
    get_tenant_from_request,
    sanitize_tenant_id,
)


def test_sanitize_tenant_id():
    """Test: sanitización de tenant_id."""
    # Casos normales
    assert sanitize_tenant_id("tenantA") == "tenantA"
    assert sanitize_tenant_id("tenant-A") == "tenant_A"  # Guiones se convierten en guiones bajos
    assert sanitize_tenant_id("tenant_A") == "tenant_A"
    assert sanitize_tenant_id("tenant123") == "tenant123"
    
    # Caracteres especiales
    assert sanitize_tenant_id("tenant@A") == "tenant_A"
    assert sanitize_tenant_id("tenant A") == "tenant_A"
    assert sanitize_tenant_id("tenant.A") == "tenant_A"
    assert sanitize_tenant_id("tenant/A") == "tenant_A"
    
    # Múltiples caracteres especiales
    assert sanitize_tenant_id("tenant@#$A") == "tenant_A"
    assert sanitize_tenant_id("tenant---A") == "tenant_A"
    assert sanitize_tenant_id("tenant___A") == "tenant_A"
    
    # Bordes
    assert sanitize_tenant_id("-tenant-") == "tenant"
    assert sanitize_tenant_id("_tenant_") == "tenant"
    
    # Vacío
    assert sanitize_tenant_id("") == "default"
    assert sanitize_tenant_id("---") == "default"


def test_get_tenant_from_request_header():
    """Test: extracción desde header X-Tenant-ID."""
    request = Mock(spec=Request)
    request.headers = {"X-Tenant-ID": "tenantA"}
    request.query_params = {}
    
    ctx = get_tenant_from_request(request)
    
    assert ctx.tenant_id == "tenantA"
    assert ctx.source == "header"


def test_get_tenant_from_request_query():
    """Test: extracción desde query param tenant_id."""
    request = Mock(spec=Request)
    request.headers = {}
    request.query_params = {"tenant_id": "tenantB"}
    
    ctx = get_tenant_from_request(request)
    
    assert ctx.tenant_id == "tenantB"
    assert ctx.source == "query"


def test_get_tenant_from_request_default():
    """Test: default cuando no hay header ni query."""
    request = Mock(spec=Request)
    request.headers = {}
    request.query_params = {}
    
    ctx = get_tenant_from_request(request)
    
    assert ctx.tenant_id == "default"
    assert ctx.source == "default"


def test_get_tenant_from_request_priority():
    """Test: header tiene prioridad sobre query."""
    request = Mock(spec=Request)
    request.headers = {"X-Tenant-ID": "tenantHeader"}
    request.query_params = {"tenant_id": "tenantQuery"}
    
    ctx = get_tenant_from_request(request)
    
    assert ctx.tenant_id == "tenantHeader"
    assert ctx.source == "header"


def test_get_tenant_from_request_none():
    """Test: request None retorna default."""
    ctx = get_tenant_from_request(None)
    
    assert ctx.tenant_id == "default"
    assert ctx.source == "default"


def test_get_tenant_from_request_sanitization():
    """Test: tenant_id se sanitiza automáticamente."""
    request = Mock(spec=Request)
    request.headers = {"X-Tenant-ID": "tenant@A"}
    request.query_params = {}
    
    ctx = get_tenant_from_request(request)
    
    assert ctx.tenant_id == "tenant_A"
    assert ctx.source == "header"
