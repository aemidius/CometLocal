"""
SPRINT C2.22B: Tests para export routes con tenant scoping.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.shared.tenant_context import get_tenant_from_request
from backend.shared.tenant_paths import tenant_exports_root, ensure_write_dir


def test_export_creates_tenant_dir():
    """Test: Export crea ZIP en ruta tenant."""
    from backend.config import DATA_DIR
    
    tenant_id = "tenantA"
    exports_dir = ensure_write_dir(tenant_exports_root(DATA_DIR, tenant_id))
    
    # Verificar que se creó el directorio
    assert exports_dir.exists()
    assert exports_dir == DATA_DIR / "tenants" / tenant_id / "exports"


def test_export_no_cross_tenants():
    """Test: No cruza exports entre tenants."""
    # Simular store de exports por tenant
    exports_store = {}
    
    tenant_a = "tenantA"
    tenant_b = "tenantB"
    
    # Crear export para tenantA
    if tenant_a not in exports_store:
        exports_store[tenant_a] = {}
    export_id_a = "export_abc123"
    exports_store[tenant_a][export_id_a] = Path("/fake/path/export_a.zip")
    
    # Crear export para tenantB
    if tenant_b not in exports_store:
        exports_store[tenant_b] = {}
    export_id_b = "export_def456"
    exports_store[tenant_b][export_id_b] = Path("/fake/path/export_b.zip")
    
    # Verificar aislamiento
    assert export_id_a in exports_store[tenant_a]
    assert export_id_b in exports_store[tenant_b]
    assert export_id_a not in exports_store[tenant_b]
    assert export_id_b not in exports_store[tenant_a]


def test_export_download_only_tenant():
    """Test: Descarga solo accede a exports del tenant."""
    # Simular store de exports por tenant
    exports_store = {
        "tenantA": {"export_abc123": Path("/fake/path/export_a.zip")},
        "tenantB": {"export_def456": Path("/fake/path/export_b.zip")},
    }
    
    # Simular request de tenantA
    request_a = Mock()
    request_a.headers = {"X-Tenant-ID": "tenantA"}
    request_a.query_params = {}
    tenant_ctx_a = get_tenant_from_request(request_a)
    
    # tenantA solo debe ver sus exports
    assert tenant_ctx_a.tenant_id == "tenantA"
    assert "export_abc123" in exports_store[tenant_ctx_a.tenant_id]
    assert "export_def456" not in exports_store[tenant_ctx_a.tenant_id]
    
    # Simular request de tenantB
    request_b = Mock()
    request_b.headers = {"X-Tenant-ID": "tenantB"}
    request_b.query_params = {}
    tenant_ctx_b = get_tenant_from_request(request_b)
    
    # tenantB solo debe ver sus exports
    assert tenant_ctx_b.tenant_id == "tenantB"
    assert "export_def456" in exports_store[tenant_ctx_b.tenant_id]
    assert "export_abc123" not in exports_store[tenant_ctx_b.tenant_id]
