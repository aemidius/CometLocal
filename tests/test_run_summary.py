"""
SPRINT C2.29: Tests para RunSummary y estructura de directorios.
"""

import json
from pathlib import Path
from datetime import datetime

import pytest

from backend.shared.run_summary import (
    RunSummaryV1, RunContextV1, create_run_dir, save_run_summary, generate_summary_md
)
from backend.config import DATA_DIR


@pytest.fixture
def test_tenant_id():
    """Tenant ID para tests."""
    return "test_tenant_summary"


def test_create_run_dir(tmp_path, test_tenant_id):
    """Test: crear directorio de run con estructura correcta."""
    run_id = "test_run_123"
    run_dir = create_run_dir(tmp_path, test_tenant_id, run_id)
    
    assert run_dir.exists()
    assert run_dir.is_dir()
    
    # Verificar estructura
    assert (run_dir / "evidence").exists()
    assert (run_dir / "export").exists()
    
    # Verificar formato del nombre
    assert run_id in run_dir.name
    assert "__" in run_dir.name


def test_save_run_summary(tmp_path, test_tenant_id):
    """Test: guardar summary y archivos relacionados."""
    run_id = "test_run_123"
    run_dir = create_run_dir(tmp_path, test_tenant_id, run_id)
    
    context = RunContextV1(
        own_company_key="F63161988",
        own_company_name="Tedelab",
        platform_key="egestiona",
        platform_name="Egestiona",
        coordinated_company_key="test_co",
        coordinated_company_name="Test Company",
    )
    
    summary = RunSummaryV1(
        run_id=run_id,
        started_at=datetime.now(),
        finished_at=datetime.now(),
        status="success",
        context=context,
        plan_id="plan_123",
        dry_run=False,
        steps_executed=["step1", "step2"],
        counters={
            "docs_processed": 10,
            "uploads_attempted": 5,
            "uploads_ok": 4,
            "uploads_failed": 1,
        },
        artifacts={"evidence": "evidence/"},
        run_dir_rel=f"tenants/{test_tenant_id}/runs/{run_dir.name}",
    )
    
    input_data = {"type": "plan", "plan_id": "plan_123"}
    result_data = {"status": "SUCCESS", "run_id": run_id}
    
    save_run_summary(run_dir, summary, input_data, result_data)
    
    # Verificar archivos creados
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "summary.md").exists()
    assert (run_dir / "input.json").exists()
    assert (run_dir / "result.json").exists()
    
    # Verificar contenido de summary.json
    with open(run_dir / "summary.json", "r", encoding="utf-8") as f:
        saved_summary = json.load(f)
    
    assert saved_summary["run_id"] == run_id
    assert saved_summary["status"] == "success"
    assert saved_summary["context"]["own_company_key"] == "F63161988"


def test_generate_summary_md():
    """Test: generar summary.md legible."""
    context = RunContextV1(
        own_company_key="F63161988",
        own_company_name="Tedelab",
        platform_key="egestiona",
        platform_name="Egestiona",
        coordinated_company_key="test_co",
        coordinated_company_name="Test Company",
    )
    
    summary = RunSummaryV1(
        run_id="test_run_123",
        started_at=datetime.now(),
        finished_at=datetime.now(),
        status="success",
        context=context,
        plan_id="plan_123",
        dry_run=True,
        steps_executed=["step1", "step2"],
        counters={"docs_processed": 10},
        run_dir_rel="tenants/test/runs/test_dir",
    )
    
    md = generate_summary_md(summary)
    
    assert "# Run Summary" in md
    assert "test_run_123" in md
    assert "Tedelab" in md
    assert "Egestiona" in md
    assert "DRY-RUN" in md
    assert "step1" in md
    assert "docs_processed" in md
