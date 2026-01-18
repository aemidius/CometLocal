"""
SPRINT C2.29: Tests para RunLock.
"""

import os
import time
from pathlib import Path
from datetime import datetime, timedelta

import pytest

from backend.shared.run_lock import RunLock, STALE_THRESHOLD_HOURS
from backend.config import DATA_DIR


@pytest.fixture
def test_tenant_id():
    """Tenant ID para tests."""
    return "test_tenant_lock"


@pytest.fixture
def lock(test_tenant_id, tmp_path):
    """RunLock para tests."""
    return RunLock(tmp_path, test_tenant_id)


def test_lock_acquire_success(lock):
    """Test: adquirir lock cuando no existe."""
    run_id = "test_run_1"
    acquired, error = lock.acquire(run_id)
    
    assert acquired is True
    assert error is None
    assert lock.lock_file.exists()


def test_lock_acquire_blocked(lock):
    """Test: no adquirir lock cuando ya existe uno activo."""
    run_id1 = "test_run_1"
    run_id2 = "test_run_2"
    
    # Adquirir primer lock
    acquired1, _ = lock.acquire(run_id1)
    assert acquired1 is True
    
    # Intentar adquirir segundo lock
    acquired2, error = lock.acquire(run_id2)
    
    assert acquired2 is False
    assert error is not None
    assert "en ejecución" in error.lower()


def test_lock_release(lock):
    """Test: liberar lock."""
    run_id = "test_run_1"
    
    # Adquirir y liberar
    lock.acquire(run_id)
    assert lock.lock_file.exists()
    
    lock.release(run_id)
    assert not lock.lock_file.exists()


def test_lock_stale_override(lock, monkeypatch):
    """Test: permitir override de lock stale."""
    run_id1 = "test_run_1"
    run_id2 = "test_run_2"
    
    # Adquirir primer lock
    lock.acquire(run_id1)
    
    # Simular lock stale (más de 2 horas)
    lock_data = {
        "run_id": run_id1,
        "locked_at": (datetime.now() - timedelta(hours=STALE_THRESHOLD_HOURS + 1)).isoformat(),
        "tenant_id": lock.tenant_id,
    }
    import json
    with open(lock.lock_file, "w", encoding="utf-8") as f:
        json.dump(lock_data, f)
    
    # Intentar adquirir segundo lock (debe permitir override)
    acquired, error = lock.acquire(run_id2)
    
    assert acquired is True
    assert error is None


def test_lock_release_wrong_run_id(lock):
    """Test: no liberar lock si el run_id no coincide."""
    run_id1 = "test_run_1"
    run_id2 = "test_run_2"
    
    lock.acquire(run_id1)
    assert lock.lock_file.exists()
    
    # Intentar liberar con run_id diferente
    lock.release(run_id2)
    
    # Lock debe seguir existiendo
    assert lock.lock_file.exists()
