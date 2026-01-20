"""
SPRINT C2.35: Unit tests para training_state_store_v1.
"""

import pytest
from pathlib import Path
from backend.training.training_state_store_v1 import TrainingStateStoreV1


def test_training_state_default_false(tmp_path):
    """Test que verifica que el estado por defecto es False."""
    store = TrainingStateStoreV1(base_dir=str(tmp_path))
    state = store.get_state()
    
    assert state["training_completed"] is False
    assert state["completed_at"] is None
    assert state["version"] == "C2.35"


def test_training_state_mark_completed(tmp_path):
    """Test que verifica que se puede marcar como completado."""
    store = TrainingStateStoreV1(base_dir=str(tmp_path))
    
    # Inicialmente no completado
    assert not store.is_training_completed()
    
    # Marcar como completado
    success = store.mark_completed(confirm=True)
    assert success is True
    
    # Verificar que está completado
    assert store.is_training_completed()
    state = store.get_state()
    assert state["training_completed"] is True
    assert state["completed_at"] is not None


def test_training_state_mark_completed_requires_confirm(tmp_path):
    """Test que verifica que se requiere confirm=True."""
    store = TrainingStateStoreV1(base_dir=str(tmp_path))
    
    # Intentar marcar sin confirmación
    success = store.mark_completed(confirm=False)
    assert success is False
    
    # Verificar que NO está completado
    assert not store.is_training_completed()


def test_training_state_idempotent(tmp_path):
    """Test que verifica que marcar como completado es idempotente."""
    store = TrainingStateStoreV1(base_dir=str(tmp_path))
    
    # Marcar como completado primera vez
    success1 = store.mark_completed(confirm=True)
    assert success1 is True
    state1 = store.get_state()
    completed_at1 = state1["completed_at"]
    
    # Marcar como completado segunda vez (idempotente)
    success2 = store.mark_completed(confirm=True)
    assert success2 is True
    state2 = store.get_state()
    completed_at2 = state2["completed_at"]
    
    # Verificar que sigue completado y la fecha no cambió
    assert state2["training_completed"] is True
    assert completed_at2 == completed_at1


def test_training_state_file_not_exists(tmp_path):
    """Test que verifica que si el archivo no existe, asume NOT COMPLETED."""
    store = TrainingStateStoreV1(base_dir=str(tmp_path))
    
    # El archivo no existe aún
    state_file = tmp_path / "training" / "state.json"
    assert not state_file.exists()
    
    # Debe retornar NOT COMPLETED
    state = store.get_state()
    assert state["training_completed"] is False
