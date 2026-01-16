"""
Tests unitarios para ejecución de planes CAE v1.2.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from pathlib import Path

from backend.cae.submission_models_v1 import (
    CAEScopeContextV1,
    CAESubmissionPlanV1,
    CAESubmissionItemV1,
)
from backend.cae.execution_models_v1 import ChallengeRequestV1, ExecuteRequestV1
from backend.cae.execution_runner_v1 import CAEExecutionRunnerV1, CAE_WRITE_ALLOWLIST
from backend.cae.submission_routes import (
    create_challenge,
    execute_plan,
    _validate_challenge,
    _save_challenge,
    _get_challenge,
)
from backend.cae.submission_planner_v1 import CAESubmissionPlannerV1
from fastapi import HTTPException


@pytest.fixture
def mock_planner():
    """Mock del planificador."""
    planner = Mock(spec=CAESubmissionPlannerV1)
    return planner


@pytest.fixture
def ready_plan():
    """Plan READY para ejecutar."""
    return CAESubmissionPlanV1(
        plan_id="CAEPLAN-TEST-001",
        created_at=datetime.now(),
        scope=CAEScopeContextV1(
            platform_key="egestiona",
            type_ids=["T104_AUTONOMOS_RECEIPT"],
            company_key=CAE_WRITE_ALLOWLIST["company_key"],
            person_key=CAE_WRITE_ALLOWLIST["person_key"],
            mode="PREPARE_WRITE",
        ),
        decision="READY",
        reasons=[],
        items=[
            CAESubmissionItemV1(
                kind="MISSING_PERIOD",
                type_id="T104_AUTONOMOS_RECEIPT",
                scope="worker",
                company_key=CAE_WRITE_ALLOWLIST["company_key"],
                person_key=CAE_WRITE_ALLOWLIST["person_key"],
                period_key="2025-12",
                status="PLANNED",
                resolved_dates={"valid_from": "2025-12-01", "valid_to": "2025-12-31"},
            )
        ],
        summary={"pending_items": 1, "docs_candidates": 0, "total_items": 1},
        executor_hint="egestiona_upload_v1",
    )


@pytest.fixture
def blocked_plan():
    """Plan BLOCKED (no ejecutable)."""
    return CAESubmissionPlanV1(
        plan_id="CAEPLAN-TEST-002",
        created_at=datetime.now(),
        scope=CAEScopeContextV1(
            platform_key="egestiona",
            type_ids=[],
            mode="READ_ONLY",
        ),
        decision="BLOCKED",
        reasons=["No hay items"],
        items=[],
        summary={"pending_items": 0, "docs_candidates": 0, "total_items": 0},
        executor_hint=None,
    )


class TestChallengeValidation:
    """Tests para validación de challenges (lógica síncrona)."""
    
    def test_validate_challenge_happy_path(self, tmp_path):
        """Test que la validación de challenge funciona correctamente."""
        with patch('backend.cae.submission_routes.DATA_DIR', tmp_path):
            plan_id = "CAEPLAN-TEST-001"
            challenge_token = "test_token_123"
            expires_at = datetime.now() + timedelta(minutes=5)
            
            _save_challenge(plan_id, challenge_token, expires_at)
            
            # Validar challenge correcto
            is_valid, error = _validate_challenge(
                challenge_token=challenge_token,
                challenge_response=f"EJECUTAR {plan_id}",
                plan_id=plan_id,
            )
            assert is_valid
            assert error is None
            
            # Validar challenge con respuesta incorrecta
            is_valid2, error2 = _validate_challenge(
                challenge_token=challenge_token,
                challenge_response="RESPUESTA_INCORRECTA",
                plan_id=plan_id,
            )
            assert not is_valid2
            assert "incorrecto" in error2.lower()
            
            # Validar challenge con token inválido
            is_valid3, error3 = _validate_challenge(
                challenge_token="INVALID_TOKEN",
                challenge_response=f"EJECUTAR {plan_id}",
                plan_id=plan_id,
            )
            assert not is_valid3
            assert "inválido" in error3.lower() or "expirado" in error3.lower()
    
    def test_validate_challenge_expired(self, tmp_path):
        """Test que la validación rechaza challenges expirados."""
        with patch('backend.cae.submission_routes.DATA_DIR', tmp_path):
            plan_id = "CAEPLAN-TEST-002"
            challenge_token = "expired_token"
            expires_at = datetime.now() - timedelta(minutes=1)  # Expirado
            
            _save_challenge(plan_id, challenge_token, expires_at)
            
            is_valid, error = _validate_challenge(
                challenge_token=challenge_token,
                challenge_response=f"EJECUTAR {plan_id}",
                plan_id=plan_id,
            )
            assert not is_valid
            assert "expirado" in error.lower()


class TestExecutionRunner:
    """Tests para el execution runner."""
    
    def test_execute_allows_multiple_items(self, tmp_path):
        """Test que el runner permite planes con múltiples items (v1.4)."""
        with patch('backend.cae.execution_runner_v1.DATA_DIR', tmp_path):
            with patch.dict('os.environ', {'CAE_EXECUTOR_MODE': 'FAKE'}):
                runner = CAEExecutionRunnerV1()
                
                # Plan con 2 items
                plan_with_multiple = CAESubmissionPlanV1(
                    plan_id="CAEPLAN-TEST-003",
                    created_at=datetime.now(),
                    scope=CAEScopeContextV1(
                        platform_key="egestiona",
                        type_ids=["T104_AUTONOMOS_RECEIPT"],
                        company_key=CAE_WRITE_ALLOWLIST["company_key"],
                        person_key=CAE_WRITE_ALLOWLIST["person_key"],
                        mode="PREPARE_WRITE",
                    ),
                    decision="READY",
                    reasons=[],
                    items=[
                        CAESubmissionItemV1(
                            kind="MISSING_PERIOD",
                            type_id="T104_AUTONOMOS_RECEIPT",
                            scope="worker",
                            company_key=CAE_WRITE_ALLOWLIST["company_key"],
                            person_key=CAE_WRITE_ALLOWLIST["person_key"],
                            period_key="2025-12",
                            status="PLANNED",
                        ),
                        CAESubmissionItemV1(
                            kind="MISSING_PERIOD",
                            type_id="T104_AUTONOMOS_RECEIPT",
                            scope="worker",
                            company_key=CAE_WRITE_ALLOWLIST["company_key"],
                            person_key=CAE_WRITE_ALLOWLIST["person_key"],
                            period_key="2026-01",
                            status="PLANNED",
                        ),
                    ],
                    summary={"pending_items": 2, "docs_candidates": 0, "total_items": 2},
                    executor_hint="egestiona_upload_v1",
                )
                
                result = runner.execute_plan_egestiona(plan=plan_with_multiple, dry_run=True)
                
                # v1.4: Múltiples items están permitidos
                assert result.status == "SUCCESS"
                assert result.summary["total_items"] == 2
                assert result.summary["items_success"] == 2
    
    def test_execute_fake_mode_success(self, tmp_path):
        """Test que el runner ejecuta correctamente en modo FAKE."""
        with patch('backend.cae.execution_runner_v1.DATA_DIR', tmp_path):
            with patch.dict('os.environ', {'CAE_EXECUTOR_MODE': 'FAKE'}):
                runner = CAEExecutionRunnerV1()
                
                plan = CAESubmissionPlanV1(
                    plan_id="CAEPLAN-TEST-004",
                    created_at=datetime.now(),
                    scope=CAEScopeContextV1(
                        platform_key="egestiona",
                        type_ids=["T104_AUTONOMOS_RECEIPT"],
                        company_key=CAE_WRITE_ALLOWLIST["company_key"],
                        person_key=CAE_WRITE_ALLOWLIST["person_key"],
                        mode="PREPARE_WRITE",
                    ),
                    decision="READY",
                    reasons=[],
                    items=[
                        CAESubmissionItemV1(
                            kind="MISSING_PERIOD",
                            type_id="T104_AUTONOMOS_RECEIPT",
                            scope="worker",
                            company_key=CAE_WRITE_ALLOWLIST["company_key"],
                            person_key=CAE_WRITE_ALLOWLIST["person_key"],
                            period_key="2025-12",
                            status="PLANNED",
                        )
                    ],
                    summary={"pending_items": 1, "docs_candidates": 0, "total_items": 1},
                    executor_hint="egestiona_upload_v1",
                )
                
                result = runner.execute_plan_egestiona(plan=plan, dry_run=True)
                
                assert result.status == "SUCCESS"
                assert result.run_id.startswith("CAERUN-")
                assert Path(result.evidence_path).exists()
                assert (Path(result.evidence_path) / "manifest.json").exists()
                assert (Path(result.evidence_path) / "run_finished.json").exists()
    
    def test_execute_validates_allowlist(self, tmp_path):
        """Test que el runner valida el allowlist."""
        with patch('backend.cae.execution_runner_v1.DATA_DIR', tmp_path):
            runner = CAEExecutionRunnerV1()
            
            # Plan con company_key no permitido
            plan_invalid_company = CAESubmissionPlanV1(
                plan_id="CAEPLAN-TEST-005",
                created_at=datetime.now(),
                scope=CAEScopeContextV1(
                    platform_key="egestiona",
                    type_ids=["T104_AUTONOMOS_RECEIPT"],
                    company_key="INVALID_COMPANY",
                    person_key=CAE_WRITE_ALLOWLIST["person_key"],
                    mode="PREPARE_WRITE",
                ),
                decision="READY",
                reasons=[],
                items=[
                    CAESubmissionItemV1(
                        kind="MISSING_PERIOD",
                        type_id="T104_AUTONOMOS_RECEIPT",
                        scope="worker",
                        company_key="INVALID_COMPANY",
                        person_key=CAE_WRITE_ALLOWLIST["person_key"],
                        period_key="2025-12",
                        status="PLANNED",
                    )
                ],
                summary={"pending_items": 1, "docs_candidates": 0, "total_items": 1},
                executor_hint="egestiona_upload_v1",
            )
            
            result = runner.execute_plan_egestiona(plan=plan_invalid_company, dry_run=True)
            
            assert result.status == "BLOCKED"
            assert "allowlist" in result.error.lower()
    
    def test_execute_real_mode_without_credentials_returns_blocked(self, tmp_path):
        """Test que el modo REAL sin credenciales retorna FAILED (no 500)."""
        with patch('backend.cae.execution_runner_v1.DATA_DIR', tmp_path):
            with patch.dict('os.environ', {'CAE_EXECUTOR_MODE': 'REAL'}):
                runner = CAEExecutionRunnerV1()
                
                plan = CAESubmissionPlanV1(
                    plan_id="CAEPLAN-TEST-006",
                    created_at=datetime.now(),
                    scope=CAEScopeContextV1(
                        platform_key="egestiona",
                        type_ids=["T104_AUTONOMOS_RECEIPT"],
                        company_key=CAE_WRITE_ALLOWLIST["company_key"],
                        person_key=CAE_WRITE_ALLOWLIST["person_key"],
                        mode="PREPARE_WRITE",
                    ),
                    decision="READY",
                    reasons=[],
                    items=[
                        CAESubmissionItemV1(
                            kind="MISSING_PERIOD",
                            type_id="T104_AUTONOMOS_RECEIPT",
                            scope="worker",
                            company_key=CAE_WRITE_ALLOWLIST["company_key"],
                            person_key=CAE_WRITE_ALLOWLIST["person_key"],
                            period_key="2025-12",
                            status="PLANNED",
                            suggested_doc_id="test-doc-001",
                        )
                    ],
                    summary={"pending_items": 1, "docs_candidates": 0, "total_items": 1},
                    executor_hint="egestiona_upload_v1",
                )
                
                # Mock store y config para simular falta de credenciales
                from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
                from backend.repository.config_store_v1 import ConfigStoreV1
                
                with patch.object(DocumentRepositoryStoreV1, 'get_document', return_value=None):
                    # El documento no existe, debe retornar FAILED
                    result = runner.execute_plan_egestiona(plan=plan, dry_run=False)
                    
                    # Debe retornar FAILED, no lanzar excepción
                    assert result.status == "FAILED"
                    assert result.error is not None
                    assert "no encontrado" in result.error.lower() or "error" in result.error.lower()
    
    def test_execute_real_write_requires_suggested_doc_id(self, tmp_path):
        """Test que REAL write requiere suggested_doc_id obligatorio (v1.3.1)."""
        with patch('backend.cae.execution_runner_v1.DATA_DIR', tmp_path):
            with patch.dict('os.environ', {'CAE_EXECUTOR_MODE': 'REAL'}):
                runner = CAEExecutionRunnerV1()
                
                plan = CAESubmissionPlanV1(
                    plan_id="CAEPLAN-TEST-007",
                    created_at=datetime.now(),
                    scope=CAEScopeContextV1(
                        platform_key="egestiona",
                        type_ids=["T104_AUTONOMOS_RECEIPT"],
                        company_key=CAE_WRITE_ALLOWLIST["company_key"],
                        person_key=CAE_WRITE_ALLOWLIST["person_key"],
                        mode="PREPARE_WRITE",
                    ),
                    decision="READY",
                    reasons=[],
                    items=[
                        CAESubmissionItemV1(
                            kind="MISSING_PERIOD",
                            type_id="T104_AUTONOMOS_RECEIPT",
                            scope="worker",
                            company_key=CAE_WRITE_ALLOWLIST["company_key"],
                            person_key=CAE_WRITE_ALLOWLIST["person_key"],
                            period_key="2025-12",
                            status="PLANNED",
                            suggested_doc_id=None,  # Sin suggested_doc_id
                        )
                    ],
                    summary={"pending_items": 1, "docs_candidates": 0, "total_items": 1},
                    executor_hint="egestiona_upload_v1",
                )
                
                # Debe ser BLOCKED en _execute_real (no en validación general)
                result = runner.execute_plan_egestiona(plan=plan, dry_run=False)
                
                # Debe retornar BLOCKED, no FAILED
                assert result.status == "BLOCKED"
                assert result.error is not None
                assert "suggested_doc_id" in result.error.lower()
    
    def test_execute_batch_two_items_fake_success(self, tmp_path):
        """Test batch: 2 items -> FAKE SUCCESS (v1.4)."""
        with patch('backend.cae.execution_runner_v1.DATA_DIR', tmp_path):
            with patch.dict('os.environ', {'CAE_EXECUTOR_MODE': 'FAKE'}):
                runner = CAEExecutionRunnerV1()
                
                plan = CAESubmissionPlanV1(
                    plan_id="CAEPLAN-TEST-008",
                    created_at=datetime.now(),
                    scope=CAEScopeContextV1(
                        platform_key="egestiona",
                        type_ids=["T104_AUTONOMOS_RECEIPT"],
                        company_key=CAE_WRITE_ALLOWLIST["company_key"],
                        person_key=CAE_WRITE_ALLOWLIST["person_key"],
                        mode="PREPARE_WRITE",
                    ),
                    decision="READY",
                    reasons=[],
                    items=[
                        CAESubmissionItemV1(
                            kind="MISSING_PERIOD",
                            type_id="T104_AUTONOMOS_RECEIPT",
                            scope="worker",
                            company_key=CAE_WRITE_ALLOWLIST["company_key"],
                            person_key=CAE_WRITE_ALLOWLIST["person_key"],
                            period_key="2025-12",
                            status="PLANNED",
                        ),
                        CAESubmissionItemV1(
                            kind="MISSING_PERIOD",
                            type_id="T104_AUTONOMOS_RECEIPT",
                            scope="worker",
                            company_key=CAE_WRITE_ALLOWLIST["company_key"],
                            person_key=CAE_WRITE_ALLOWLIST["person_key"],
                            period_key="2026-01",
                            status="PLANNED",
                        ),
                    ],
                    summary={"pending_items": 2, "docs_candidates": 0, "total_items": 2},
                    executor_hint="egestiona_upload_v1",
                )
                
                result = runner.execute_plan_egestiona(plan=plan, dry_run=True)
                
                assert result.status == "SUCCESS"
                assert result.summary["total_items"] == 2
                assert result.summary["items_success"] == 2
                assert result.summary["items_processed"] == 2
                
                # Verificar que hay subcarpetas por item
                evidence_path = Path(result.evidence_path)
                assert (evidence_path / "item_1").exists()
                assert (evidence_path / "item_2").exists()
                assert (evidence_path / "item_1" / "manifest.json").exists()
                assert (evidence_path / "item_2" / "manifest.json").exists()
    
    def test_execute_batch_second_item_fails_partial_success(self, tmp_path):
        """Test batch: 2 items donde 2º falla -> PARTIAL_SUCCESS (v1.4)."""
        with patch('backend.cae.execution_runner_v1.DATA_DIR', tmp_path):
            with patch.dict('os.environ', {'CAE_EXECUTOR_MODE': 'FAKE'}):
                runner = CAEExecutionRunnerV1()
                
                # Mock _execute_fake para que el segundo item falle
                original_execute_fake = runner._execute_fake
                call_count = [0]
                
                def mock_execute_fake(*args, **kwargs):
                    call_count[0] += 1
                    if call_count[0] == 2:
                        # Segundo item falla
                        item = kwargs.get('item') or args[1]
                        evidence_dir = kwargs.get('evidence_dir') or args[3]
                        started_at = kwargs.get('started_at') or args[5]
                        return runner._create_failed_run(
                            run_id=kwargs.get('run_id') or args[2],
                            evidence_dir=evidence_dir,
                            error="Simulated failure for second item",
                            started_at=started_at,
                        )
                    return original_execute_fake(*args, **kwargs)
                
                runner._execute_fake = mock_execute_fake
                
                plan = CAESubmissionPlanV1(
                    plan_id="CAEPLAN-TEST-009",
                    created_at=datetime.now(),
                    scope=CAEScopeContextV1(
                        platform_key="egestiona",
                        type_ids=["T104_AUTONOMOS_RECEIPT"],
                        company_key=CAE_WRITE_ALLOWLIST["company_key"],
                        person_key=CAE_WRITE_ALLOWLIST["person_key"],
                        mode="PREPARE_WRITE",
                    ),
                    decision="READY",
                    reasons=[],
                    items=[
                        CAESubmissionItemV1(
                            kind="MISSING_PERIOD",
                            type_id="T104_AUTONOMOS_RECEIPT",
                            scope="worker",
                            company_key=CAE_WRITE_ALLOWLIST["company_key"],
                            person_key=CAE_WRITE_ALLOWLIST["person_key"],
                            period_key="2025-12",
                            status="PLANNED",
                        ),
                        CAESubmissionItemV1(
                            kind="MISSING_PERIOD",
                            type_id="T104_AUTONOMOS_RECEIPT",
                            scope="worker",
                            company_key=CAE_WRITE_ALLOWLIST["company_key"],
                            person_key=CAE_WRITE_ALLOWLIST["person_key"],
                            period_key="2026-01",
                            status="PLANNED",
                        ),
                    ],
                    summary={"pending_items": 2, "docs_candidates": 0, "total_items": 2},
                    executor_hint="egestiona_upload_v1",
                )
                
                result = runner.execute_plan_egestiona(plan=plan, dry_run=True)
                
                assert result.status == "PARTIAL_SUCCESS"
                assert result.summary["total_items"] == 2
                assert result.summary["items_success"] == 1
                assert result.summary["items_failed"] == 1
                assert result.summary["items_processed"] == 2
                assert result.error is not None
                assert "Simulated failure" in result.error

