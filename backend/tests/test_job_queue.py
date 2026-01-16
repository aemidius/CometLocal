"""
Tests unitarios para cola de ejecuciones CAE v1.8.
"""

import pytest
import os
import asyncio
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# No usar pytest_plugins - usamos asyncio.run() directamente

from backend.cae.job_queue_models_v1 import CAEJobV1, CAEJobStatus, CAEJobProgressV1
from backend.cae.job_queue_v1 import enqueue_job, get_job, list_jobs, start_worker, stop_worker, cancel_job, retry_job
from backend.cae.submission_models_v1 import CAESubmissionPlanV1, CAESubmissionItemV1, CAEScopeContextV1
from backend.cae.execution_models_v1 import RunResultV1


@pytest.fixture(autouse=True)
def reset_job_queue():
    """Limpia la cola antes y después de cada test."""
    from backend.cae.job_queue_v1 import _jobs, _queue, _current_job_id
    _jobs.clear()
    _queue.clear()
    _current_job_id = None
    yield
    _jobs.clear()
    _queue.clear()
    _current_job_id = None


@pytest.fixture
def sample_plan():
    """Crea un plan de ejemplo."""
    return CAESubmissionPlanV1(
        plan_id="TEST-PLAN-001",
        created_at=datetime.utcnow(),
        scope=CAEScopeContextV1(
            platform_key="egestiona",
            type_ids=[],
            company_key="TEDELAB",
            person_key="EMILIO",
            mode="PREPARE_WRITE",
        ),
        decision="READY",
        reasons=[],
        items=[
            CAESubmissionItemV1(
                kind="MISSING_PERIOD",
                type_id="TEST_TYPE",
                scope="worker",
                company_key="TEDELAB",
                person_key="EMILIO",
                period_key="2025-01",
                suggested_doc_id="doc-001",
                status="PLANNED",
            ),
            CAESubmissionItemV1(
                kind="MISSING_PERIOD",
                type_id="TEST_TYPE",
                scope="worker",
                company_key="TEDELAB",
                person_key="EMILIO",
                period_key="2025-02",
                suggested_doc_id="doc-002",
                status="PLANNED",
            ),
        ],
        summary={"total_items": 2},
    )


def test_enqueue_creates_job_queued(sample_plan):
    """Test que enqueue crea un job con status QUEUED."""
    job = enqueue_job(
        plan=sample_plan,
        challenge_token="test-token-123",
        challenge_response="EJECUTAR TEST-PLAN-001",
        dry_run=True,
    )
    
    assert job.status == "QUEUED"
    assert job.plan_id == "TEST-PLAN-001"
    assert job.progress.total_items == 2
    assert job.progress.percent == 0
    assert job.mode["dry_run"] is True
    assert job.job_id.startswith("CAEJOB-")
    
    # Verificar que está en la cola
    from backend.cae.job_queue_v1 import _queue, _jobs
    assert job.job_id in _jobs
    assert len(_queue) == 1


def test_get_job_returns_job(sample_plan):
    """Test que get_job devuelve el job correcto."""
    job = enqueue_job(
        plan=sample_plan,
        challenge_token="test-token-123",
        challenge_response="EJECUTAR TEST-PLAN-001",
        dry_run=True,
    )
    
    retrieved = get_job(job.job_id)
    assert retrieved is not None
    assert retrieved.job_id == job.job_id
    assert retrieved.status == "QUEUED"


def test_get_job_returns_none_for_invalid_id():
    """Test que get_job devuelve None para ID inválido."""
    assert get_job("INVALID-ID") is None


def test_list_jobs_order(sample_plan):
    """Test que list_jobs devuelve jobs ordenados por created_at desc."""
    # Crear 3 jobs con delays mínimos
    import time
    job1 = enqueue_job(
        plan=sample_plan,
        challenge_token="token1",
        challenge_response="EJECUTAR TEST-PLAN-001",
        dry_run=True,
    )
    time.sleep(0.01)
    job2 = enqueue_job(
        plan=sample_plan,
        challenge_token="token2",
        challenge_response="EJECUTAR TEST-PLAN-001",
        dry_run=True,
    )
    time.sleep(0.01)
    job3 = enqueue_job(
        plan=sample_plan,
        challenge_token="token3",
        challenge_response="EJECUTAR TEST-PLAN-001",
        dry_run=True,
    )
    
    jobs = list_jobs(limit=10)
    assert len(jobs) == 3
    # El más reciente debe ser el primero
    assert jobs[0].job_id == job3.job_id
    assert jobs[1].job_id == job2.job_id
    assert jobs[2].job_id == job1.job_id


