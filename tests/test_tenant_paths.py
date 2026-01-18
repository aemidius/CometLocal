"""
SPRINT C2.22A: Tests para tenant paths.
"""
import pytest
import tempfile
import shutil
from pathlib import Path

from backend.shared.tenant_paths import (
    tenants_root,
    tenant_root,
    tenant_runs_root,
    tenant_learning_root,
    tenant_presets_root,
    tenant_exports_root,
    tenant_repository_root,
    resolve_read_path,
    ensure_write_dir,
    get_runs_root,
)


@pytest.fixture
def temp_base_dir():
    """Fixture con directorio temporal."""
    temp_dir = tempfile.mkdtemp()
    base_dir = Path(temp_dir)
    yield base_dir
    shutil.rmtree(temp_dir)


def test_tenants_root(temp_base_dir):
    """Test: tenants_root retorna data/tenants/."""
    result = tenants_root(temp_base_dir)
    assert result == temp_base_dir / "tenants"


def test_tenant_root(temp_base_dir):
    """Test: tenant_root retorna data/tenants/<tenant_id>/."""
    result = tenant_root(temp_base_dir, "tenantA")
    assert result == temp_base_dir / "tenants" / "tenantA"


def test_tenant_runs_root(temp_base_dir):
    """Test: tenant_runs_root retorna data/tenants/<tenant_id>/runs/."""
    result = tenant_runs_root(temp_base_dir, "tenantA")
    assert result == temp_base_dir / "tenants" / "tenantA" / "runs"


def test_tenant_learning_root(temp_base_dir):
    """Test: tenant_learning_root retorna data/tenants/<tenant_id>/learning/."""
    result = tenant_learning_root(temp_base_dir, "tenantA")
    assert result == temp_base_dir / "tenants" / "tenantA" / "learning"


def test_tenant_presets_root(temp_base_dir):
    """Test: tenant_presets_root retorna data/tenants/<tenant_id>/presets/."""
    result = tenant_presets_root(temp_base_dir, "tenantA")
    assert result == temp_base_dir / "tenants" / "tenantA" / "presets"


def test_tenant_exports_root(temp_base_dir):
    """Test: tenant_exports_root retorna data/tenants/<tenant_id>/exports/."""
    result = tenant_exports_root(temp_base_dir, "tenantA")
    assert result == temp_base_dir / "tenants" / "tenantA" / "exports"


def test_tenant_repository_root(temp_base_dir):
    """Test: tenant_repository_root retorna data/tenants/<tenant_id>/repository/."""
    result = tenant_repository_root(temp_base_dir, "tenantA")
    assert result == temp_base_dir / "tenants" / "tenantA" / "repository"


def test_resolve_read_path_tenant_exists(temp_base_dir):
    """Test: resolve_read_path prefiere tenant si existe."""
    tenant_path = temp_base_dir / "tenants" / "tenantA" / "runs" / "plan123.json"
    legacy_path = temp_base_dir / "runs" / "plan123.json"
    
    # Crear tenant path
    tenant_path.parent.mkdir(parents=True, exist_ok=True)
    tenant_path.write_text("tenant content")
    
    result = resolve_read_path(tenant_path, legacy_path)
    
    assert result == tenant_path
    assert result.exists()


def test_resolve_read_path_fallback_legacy(temp_base_dir):
    """Test: resolve_read_path fallback a legacy si tenant no existe."""
    tenant_path = temp_base_dir / "tenants" / "tenantA" / "runs" / "plan123.json"
    legacy_path = temp_base_dir / "runs" / "plan123.json"
    
    # Crear legacy path
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text("legacy content")
    
    result = resolve_read_path(tenant_path, legacy_path)
    
    assert result == legacy_path
    assert result.exists()


def test_resolve_read_path_directory_exists(temp_base_dir):
    """Test: resolve_read_path usa tenant si el directorio padre existe."""
    tenant_dir = temp_base_dir / "tenants" / "tenantA" / "runs"
    tenant_path = tenant_dir / "plan123.json"
    legacy_path = temp_base_dir / "runs" / "plan123.json"
    
    # Crear solo el directorio tenant (sin archivo)
    tenant_dir.mkdir(parents=True, exist_ok=True)
    
    result = resolve_read_path(tenant_path, legacy_path)
    
    # Debe preferir tenant aunque el archivo no exista
    assert result == tenant_path


def test_ensure_write_dir(temp_base_dir):
    """Test: ensure_write_dir crea directorio."""
    target_dir = temp_base_dir / "tenants" / "tenantA" / "runs"
    
    assert not target_dir.exists()
    
    result = ensure_write_dir(target_dir)
    
    assert result == target_dir
    assert target_dir.exists()
    assert target_dir.is_dir()


def test_get_runs_root_write(temp_base_dir):
    """Test: get_runs_root mode='write' crea tenant path."""
    result = get_runs_root(temp_base_dir, "tenantA", mode="write")
    
    assert result == temp_base_dir / "tenants" / "tenantA" / "runs"
    assert result.exists()
    assert result.is_dir()


def test_get_runs_root_read_tenant_exists(temp_base_dir):
    """Test: get_runs_root mode='read' prefiere tenant si existe."""
    tenant_runs = temp_base_dir / "tenants" / "tenantA" / "runs"
    legacy_runs = temp_base_dir / "runs"
    
    # Crear tenant runs
    tenant_runs.mkdir(parents=True, exist_ok=True)
    
    result = get_runs_root(temp_base_dir, "tenantA", mode="read")
    
    assert result == tenant_runs
    assert result.exists()


def test_get_runs_root_read_fallback_legacy(temp_base_dir):
    """Test: get_runs_root mode='read' fallback a legacy si tenant no existe."""
    tenant_runs = temp_base_dir / "tenants" / "tenantA" / "runs"
    legacy_runs = temp_base_dir / "runs"
    
    # Crear legacy runs
    legacy_runs.mkdir(parents=True, exist_ok=True)
    
    result = get_runs_root(temp_base_dir, "tenantA", mode="read")
    
    assert result == legacy_runs
    assert result.exists()


def test_get_runs_root_read_both_exist_prefers_tenant(temp_base_dir):
    """Test: get_runs_root mode='read' prefiere tenant aunque legacy exista."""
    tenant_runs = temp_base_dir / "tenants" / "tenantA" / "runs"
    legacy_runs = temp_base_dir / "runs"
    
    # Crear ambos
    tenant_runs.mkdir(parents=True, exist_ok=True)
    legacy_runs.mkdir(parents=True, exist_ok=True)
    
    result = get_runs_root(temp_base_dir, "tenantA", mode="read")
    
    assert result == tenant_runs
