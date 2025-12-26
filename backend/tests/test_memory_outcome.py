"""
Tests para memoria de resultados OutcomeJudge v4.2.0
"""

import json
import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from backend.memory.memory_store import MemoryStore
from backend.shared.models import WorkerMemory, CompanyMemory, PlatformMemory


class TestMemoryOutcome:
    """Tests para actualización de memoria con resultados de OutcomeJudge"""
    
    @pytest.fixture
    def temp_dir(self):
        """Crea un directorio temporal para tests"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    def test_update_worker_outcome_initializes_new_memory(self, temp_dir):
        """update_worker_outcome debe inicializar memoria nueva si no existe"""
        store = MemoryStore(temp_dir)
        now = datetime.now()
        
        updated = store.update_worker_outcome(
            worker_id="worker_123",
            new_score=0.85,
            issues=["Issue 1", "Issue 2"],
            timestamp=now
        )
        
        assert updated is not None
        assert updated.worker_id == "worker_123"
        assert updated.last_outcome_score == 0.85
        assert updated.best_outcome_score == 0.85
        assert updated.worst_outcome_score == 0.85
        assert updated.outcome_run_count == 1
        assert updated.last_outcome_issues == ["Issue 1", "Issue 2"]
        assert updated.last_outcome_timestamp == now
        assert len(updated.outcome_history) == 1
    
    def test_update_worker_outcome_updates_existing_memory(self, temp_dir):
        """update_worker_outcome debe actualizar memoria existente correctamente"""
        store = MemoryStore(temp_dir)
        now = datetime.now()
        
        # Primera actualización
        store.update_worker_outcome(
            worker_id="worker_123",
            new_score=0.90,
            issues=["Issue A"],
            timestamp=now
        )
        
        # Segunda actualización
        updated = store.update_worker_outcome(
            worker_id="worker_123",
            new_score=0.75,
            issues=["Issue B"],
            timestamp=now
        )
        
        assert updated.outcome_run_count == 2
        assert updated.last_outcome_score == 0.75
        assert updated.best_outcome_score == 0.90  # Mejor puntuación
        assert updated.worst_outcome_score == 0.75  # Peor puntuación
        assert updated.last_outcome_issues == ["Issue B"]
        assert len(updated.outcome_history) == 2
    
    def test_update_worker_outcome_limits_history(self, temp_dir):
        """update_worker_outcome debe limitar el historial a 10 entradas"""
        store = MemoryStore(temp_dir)
        now = datetime.now()
        
        # Añadir 12 ejecuciones
        for i in range(12):
            store.update_worker_outcome(
                worker_id="worker_123",
                new_score=0.8 + (i * 0.01),
                issues=[f"Issue {i}"],
                timestamp=now
            )
        
        memory = store.load_worker("worker_123")
        assert memory is not None
        assert memory.outcome_run_count == 12
        assert len(memory.outcome_history) == 10  # Solo últimos 10
    
    def test_update_company_outcome_calculates_incremental_average(self, temp_dir):
        """update_company_outcome debe calcular media incremental correctamente"""
        store = MemoryStore(temp_dir)
        now = datetime.now()
        
        # Primera actualización
        store.update_company_outcome(
            company_name="Empresa Test",
            platform="test_platform",
            worker_contribution_score=0.80,
            issues=["Issue 1"],
            timestamp=now
        )
        
        # Segunda actualización
        updated = store.update_company_outcome(
            company_name="Empresa Test",
            platform="test_platform",
            worker_contribution_score=0.90,
            issues=["Issue 2"],
            timestamp=now
        )
        
        assert updated.outcome_run_count == 2
        # Media: (0.80 * 1 + 0.90) / 2 = 0.85
        assert abs(updated.avg_outcome_score - 0.85) < 0.01
        assert updated.common_issues is not None
        assert "Issue 1" in updated.common_issues
        assert "Issue 2" in updated.common_issues
    
    def test_update_company_outcome_merges_common_issues(self, temp_dir):
        """update_company_outcome debe hacer merge de issues comunes"""
        store = MemoryStore(temp_dir)
        now = datetime.now()
        
        # Primera actualización
        store.update_company_outcome(
            company_name="Empresa Test",
            platform=None,
            worker_contribution_score=0.80,
            issues=["Issue A", "Issue B"],
            timestamp=now
        )
        
        # Segunda actualización con issues parcialmente nuevas
        updated = store.update_company_outcome(
            company_name="Empresa Test",
            platform=None,
            worker_contribution_score=0.85,
            issues=["Issue B", "Issue C"],
            timestamp=now
        )
        
        assert "Issue A" in updated.common_issues
        assert "Issue B" in updated.common_issues
        assert "Issue C" in updated.common_issues
    
    def test_update_platform_outcome_calculates_incremental_average(self, temp_dir):
        """update_platform_outcome debe calcular media incremental correctamente"""
        store = MemoryStore(temp_dir)
        now = datetime.now()
        
        # Primera actualización
        store.update_platform_outcome(
            platform_name="test_platform",
            company_contribution_score=0.75,
            issues=["Platform Issue 1"],
            timestamp=now
        )
        
        # Segunda actualización
        updated = store.update_platform_outcome(
            platform_name="test_platform",
            company_contribution_score=0.85,
            issues=["Platform Issue 2"],
            timestamp=now
        )
        
        assert updated.outcome_run_count == 2
        # Media: (0.75 * 1 + 0.85) / 2 = 0.80
        assert abs(updated.avg_outcome_score - 0.80) < 0.01
        assert updated.common_issues is not None
    
    def test_update_worker_outcome_handles_none_score(self, temp_dir):
        """update_worker_outcome debe manejar score None correctamente"""
        store = MemoryStore(temp_dir)
        now = datetime.now()
        
        updated = store.update_worker_outcome(
            worker_id="worker_123",
            new_score=None,
            issues=["Issue 1"],
            timestamp=now
        )
        
        assert updated is not None
        assert updated.last_outcome_score is None
        assert updated.best_outcome_score is None
        assert updated.worst_outcome_score is None
        assert updated.outcome_run_count == 1
        assert updated.last_outcome_issues == ["Issue 1"]
    
    def test_update_company_outcome_handles_none_score(self, temp_dir):
        """update_company_outcome debe manejar score None correctamente"""
        store = MemoryStore(temp_dir)
        now = datetime.now()
        
        # Primera actualización con score
        store.update_company_outcome(
            company_name="Empresa Test",
            platform=None,
            worker_contribution_score=0.80,
            issues=[],
            timestamp=now
        )
        
        # Segunda actualización sin score (no debe cambiar la media)
        updated = store.update_company_outcome(
            company_name="Empresa Test",
            platform=None,
            worker_contribution_score=None,
            issues=[],
            timestamp=now
        )
        
        assert updated.outcome_run_count == 2
        assert updated.avg_outcome_score == 0.80  # Media no cambia
    
    def test_update_worker_outcome_limits_issues(self, temp_dir):
        """update_worker_outcome debe limitar issues a top 5"""
        store = MemoryStore(temp_dir)
        now = datetime.now()
        
        many_issues = [f"Issue {i}" for i in range(10)]
        updated = store.update_worker_outcome(
            worker_id="worker_123",
            new_score=0.85,
            issues=many_issues,
            timestamp=now
        )
        
        assert len(updated.last_outcome_issues) == 5
        assert updated.last_outcome_issues == many_issues[:5]




















