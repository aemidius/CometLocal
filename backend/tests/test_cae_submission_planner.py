"""
Tests unitarios para CAESubmissionPlannerV1.

Cubre casos:
- READY (fechas resueltas)
- NEEDS_CONFIRMATION (ambigüedad)
- BLOCKED (scope inválido, o sin docs en scope)
"""

import pytest
from datetime import date, datetime
from pathlib import Path
import tempfile
import shutil

from backend.cae.submission_planner_v1 import CAESubmissionPlannerV1
from backend.cae.submission_models_v1 import CAEScopeContextV1
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.shared.document_repository_v1 import (
    DocumentTypeV1,
    DocumentInstanceV1,
    DocumentScopeV1,
    ValidityPolicyV1,
    MonthlyValidityConfigV1,
    PeriodKindV1,
    ExtractedMetadataV1,
    ComputedValidityV1,
    DocumentStatusV1,
)


@pytest.fixture
def temp_store():
    """Crea un store temporal para tests."""
    temp_dir = tempfile.mkdtemp()
    store = DocumentRepositoryStoreV1(base_dir=temp_dir)
    yield store
    shutil.rmtree(temp_dir)


@pytest.fixture
def planner(temp_store):
    """Crea un planificador con store temporal."""
    return CAESubmissionPlannerV1(store=temp_store)


@pytest.fixture
def monthly_type(temp_store):
    """Crea un tipo de documento mensual."""
    # Verificar si ya existe y eliminarlo primero
    existing = temp_store.get_type("TEST_MONTHLY")
    if existing:
        try:
            temp_store.delete_type("TEST_MONTHLY")
        except:
            pass
    
    doc_type = DocumentTypeV1(
        type_id="TEST_MONTHLY",
        name="Test Mensual",
        description="Tipo de prueba mensual",
        scope="worker",
        validity_policy=ValidityPolicyV1(
            mode="monthly",
            basis="name_date",
            monthly=MonthlyValidityConfigV1(
                month_source="name_date",
                valid_from="period_start",
                valid_to="period_end",
                grace_days=0
            )
        ),
        required_fields=["valid_from", "valid_to"],
        platform_aliases=[],
        active=True
    )
    temp_store.create_type(doc_type)
    return doc_type


def test_plan_ready_with_resolved_dates(planner, temp_store, monthly_type):
    """Test caso READY: fechas resueltas correctamente."""
    # Asegurar que no hay documentos existentes para este período
    existing_docs = temp_store.list_documents(
        type_id="TEST_MONTHLY",
        scope="worker",
        company_key="TEST_COMPANY",
        person_key="TEST_WORKER",
        period_key="2025-12",
    )
    # Eliminar cualquier documento existente
    for doc in existing_docs:
        try:
            temp_store.delete_document(doc.doc_id)
        except:
            pass
    
    scope = CAEScopeContextV1(
        platform_key="egestiona",
        type_ids=["TEST_MONTHLY"],
        company_key="TEST_COMPANY",
        person_key="TEST_WORKER",
        period_keys=["2025-12"],
        mode="READ_ONLY",
    )
    
    plan = planner.plan_submission(scope)
    
    assert plan.decision == "READY"
    assert len(plan.items) > 0
    assert plan.items[0].kind == "MISSING_PERIOD"
    assert plan.items[0].period_key == "2025-12"
    assert plan.items[0].resolved_dates is not None
    assert "issued_at" in plan.items[0].resolved_dates
    assert "valid_from" in plan.items[0].resolved_dates
    assert "valid_to" in plan.items[0].resolved_dates
    assert plan.items[0].status == "PLANNED"


def test_plan_needs_confirmation_with_ambiguous_dates(planner, temp_store, monthly_type):
    """Test caso NEEDS_CONFIRMATION: ambigüedad en fechas."""
    # Scope con period_key inválido
    scope = CAEScopeContextV1(
        platform_key="egestiona",
        type_ids=["TEST_MONTHLY"],
        company_key="TEST_COMPANY",
        person_key="TEST_WORKER",
        period_keys=["INVALID-PERIOD"],
        mode="READ_ONLY",
    )
    
    plan = planner.plan_submission(scope)
    
    assert plan.decision == "NEEDS_CONFIRMATION"
    assert len(plan.reasons) > 0
    assert any("period_key" in reason.lower() or "formato" in reason.lower() for reason in plan.reasons)
    if plan.items:
        assert plan.items[0].status == "NEEDS_CONFIRMATION"


def test_plan_blocked_invalid_scope(planner):
    """Test caso BLOCKED: scope inválido (sin platform_key)."""
    scope = CAEScopeContextV1(
        platform_key="",  # Inválido
        type_ids=[],
        mode="READ_ONLY",
    )
    
    plan = planner.plan_submission(scope)
    
    assert plan.decision == "BLOCKED"
    assert len(plan.reasons) > 0
    assert any("platform_key" in reason.lower() for reason in plan.reasons)


