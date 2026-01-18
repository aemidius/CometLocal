"""
SPRINT C2.20B: Tests para Run Metrics.
"""
import pytest
from pathlib import Path
import tempfile
import shutil

from backend.shared.run_metrics import (
    RunMetricsV1,
    initialize_metrics,
    load_metrics,
    save_metrics,
    update_metrics_from_decisions,
    record_decision_pack_created,
    record_execution_started,
    record_execution_finished,
    record_learning_hint_applied,
    record_preset_applied,
    record_manual_decision,
)


@pytest.fixture
def temp_dir(tmp_path):
    """Fixture con directorio temporal."""
    return tmp_path


def test_initialize_metrics(temp_dir):
    """Test: Inicializar métricas crea archivo."""
    plan_id = "plan_test123"
    total_items = 10
    
    metrics = initialize_metrics(plan_id, total_items, base_dir=temp_dir)
    
    assert metrics.plan_id == plan_id
    assert metrics.total_items == total_items
    assert metrics.timestamps["plan_created_at"] is not None
    
    # Verificar que se guardó
    loaded = load_metrics(plan_id, base_dir=temp_dir)
    assert loaded is not None
    assert loaded.plan_id == plan_id
    assert loaded.total_items == total_items


def test_update_metrics_from_decisions(temp_dir):
    """Test: Actualizar métricas desde decisiones."""
    plan_id = "plan_test123"
    
    # Inicializar
    initialize_metrics(plan_id, 5, base_dir=temp_dir)
    
    # Actualizar con decisiones
    decisions = [
        {"decision": "AUTO_UPLOAD"},
        {"decision": "AUTO_UPLOAD"},
        {"decision": "REVIEW_REQUIRED"},
        {"decision": "NO_MATCH"},
        {"decision": "SKIP"},
    ]
    
    metrics = update_metrics_from_decisions(plan_id, decisions, source="auto_matching", base_dir=temp_dir)
    
    assert metrics.decisions_count["AUTO_UPLOAD"] == 2
    assert metrics.decisions_count["REVIEW_REQUIRED"] == 1
    assert metrics.decisions_count["NO_MATCH"] == 1
    assert metrics.decisions_count["SKIP"] == 1
    assert metrics.source_breakdown["auto_matching"] == 5


def test_record_decision_pack_created(temp_dir):
    """Test: Registrar creación de decision pack."""
    plan_id = "plan_test123"
    initialize_metrics(plan_id, 5, base_dir=temp_dir)
    
    record_decision_pack_created(plan_id, base_dir=temp_dir)
    
    metrics = load_metrics(plan_id, base_dir=temp_dir)
    assert metrics.timestamps["decision_pack_created_at"] is not None


def test_record_execution_lifecycle(temp_dir):
    """Test: Registrar ciclo completo de ejecución."""
    plan_id = "plan_test123"
    run_id = "run_test456"
    
    initialize_metrics(plan_id, 5, base_dir=temp_dir)
    
    record_execution_started(plan_id, run_id, base_dir=temp_dir)
    metrics = load_metrics(plan_id, base_dir=temp_dir)
    assert metrics.run_id == run_id
    assert metrics.timestamps["execution_started_at"] is not None
    
    record_execution_finished(plan_id, base_dir=temp_dir)
    metrics = load_metrics(plan_id, base_dir=temp_dir)
    assert metrics.timestamps["execution_finished_at"] is not None


def test_record_learning_and_preset(temp_dir):
    """Test: Registrar hints de learning y presets aplicados."""
    plan_id = "plan_test123"
    initialize_metrics(plan_id, 10, base_dir=temp_dir)
    
    record_learning_hint_applied(plan_id, count=3, base_dir=temp_dir)
    record_preset_applied(plan_id, count=2, base_dir=temp_dir)
    
    metrics = load_metrics(plan_id, base_dir=temp_dir)
    assert metrics.source_breakdown["learning_hint_resolved"] == 3
    assert metrics.source_breakdown["preset_applied"] == 2


def test_record_manual_decision(temp_dir):
    """Test: Registrar decisiones manuales (single vs batch)."""
    plan_id = "plan_test123"
    initialize_metrics(plan_id, 5, base_dir=temp_dir)
    
    record_manual_decision(plan_id, is_batch=False, base_dir=temp_dir)
    record_manual_decision(plan_id, is_batch=True, base_dir=temp_dir)
    record_manual_decision(plan_id, is_batch=True, base_dir=temp_dir)
    
    metrics = load_metrics(plan_id, base_dir=temp_dir)
    assert metrics.source_breakdown["manual_single"] == 1
    assert metrics.source_breakdown["manual_batch"] == 2
