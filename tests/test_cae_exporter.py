"""
SPRINT C2.21: Tests para CAE Exporter.
"""
import pytest
from pathlib import Path
import tempfile
import json
import zipfile
from datetime import datetime

from backend.export.cae_exporter import export_cae, generate_readme


@pytest.fixture
def temp_data_dir(tmp_path):
    """Fixture con estructura de datos temporal."""
    data_dir = tmp_path / "data"
    runs_dir = data_dir / "runs"
    runs_dir.mkdir(parents=True)
    
    # Crear plan de ejemplo
    plan_id = "plan_test123"
    plan_dir = runs_dir / plan_id
    plan_dir.mkdir(parents=True)
    
    # Plan response
    plan_data = {
        "status": "ok",
        "plan_id": plan_id,
        "snapshot": {
            "items": [
                {
                    "pending_item_key": "item_1",
                    "tipo_doc": "T104",
                    "empresa": "COMPANY123",
                    "elemento": "PERSON123",
                    "periodo": "2025-01",
                },
                {
                    "pending_item_key": "item_2",
                    "tipo_doc": "T104",
                    "empresa": "COMPANY123",
                    "elemento": "PERSON123",
                    "periodo": "2025-02",  # Fuera del periodo
                },
            ],
        },
        "decisions": [
            {
                "pending_item_key": "item_1",
                "decision": "AUTO_UPLOAD",
            },
        ],
        "artifacts": {
            "company_key": "COMPANY123",
            "person_key": "PERSON123",
        },
    }
    
    with open(plan_dir / "plan_response.json", "w", encoding="utf-8") as f:
        json.dump(plan_data, f)
    
    # Métricas
    metrics_data = {
        "plan_id": plan_id,
        "total_items": 2,
        "decisions_count": {
            "AUTO_UPLOAD": 1,
            "REVIEW_REQUIRED": 0,
            "NO_MATCH": 0,
            "SKIP": 0,
        },
        "source_breakdown": {
            "auto_matching": 1,
            "learning_hint_resolved": 0,
            "preset_applied": 0,
            "manual_single": 0,
            "manual_batch": 0,
        },
    }
    
    with open(plan_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_data, f)
    
    return data_dir


def test_export_cae_basic(temp_data_dir, tmp_path):
    """Test: Export básico genera ZIP con estructura correcta."""
    output_dir = tmp_path / "exports"
    output_dir.mkdir()
    
    zip_path = export_cae(
        company_key="COMPANY123",
        period="2025-01",
        output_dir=output_dir,
        base_dir=temp_data_dir,
    )
    
    assert zip_path.exists()
    assert zip_path.suffix == ".zip"
    
    # Verificar contenido del ZIP
    with zipfile.ZipFile(zip_path, "r") as zipf:
        files = zipf.namelist()
        
        # Debe tener README.md
        assert "README.md" in files
        
        # Debe tener summary.json
        assert "summary.json" in files
        
        # Debe tener métricas
        assert any("metrics/" in f for f in files)
        
        # Debe tener plan
        assert any("plans/plan_" in f for f in files)


def test_export_cae_filters_by_period(temp_data_dir, tmp_path):
    """Test: Export filtra items por periodo."""
    output_dir = tmp_path / "exports"
    output_dir.mkdir()
    
    zip_path = export_cae(
        company_key="COMPANY123",
        period="2025-01",
        output_dir=output_dir,
        base_dir=temp_data_dir,
    )
    
    with zipfile.ZipFile(zip_path, "r") as zipf:
        summary_str = zipf.read("summary.json").decode("utf-8")
        summary = json.loads(summary_str)
        
        # Debe tener solo 1 item (2025-01, no 2025-02)
        assert summary["total_items"] == 1
        assert summary["total_plans"] == 1


def test_export_cae_filters_by_company(temp_data_dir, tmp_path):
    """Test: Export filtra por company_key."""
    output_dir = tmp_path / "exports"
    output_dir.mkdir()
    
    zip_path = export_cae(
        company_key="COMPANY999",  # Diferente
        period="2025-01",
        output_dir=output_dir,
        base_dir=temp_data_dir,
    )
    
    with zipfile.ZipFile(zip_path, "r") as zipf:
        summary_str = zipf.read("summary.json").decode("utf-8")
        summary = json.loads(summary_str)
        
        # No debe tener items (company_key diferente)
        assert summary["total_items"] == 0
        assert summary["total_plans"] == 0


def test_generate_readme():
    """Test: README se genera correctamente."""
    readme = generate_readme(
        company_key="COMPANY123",
        period="2025-01",
        total_items=10,
        total_auto_upload=8,
        total_learning_hints=2,
        total_presets=1,
        plans_count=3,
        export_date=datetime.now(),
    )
    
    assert "COMPANY123" in readme
    assert "2025-01" in readme
    assert "10" in readme
    assert "8" in readme
