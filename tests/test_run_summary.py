"""
Unit tests para run_summary.

SPRINT C2.16: Valida que run_summary se guarda y carga correctamente.
"""
import pytest
from pathlib import Path
import json
import tempfile
import shutil
from datetime import datetime
from backend.shared.run_summary import save_run_summary, load_run_summary, list_run_summaries


def test_save_run_summary_plan():
    """SPRINT C2.16.2: Test para run_summary con run_kind='plan'."""
    import tempfile
    import shutil
    from datetime import datetime
    from pathlib import Path
    from backend.shared.run_summary import save_run_summary, load_run_summary
    
    with tempfile.TemporaryDirectory() as tmpdir:
        run_id = "plan_test_123"
        started_at = datetime.utcnow()
        
        summary_path = save_run_summary(
            run_id=run_id,
            platform="egestiona",
            coord="Test Coord",
            company_key="TEST123",
            person_key="test_person",
            started_at=started_at,
            pending_total=10,
            auto_upload_count=2,
            review_required_count=3,
            no_match_count=5,
            run_kind="plan",  # SPRINT C2.16.2
            evidence_root=str(Path(tmpdir) / "runs" / run_id),
            evidence_paths={"plan_response": str(Path(tmpdir) / "runs" / run_id / "plan_response.json")},
            base_dir=tmpdir,
        )
        
        assert summary_path.exists()
        
        # Cargar y verificar
        loaded = load_run_summary(run_id, base_dir=tmpdir)
        assert loaded is not None
        assert loaded["run_id"] == run_id
        assert loaded["run_kind"] == "plan"  # SPRINT C2.16.2
        assert loaded["counts"]["pending_total"] == 10
        assert loaded["evidence_root"] is not None
        assert loaded["evidence_paths"] is not None
        assert "plan_response" in loaded["evidence_paths"]


def test_save_run_summary():
    """Test: save_run_summary guarda summary correctamente"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_id = "test_run_123"
        started_at = datetime.utcnow()
        
        summary_path = save_run_summary(
            run_id=run_id,
            platform="egestiona",
            coord="Kern",
            company_key="F63161988",
            person_key="erm",
            started_at=started_at,
            finished_at=datetime.utcnow(),
            duration_ms=300000,
            pending_total=16,
            auto_upload_count=4,
            review_required_count=8,
            no_match_count=4,
            attempted_uploads=3,
            success_uploads=2,
            failed_uploads=1,
            errors=[
                {
                    "phase": "upload",
                    "error_code": "upload_failed",
                    "message": "Upload failed",
                    "transient": False,
                    "attempt": 1,
                }
            ],
            base_dir=tmpdir,
        )
        
        assert summary_path.exists()
        
        # Verificar contenido
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
        
        assert summary["run_id"] == run_id
        assert summary["platform"] == "egestiona"
        assert summary["counts"]["pending_total"] == 16
        assert summary["execution"]["attempted_uploads"] == 3
        assert len(summary["errors"]) == 1


def test_load_run_summary():
    """Test: load_run_summary carga summary correctamente"""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_id = "test_run_456"
        started_at = datetime.utcnow()
        
        # Guardar summary
        save_run_summary(
            run_id=run_id,
            platform="egestiona",
            coord="Kern",
            company_key="F63161988",
            person_key=None,
            started_at=started_at,
            base_dir=tmpdir,
        )
        
        # Cargar summary
        summary = load_run_summary(run_id, base_dir=tmpdir)
        
        assert summary is not None
        assert summary["run_id"] == run_id
        assert summary["platform"] == "egestiona"


def test_load_run_summary_not_found():
    """Test: load_run_summary retorna None si no existe"""
    with tempfile.TemporaryDirectory() as tmpdir:
        summary = load_run_summary("nonexistent_run", base_dir=tmpdir)
        assert summary is None


def test_list_run_summaries():
    """Test: list_run_summaries lista summaries correctamente"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Crear múltiples runs
        for i in range(3):
            save_run_summary(
                run_id=f"test_run_{i}",
                platform="egestiona",
                coord="Kern",
                company_key="F63161988",
                person_key=None,
                started_at=datetime.utcnow(),
                base_dir=tmpdir,
            )
        
        summaries = list_run_summaries(limit=10, base_dir=tmpdir)
        
        assert len(summaries) == 3
        assert all(s["platform"] == "egestiona" for s in summaries)


def test_list_run_summaries_filter_platform():
    """Test: list_run_summaries filtra por plataforma"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Crear runs de diferentes plataformas
        save_run_summary(
            run_id="test_run_egestiona",
            platform="egestiona",
            coord="Kern",
            company_key="F63161988",
            person_key=None,
            started_at=datetime.utcnow(),
            base_dir=tmpdir,
        )
        save_run_summary(
            run_id="test_run_other",
            platform="other",
            coord="Kern",
            company_key="F63161988",
            person_key=None,
            started_at=datetime.utcnow(),
            base_dir=tmpdir,
        )
        
        summaries = list_run_summaries(limit=10, platform="egestiona", base_dir=tmpdir)
        
        assert len(summaries) == 1
        assert summaries[0]["platform"] == "egestiona"