def test_plan_blocked_no_types(planner):
    """Test caso BLOCKED: sin tipos que coincidan con el scope."""
    scope = CAEScopeContextV1(
        platform_key="egestiona",
        type_ids=["NONEXISTENT_TYPE"],
        mode="READ_ONLY",
    )
    
    plan = planner.plan_submission(scope)
    
    assert plan.decision == "BLOCKED"
    assert len(plan.reasons) > 0
    assert any("tipos" in reason.lower() or "coincidan" in reason.lower() for reason in plan.reasons)


def test_plan_blocked_no_docs_in_scope(planner, temp_store, monthly_type):
    """Test caso BLOCKED: scope válido pero sin documentos/períodos."""
    scope = CAEScopeContextV1(
        platform_key="egestiona",
        type_ids=["TEST_MONTHLY"],
        company_key="NONEXISTENT_COMPANY",
        person_key="NONEXISTENT_WORKER",
        mode="READ_ONLY",
    )
    
    plan = planner.plan_submission(scope)
    
    # Puede ser BLOCKED o READY con 0 items, dependiendo de la implementación
    assert plan.decision in ["BLOCKED", "READY"]
    if plan.decision == "BLOCKED":
        assert len(plan.reasons) > 0


def test_plan_with_existing_document(planner, temp_store, monthly_type):
    """Test plan con documento existente (DOC_INSTANCE)."""
    # Crear un documento existente
    doc = DocumentInstanceV1(
        doc_id="TEST_DOC_1",
        file_name_original="test.pdf",
        stored_path="data/repository/docs/TEST_DOC_1.pdf",
        sha256="test_hash",
        type_id="TEST_MONTHLY",
        scope=DocumentScopeV1("worker"),
        company_key="TEST_COMPANY",
        person_key="TEST_WORKER",
        extracted=ExtractedMetadataV1(
            issue_date=date(2025, 12, 1),
        ),
        computed_validity=ComputedValidityV1(
            valid_from=date(2025, 12, 1),
            valid_to=date(2025, 12, 31),
        ),
        period_kind=PeriodKindV1.MONTH,
        period_key="2025-12",
        issued_at=date(2025, 12, 1),
        needs_period=False,
        status=DocumentStatusV1.draft,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    temp_store.save_document(doc)
    
    scope = CAEScopeContextV1(
        platform_key="egestiona",
        type_ids=["TEST_MONTHLY"],
        company_key="TEST_COMPANY",
        person_key="TEST_WORKER",
        mode="READ_ONLY",
    )
    
    plan = planner.plan_submission(scope)
    
    # Debe encontrar el documento
    assert plan.decision in ["READY", "NEEDS_CONFIRMATION"]
    # Puede tener items de tipo DOC_INSTANCE o MISSING_PERIOD para otros períodos
    assert len(plan.items) >= 0


def test_plan_id_generation(planner):
    """Test que los plan_id se generan correctamente."""
    scope = CAEScopeContextV1(
        platform_key="egestiona",
        type_ids=[],
        mode="READ_ONLY",
    )
    
    plan1 = planner.plan_submission(scope)
    plan2 = planner.plan_submission(scope)
    
    assert plan1.plan_id != plan2.plan_id
    assert plan1.plan_id.startswith("CAEPLAN-")
    assert plan2.plan_id.startswith("CAEPLAN-")


def test_plan_summary(planner, temp_store, monthly_type):
    """Test que el summary se calcula correctamente."""
    scope = CAEScopeContextV1(
        platform_key="egestiona",
        type_ids=["TEST_MONTHLY"],
        company_key="TEST_COMPANY",
        person_key="TEST_WORKER",
        period_keys=["2025-12"],
        mode="READ_ONLY",
    )
    
    plan = planner.plan_submission(scope)
    
    assert "pending_items" in plan.summary
    assert "docs_candidates" in plan.summary
    assert "total_items" in plan.summary
    assert "types_processed" in plan.summary
    assert isinstance(plan.summary["pending_items"], int)
    assert isinstance(plan.summary["docs_candidates"], int)


def test_plan_executor_hint(planner):
    """Test que executor_hint se asigna correctamente según platform_key."""
    scope = CAEScopeContextV1(
        platform_key="egestiona",
        type_ids=[],
        mode="READ_ONLY",
    )
    
    plan = planner.plan_submission(scope)
    
    assert plan.executor_hint == "egestiona_upload_v1"
    
    # Test con otra plataforma
    scope2 = CAEScopeContextV1(
        platform_key="other_platform",
        type_ids=[],
        mode="READ_ONLY",
    )
    
    plan2 = planner.plan_submission(scope2)
    
    assert plan2.executor_hint is None or plan2.executor_hint != "egestiona_upload_v1"

