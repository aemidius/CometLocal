"""
SPRINT C2.26: Tests para resolución de tenant desde headers humanos de coordinación.
"""
import pytest
from unittest.mock import Mock
from fastapi import Request

from backend.shared.tenant_context import (
    get_tenant_from_request,
    compute_tenant_from_coordination_context,
    TenantContext
)


def test_compute_tenant_from_coordination_context_all_present():
    """Test: cálculo de tenant desde contexto humano completo."""
    tenant_id = compute_tenant_from_coordination_context(
        own_company_key="F63161988",
        platform_key="egestiona",
        coordinated_company_key="aiguesdemanresa"
    )
    
    assert tenant_id == "F63161988__egestiona__aiguesdemanresa"


def test_compute_tenant_from_coordination_context_missing_own():
    """Test: falta empresa propia => default."""
    tenant_id = compute_tenant_from_coordination_context(
        own_company_key=None,
        platform_key="egestiona",
        coordinated_company_key="aiguesdemanresa"
    )
    
    assert tenant_id == "default"


def test_compute_tenant_from_coordination_context_missing_platform():
    """Test: falta plataforma => default."""
    tenant_id = compute_tenant_from_coordination_context(
        own_company_key="F63161988",
        platform_key=None,
        coordinated_company_key="aiguesdemanresa"
    )
    
    assert tenant_id == "default"


def test_compute_tenant_from_coordination_context_missing_coordinated():
    """Test: falta empresa coordinada => default."""
    tenant_id = compute_tenant_from_coordination_context(
        own_company_key="F63161988",
        platform_key="egestiona",
        coordinated_company_key=None
    )
    
    assert tenant_id == "default"


def test_get_tenant_from_request_human_headers():
    """Test: extracción desde headers humanos de coordinación."""
    request = Mock(spec=Request)
    request.headers = {
        "X-Coordination-Own-Company": "F63161988",
        "X-Coordination-Platform": "egestiona",
        "X-Coordination-Coordinated-Company": "aiguesdemanresa"
    }
    request.query_params = {}
    
    ctx = get_tenant_from_request(request)
    
    assert ctx.tenant_id == "F63161988__egestiona__aiguesdemanresa"
    assert ctx.source == "header"


def test_get_tenant_from_request_human_headers_partial():
    """Test: headers humanos parciales => fallback a legacy."""
    request = Mock(spec=Request)
    request.headers = {
        "X-Coordination-Own-Company": "F63161988",
        "X-Coordination-Platform": "egestiona",
        # Falta X-Coordination-Coordinated-Company
        "X-Tenant-ID": "legacy_tenant"
    }
    request.query_params = {}
    
    ctx = get_tenant_from_request(request)
    
    # Debe usar fallback legacy (X-Tenant-ID)
    assert ctx.tenant_id == "legacy_tenant"
    assert ctx.source == "header"


def test_get_tenant_from_request_human_headers_priority():
    """Test: headers humanos tienen prioridad sobre X-Tenant-ID."""
    request = Mock(spec=Request)
    request.headers = {
        "X-Coordination-Own-Company": "F63161988",
        "X-Coordination-Platform": "egestiona",
        "X-Coordination-Coordinated-Company": "aiguesdemanresa",
        "X-Tenant-ID": "should_be_ignored"
    }
    request.query_params = {}
    
    ctx = get_tenant_from_request(request)
    
    # Debe usar headers humanos, no X-Tenant-ID
    assert ctx.tenant_id == "F63161988__egestiona__aiguesdemanresa"
    assert ctx.source == "header"