def test_list_jobs_limit(sample_plan):
    """Test que list_jobs respeta el límite."""
    # Crear 5 jobs
    for i in range(5):
        enqueue_job(
            plan=sample_plan,
            challenge_token=f"token{i}",
            challenge_response="EJECUTAR TEST-PLAN-001",
            dry_run=True,
        )
    
    jobs = list_jobs(limit=3)
    assert len(jobs) == 3


def test_worker_processes_job_fake_success(sample_plan, tmp_path):
    """Test que el worker procesa un job en modo FAKE y lo marca como SUCCESS."""
    import json
    import os
    from pathlib import Path
    
    # Mock DATA_DIR para usar tmp_path
    with patch('backend.config.DATA_DIR', tmp_path):
        # Crear directorio de evidencia
        evidence_dir = tmp_path / "docs" / "evidence" / "cae_plans"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        
        # Guardar plan como JSON
        plan_file = evidence_dir / f"{sample_plan.plan_id}.json"
        plan_file.write_text(
            json.dumps(sample_plan.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        
        # Crear directorio de runs
        runs_dir = tmp_path / "docs" / "evidence" / "cae_runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        
        # Mock challenge validation (está en submission_routes, pero se importa en job_queue_v1)
        with patch('backend.cae.submission_routes._validate_challenge', return_value=(True, None)):
            # Mock execution runner para que devuelva SUCCESS
            with patch('backend.cae.job_queue_v1.CAEExecutionRunnerV1') as MockRunner:
                mock_runner_instance = MockRunner.return_value
                
                # Crear un resultado mock async
                async def mock_execute(*args, **kwargs):
                    # Simular callback de progreso
                    on_progress = kwargs.get('on_progress')
                    if on_progress:
                        from backend.cae.job_queue_models_v1 import CAEJobProgressV1
                        # Progreso inicial
                        on_progress(CAEJobProgressV1(
                            total_items=2,
                            current_index=0,
                            items_success=0,
                            items_failed=0,
                            items_blocked=0,
                            percent=0,
                            message="Iniciando...",
                        ))
                        await asyncio.sleep(0.01)  # Pequeño delay para simular trabajo
                        # Progreso intermedio
                        on_progress(CAEJobProgressV1(
                            total_items=2,
                            current_index=1,
                            items_success=1,
                            items_failed=0,
                            items_blocked=0,
                            percent=50,
                            message="Subiendo item 1/2...",
                        ))
                        await asyncio.sleep(0.01)
                        # Progreso final
                        on_progress(CAEJobProgressV1(
                            total_items=2,
                            current_index=2,
                            items_success=2,
                            items_failed=0,
                            items_blocked=0,
                            percent=100,
                            message="Completado",
                        ))
                    
                    return RunResultV1(
                        run_id="TEST-RUN-001",
                        status="SUCCESS",
                        evidence_path=str(runs_dir / "TEST-RUN-001"),
                        summary={
                            "total_items": 2,
                            "items_success": 2,
                            "items_failed": 0,
                            "items_blocked": 0,
                        },
                        started_at=datetime.utcnow(),
                        finished_at=datetime.utcnow(),
                    )
                
                mock_runner_instance.execute_plan_egestiona_with_progress = mock_execute
                
                # Encolar job
                job = enqueue_job(
                    plan=sample_plan,
                    challenge_token="test-token",
                    challenge_response="EJECUTAR TEST-PLAN-001",
                    dry_run=True,
                )
                
                job_id = job.job_id
                
                # Ejecutar test async usando asyncio.run()
                async def run_test():
                    # Iniciar worker
                    start_worker()
                    
                    try:
                        # Esperar activamente a que el job termine (polling corto)
                        max_iterations = 100  # Máximo 100 iteraciones
                        for i in range(max_iterations):
                            await asyncio.sleep(0)  # Yield al event loop
                            job = get_job(job_id)
                            if job and job.status in ("SUCCESS", "FAILED", "BLOCKED"):
                                break
                            # Pequeño delay para dar tiempo al worker
                            await asyncio.sleep(0.05)
                        
                        # Verificar resultado
                        final_job = get_job(job_id)
                        assert final_job is not None, "Job no encontrado"
                        if final_job.status != "SUCCESS":
                            error_msg = f"Job status: {final_job.status}, error: {final_job.error}"
                            print(f"[TEST] Job failed: {error_msg}")
                        assert final_job.status == "SUCCESS", f"Status esperado SUCCESS, obtenido {final_job.status} (error: {final_job.error})"
                        assert final_job.progress.percent == 100, f"Percent esperado 100, obtenido {final_job.progress.percent}"
                        assert final_job.run_id == "TEST-RUN-001", f"Run ID esperado TEST-RUN-001, obtenido {final_job.run_id}"
                        assert final_job.evidence_path is not None, "evidence_path no debe ser None"
                        assert final_job.progress.items_success == 2, f"items_success esperado 2, obtenido {final_job.progress.items_success}"
                    finally:
                        # Detener worker
                        stop_worker()
                
                # Ejecutar el test async
                asyncio.run(run_test())


def test_job_progress_updates():
    """Test que el progreso se actualiza correctamente."""
    progress = CAEJobProgressV1(
        total_items=5,
        current_index=0,
        items_success=0,
        items_failed=0,
        items_blocked=0,
        percent=0,
        message="Iniciando...",
    )
    
    assert progress.percent == 0
    
    # Simular progreso
    progress.current_index = 2
    progress.percent = int((2 / 5) * 100)
    progress.message = "Subiendo item 2/5..."
    
    assert progress.percent == 40
    assert progress.current_index == 2
    
    # Completar
    progress.current_index = 5
    progress.percent = 100
    progress.items_success = 5
    
    assert progress.percent == 100
    assert progress.items_success == 5


# v1.9: Tests para persistencia, cancelación y reintento

def test_job_persistence_roundtrip(sample_plan, tmp_path):
    """Test que los jobs se pueden guardar y cargar desde disco."""
    import json
    from pathlib import Path
    
    # Mock DATA_DIR para usar tmp_path
    with patch('backend.config.DATA_DIR', tmp_path):
        # Crear directorio de jobs
        jobs_file = tmp_path / "cae_jobs.json"
        
        # Encolar un job
        job = enqueue_job(
            plan=sample_plan,
            challenge_token="test-token",
            challenge_response="EJECUTAR TEST-PLAN-001",
            dry_run=True,
        )
        
        # Guardar jobs (llamando a la función privada a través del módulo)
        from backend.cae.job_queue_v1 import _save_jobs, _load_jobs
        _save_jobs()
        
        # Verificar que el archivo existe
        assert jobs_file.exists()
        
        # Limpiar jobs en memoria
        from backend.cae.job_queue_v1 import _jobs, _queue
        job_id = job.job_id
        _jobs.clear()
        _queue.clear()
        
        # Cargar jobs
        _load_jobs()
        
        # Verificar que el job se cargó
        loaded_job = get_job(job_id)
        assert loaded_job is not None
        assert loaded_job.job_id == job_id
        assert loaded_job.status == "QUEUED"
        assert loaded_job.plan_id == sample_plan.plan_id


def test_cancel_queued_job(sample_plan):
    """Test que se puede cancelar un job en cola."""
    job = enqueue_job(
        plan=sample_plan,
        challenge_token="test-token",
        challenge_response="EJECUTAR TEST-PLAN-001",
        dry_run=True,
    )
    
    job_id = job.job_id
    
    # Verificar que está en cola
    from backend.cae.job_queue_v1 import _queue
    assert job_id in _queue
    
    # Cancelar
    canceled_job = cancel_job(job_id)
    assert canceled_job is not None
    assert canceled_job.status == "CANCELED"
    assert canceled_job.finished_at is not None
    assert job_id not in _queue


def test_cancel_running_job_sets_canceled(sample_plan):
    """Test que cancelar un job RUNNING marca cancel_requested."""
    job = enqueue_job(
        plan=sample_plan,
        challenge_token="test-token",
        challenge_response="EJECUTAR TEST-PLAN-001",
        dry_run=True,
    )
    
    job_id = job.job_id
    
    # Marcar como RUNNING manualmente
    from backend.cae.job_queue_v1 import _jobs
    job.status = "RUNNING"
    _jobs[job_id] = job
    
    # Cancelar
    canceled_job = cancel_job(job_id)
    assert canceled_job is not None
    assert canceled_job.cancel_requested is True
    assert canceled_job.status == "RUNNING"  # Sigue RUNNING hasta que el worker lo maneje


def test_cancel_terminal_job_returns_none(sample_plan):
    """Test que cancelar un job terminal retorna None."""
    job = enqueue_job(
        plan=sample_plan,
        challenge_token="test-token",
        challenge_response="EJECUTAR TEST-PLAN-001",
        dry_run=True,
    )
    
    job_id = job.job_id
    
    # Marcar como SUCCESS
    from backend.cae.job_queue_v1 import _jobs
    job.status = "SUCCESS"
    job.finished_at = datetime.utcnow()
    _jobs[job_id] = job
    
    # Intentar cancelar
    result = cancel_job(job_id)
    assert result is None


def test_retry_creates_new_job(sample_plan, tmp_path):
    """Test que retry crea un nuevo job."""
    import json
    from pathlib import Path
    
    # Mock DATA_DIR para usar tmp_path
    with patch('backend.config.DATA_DIR', tmp_path):
        # Crear directorio de evidencia
        evidence_dir = tmp_path / "docs" / "evidence" / "cae_plans"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        
        # Guardar plan como JSON
        plan_file = evidence_dir / f"{sample_plan.plan_id}.json"
        plan_file.write_text(
            json.dumps(sample_plan.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        
        # Crear job y marcarlo como FAILED
        job = enqueue_job(
            plan=sample_plan,
            challenge_token="test-token",
            challenge_response="EJECUTAR TEST-PLAN-001",
            dry_run=True,
        )
        
        job_id = job.job_id
        
        # Marcar como FAILED
        from backend.cae.job_queue_v1 import _jobs
        job.status = "FAILED"
        job.finished_at = datetime.utcnow()
        _jobs[job_id] = job
        
        # Reintentar
        new_job = retry_job(job_id)
        assert new_job is not None
        assert new_job.job_id != job_id
        assert new_job.status == "QUEUED"
        assert new_job.retry_of == job_id
        assert new_job.plan_id == sample_plan.plan_id


def test_retry_rejected_for_success(sample_plan):
    """Test que retry es rechazado para jobs SUCCESS."""
    job = enqueue_job(
        plan=sample_plan,
        challenge_token="test-token",
        challenge_response="EJECUTAR TEST-PLAN-001",
        dry_run=True,
    )
    
    job_id = job.job_id
    
    # Marcar como SUCCESS
    from backend.cae.job_queue_v1 import _jobs
    job.status = "SUCCESS"
    job.finished_at = datetime.utcnow()
    _jobs[job_id] = job
    
    # Intentar reintentar
    result = retry_job(job_id)
    assert result is None


def test_retry_rejected_for_canceled(sample_plan):
    """Test que retry es rechazado para jobs CANCELED."""
    job = enqueue_job(
        plan=sample_plan,
        challenge_token="test-token",
        challenge_response="EJECUTAR TEST-PLAN-001",
        dry_run=True,
    )
    
    job_id = job.job_id
    
    # Marcar como CANCELED
    from backend.cae.job_queue_v1 import _jobs
    job.status = "CANCELED"
    job.finished_at = datetime.utcnow()
    _jobs[job_id] = job
    
    # Intentar reintentar
    result = retry_job(job_id)
    assert result is None

