"""
Tests unitarios para el registry de conectores.
"""

import pytest
from backend.connectors.registry import (
    register_connector,
    get_connector,
    list_platforms,
)
from backend.connectors.base import BaseConnector
from backend.connectors.models import RunContext
from backend.connectors.egestiona.connector import EgestionaConnector


def test_egestiona_connector_registered():
    """Verifica que e-gestiona está registrado."""
    # El conector se registra automáticamente al importar
    import backend.connectors.egestiona  # noqa: F401
    
    platforms = list_platforms()
    assert "egestiona" in platforms


def test_get_egestiona_connector():
    """Verifica que se puede obtener una instancia de e-gestiona."""
    import backend.connectors.egestiona  # noqa: F401
    
    ctx = RunContext(
        run_id="test-123",
        platform_id="egestiona",
    )
    
    connector = get_connector("egestiona", ctx)
    assert connector is not None
    assert isinstance(connector, EgestionaConnector)
    assert connector.platform_id == "egestiona"


def test_get_unknown_connector():
    """Verifica que get_connector devuelve None para plataformas desconocidas."""
    ctx = RunContext(
        run_id="test-123",
        platform_id="unknown",
    )
    
    connector = get_connector("unknown_platform", ctx)
    assert connector is None


def test_pending_requirement_model():
    """Verifica que PendingRequirement valida y serializa correctamente."""
    from backend.connectors.models import PendingRequirement
    
    req = PendingRequirement(
        id="test-id-123",
        subject_type="empresa",
        subject_id="B12345678",
        doc_type_hint="TC2",
        period="2025-01",
        due_date="2025-02-15",
        status="missing",
    )
    
    assert req.id == "test-id-123"
    assert req.subject_type == "empresa"
    assert req.doc_type_hint == "TC2"
    assert req.period == "2025-01"
    
    # Verificar que create_id genera IDs deterministas
    id1 = PendingRequirement.create_id("egestiona", "empresa", "TC2", "B12345678", "2025-01")
    id2 = PendingRequirement.create_id("egestiona", "empresa", "TC2", "B12345678", "2025-01")
    assert id1 == id2  # Determinista
    
    id3 = PendingRequirement.create_id("egestiona", "trabajador", "TC2", "B12345678", "2025-01")
    assert id1 != id3  # Diferente para diferente subject_type


def test_upload_result_model():
    """Verifica que UploadResult valida correctamente."""
    from backend.connectors.models import UploadResult
    
    result = UploadResult(
        success=True,
        requirement_id="req-123",
        uploaded_doc_id="doc-456",
        portal_reference="portal-ref-789",
    )
    
    assert result.success is True
    assert result.uploaded_doc_id == "doc-456"
    assert result.error is None


def test_run_context_model():
    """Verifica que RunContext valida correctamente."""
    from backend.connectors.models import RunContext
    
    ctx = RunContext(
        run_id="test-run-123",
        base_url="https://example.com",
        platform_id="egestiona",
        tenant_id="clienteX",
        headless=True,
    )
    
    assert ctx.run_id == "test-run-123"
    assert ctx.platform_id == "egestiona"
    assert ctx.tenant_id == "clienteX"
    assert ctx.headless is True
    
    # Verificar que create_run_id genera IDs únicos
    id1 = RunContext.create_run_id()
    id2 = RunContext.create_run_id()
    assert id1 != id2  # Deben ser diferentes
    assert id1.startswith("CONN-")
    assert id2.startswith("CONN-")
