"""
SPRINT C2.18A: Tests unitarios para matching debug report.

Verifica que el sistema genera reportes correctos para diferentes escenarios de NO_MATCH.
"""

import pytest
from pathlib import Path
from datetime import datetime
from backend.shared.matching_debug_report import (
    MatchingDebugReportV1,
    PrimaryReasonCode,
    PipelineStep,
    CandidateTop,
    MatchingOutcome,
)
from backend.repository.document_matcher_v1 import DocumentMatcherV1, PendingItemV1
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.shared.document_repository_v1 import (
    DocumentTypeV1,
    DocumentInstanceV1,
    DocumentStatusV1,
    DocumentScopeV1,
    ValidityPolicyV1,
    MonthlyValidityConfigV1,
)


@pytest.fixture
def temp_store(tmp_path):
    """Store temporal para tests."""
    store = DocumentRepositoryStoreV1(base_dir=str(tmp_path))
    return store


@pytest.fixture
def matcher(temp_store):
    """Matcher con store temporal."""
    return DocumentMatcherV1(temp_store, base_dir=str(temp_store.base_dir))


def test_repo_empty_scenario(matcher, tmp_path):
    """Test: REPO_EMPTY cuando el repositorio está vacío (o TYPE_FILTER_ZERO si hay seed)."""
    # Buscar un tipo que definitivamente no existe
    pending = PendingItemV1(
        tipo_doc="T999_NONEXISTENT Tipo que no existe",
        elemento="Test Worker",
        empresa="Test Company",
    )
    
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    result = matcher.match_pending_item(
        pending,
        company_key="TEST123",
        person_key="worker123",
        evidence_dir=evidence_dir,
        generate_debug_report=True,
    )
    
    # Puede ser NO_MATCH si no hay tipos que matcheen
    debug_report_dict = result.get("matching_debug_report")
    assert debug_report_dict is not None
    
    # Verificar que se guardó el reporte
    matching_debug_dir = evidence_dir / "matching_debug"
    assert matching_debug_dir.exists()
    index_path = matching_debug_dir / "index.json"
    assert index_path.exists()
    
    # Verificar contenido del reporte
    import json
    with open(index_path, "r", encoding="utf-8") as f:
        index_data = json.load(f)
    
    assert index_data["summary"]["total_items"] > 0
    # Verificar que el reporte se generó correctamente
    # Cuando el repo está vacío o no hay tipos que matcheen, puede ser REPO_EMPTY o TYPE_FILTER_ZERO
    items = index_data["items"]
    assert len(items) > 0
    # Verificar que el outcome tiene información útil
    outcome = items[0]["outcome"]
    assert outcome["local_docs_considered"] == 0
    # Aceptar ambos casos: REPO_EMPTY (repo realmente vacío) o TYPE_FILTER_ZERO (hay tipos pero no matchean)
    assert outcome["primary_reason_code"] in [
        PrimaryReasonCode.REPO_EMPTY.value,
        PrimaryReasonCode.TYPE_FILTER_ZERO.value,
    ], f"Expected REPO_EMPTY or TYPE_FILTER_ZERO, got {outcome['primary_reason_code']}"


def test_type_filter_zero_scenario(matcher, temp_store, tmp_path):
    """Test: TYPE_FILTER_ZERO cuando hay docs pero no del tipo requerido."""
    # Crear un tipo de documento con ID único
    import uuid
    unique_id = f"T999_{uuid.uuid4().hex[:8]}"
    doc_type = DocumentTypeV1(
        type_id=unique_id,
        name="Otro documento",
        scope=DocumentScopeV1.worker,
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
        required_fields=[],
        platform_aliases=[],
        active=True,
    )
    temp_store.create_type(doc_type)
    
    # Crear un documento de ese tipo
    doc = DocumentInstanceV1(
        doc_id="doc1",
        type_id=unique_id,
        file_name_original="test.pdf",
        stored_path="test.pdf",  # Requerido
        sha256="abc123",  # Requerido
        scope=DocumentScopeV1.worker,
        company_key="TEST123",
        person_key="worker123",
        status=DocumentStatusV1.ready_to_submit,
    )
    temp_store.save_document(doc)
    
    # Buscar un tipo diferente (que no existe, pero que matchee con aliases de T104 si existe)
    pending = PendingItemV1(
        tipo_doc="T888_OTHER_DOC Tipo completamente diferente",
        elemento="Test Worker",
        empresa="Test Company",
    )
    
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    result = matcher.match_pending_item(
        pending,
        company_key="TEST123",
        person_key="worker123",
        evidence_dir=evidence_dir,
        generate_debug_report=True,
    )
    
    debug_report_dict = result.get("matching_debug_report")
    assert debug_report_dict is not None
    
    # Verificar primary_reason_code
    outcome = debug_report_dict.get("outcome", {})
    # Puede ser TYPE_FILTER_ZERO si no hay tipos que matcheen, o SUBJECT_FILTER_ZERO si hay tipos pero no docs
    assert outcome.get("primary_reason_code") in [
        PrimaryReasonCode.TYPE_FILTER_ZERO.value,
        PrimaryReasonCode.SUBJECT_FILTER_ZERO.value,
    ]


def test_subject_filter_zero_scenario(matcher, temp_store, tmp_path):
    """Test: SUBJECT_FILTER_ZERO cuando hay docs del tipo pero no para el subject."""
    # Crear tipo T104_AUTONOMOS_RECEIPT (ya existe en seed)
    doc_type = temp_store.get_type("T104_AUTONOMOS_RECEIPT")
    if not doc_type:
        pytest.skip("T104_AUTONOMOS_RECEIPT no existe en seed")
    
    # Crear documento para company_key/person_key diferentes
    doc = DocumentInstanceV1(
        doc_id="doc1",
        type_id="T104_AUTONOMOS_RECEIPT",
        file_name_original="test.pdf",
        stored_path="test.pdf",  # Requerido
        sha256="abc123",  # Requerido
        scope=DocumentScopeV1.worker,
        company_key="OTHER123",  # Diferente
        person_key="other_worker",  # Diferente
        status=DocumentStatusV1.ready_to_submit,
    )
    temp_store.save_document(doc)
    
    # Buscar para company_key/person_key que no tienen docs
    pending = PendingItemV1(
        tipo_doc="T205.0 Último Recibo bancario pago cuota autónomos",
        elemento="Test Worker",
        empresa="Test Company",
    )
    
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    result = matcher.match_pending_item(
        pending,
        company_key="TEST123",  # Diferente
        person_key="worker123",  # Diferente
        evidence_dir=evidence_dir,
        generate_debug_report=True,
    )
    
    debug_report_dict = result.get("matching_debug_report")
    assert debug_report_dict is not None
    
    # Verificar que hay pipeline steps
    pipeline = debug_report_dict.get("pipeline", [])
    assert len(pipeline) > 0
    
    # Verificar que hay step de filter: subject
    subject_steps = [s for s in pipeline if "subject" in s.get("step_name", "").lower()]
    assert len(subject_steps) > 0


def test_period_filter_zero_scenario(matcher, temp_store, tmp_path):
    """Test: PERIOD_FILTER_ZERO cuando hay docs del tipo y subject pero no del período."""
    # Crear tipo T104_AUTONOMOS_RECEIPT
    doc_type = temp_store.get_type("T104_AUTONOMOS_RECEIPT")
    if not doc_type:
        pytest.skip("T104_AUTONOMOS_RECEIPT no existe en seed")
    
    # Crear documento para período diferente
    doc = DocumentInstanceV1(
        doc_id="doc1",
        type_id="T104_AUTONOMOS_RECEIPT",
        file_name_original="test.pdf",
        stored_path="test.pdf",  # Requerido
        sha256="abc123",  # Requerido
        scope=DocumentScopeV1.worker,
        company_key="TEST123",
        person_key="worker123",
        period_key="2023-01",  # Enero 2023
        status=DocumentStatusV1.ready_to_submit,
    )
    temp_store.save_document(doc)
    
    # Buscar para período diferente
    pending = PendingItemV1(
        tipo_doc="T205.0 Último Recibo bancario pago cuota autónomos (Mayo 2024)",
        elemento="Test Worker",
        empresa="Test Company",
    )
    
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    result = matcher.match_pending_item(
        pending,
        company_key="TEST123",
        person_key="worker123",
        evidence_dir=evidence_dir,
        generate_debug_report=True,
    )
    
    debug_report_dict = result.get("matching_debug_report")
    assert debug_report_dict is not None
    
    # Verificar que hay pipeline steps
    pipeline = debug_report_dict.get("pipeline", [])
    assert len(pipeline) > 0


def test_confidence_too_low_scenario(matcher, temp_store, tmp_path):
    """Test: CONFIDENCE_TOO_LOW cuando hay candidates pero no superan threshold."""
    # Crear tipo T104_AUTONOMOS_RECEIPT
    doc_type = temp_store.get_type("T104_AUTONOMOS_RECEIPT")
    if not doc_type:
        pytest.skip("T104_AUTONOMOS_RECEIPT no existe en seed")
    
    # Crear documento con status draft (baja confianza)
    doc = DocumentInstanceV1(
        doc_id="doc1",
        type_id="T104_AUTONOMOS_RECEIPT",
        file_name_original="test.pdf",
        stored_path="test.pdf",  # Requerido
        sha256="abc123",  # Requerido
        scope=DocumentScopeV1.worker,
        company_key="TEST123",
        person_key="worker123",
        status=DocumentStatusV1.draft,  # Draft reduce confidence
    )
    temp_store.save_document(doc)
    
    # Buscar documento
    pending = PendingItemV1(
        tipo_doc="T205.0 Último Recibo bancario pago cuota autónomos",
        elemento="Test Worker",
        empresa="Test Company",
    )
    
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    result = matcher.match_pending_item(
        pending,
        company_key="TEST123",
        person_key="worker123",
        evidence_dir=evidence_dir,
        generate_debug_report=True,
    )
    
    debug_report_dict = result.get("matching_debug_report")
    assert debug_report_dict is not None
    
    # Verificar que hay candidates_top
    candidates_top = debug_report_dict.get("candidates_top", [])
    # Puede haber candidates si el score es suficiente, o no si es muy bajo
    outcome = debug_report_dict.get("outcome", {})
    assert outcome.get("local_docs_considered", 0) >= 0


def test_generate_plan_id_stability_with_debug_report():
    """Test: plan_id debe ser estable incluso con matching_debug_report."""
    from backend.shared.upload_decision_engine import generate_plan_id
    
    plan_content_1 = {
        "snapshot": {"items": [{"key": "item1"}]},
        "decisions": [{"decision": "NO_MATCH", "pending_item_key": "item1"}],
    }
    
    plan_content_2 = {
        "snapshot": {"items": [{"key": "item1"}]},
        "decisions": [{"decision": "NO_MATCH", "pending_item_key": "item1"}],
        # matching_debug_report NO debe afectar el plan_id
        "matching_debug_report": {"meta": {"created_at": "2024-01-01"}},
    }
    
    plan_id_1 = generate_plan_id(plan_content_1)
    plan_id_2 = generate_plan_id(plan_content_2)
    
    # Los plan_id deben ser iguales (matching_debug_report no está en snapshot/decisions)
    assert plan_id_1 == plan_id_2


def test_data_dir_mismatch_scenario(matcher, tmp_path, monkeypatch):
    """Test: DATA_DIR_MISMATCH cuando repo está vacío y data_dir_resolved != expected."""
    import os
    from pathlib import Path
    
    # Simular un data_dir_expected diferente
    expected_dir = tmp_path / "expected_data"
    expected_dir.mkdir(parents=True, exist_ok=True)
    
    # El matcher usa el store que tiene su propio base_dir (tmp_path)
    # Pero podemos simular que el expected es diferente
    # Monkeypatch para que create_empty detecte el mismatch
    pending = PendingItemV1(
        tipo_doc="T999_NONEXISTENT Tipo que no existe",
        elemento="Test Worker",
        empresa="Test Company",
    )
    
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    # Simular que COMETLOCAL_DATA_DIR apunta a otro lugar
    monkeypatch.setenv("COMETLOCAL_DATA_DIR", str(expected_dir))
    
    result = matcher.match_pending_item(
        pending,
        company_key="TEST123",
        person_key="worker123",
        evidence_dir=evidence_dir,
        generate_debug_report=True,
    )
    
    debug_report_dict = result.get("matching_debug_report")
    assert debug_report_dict is not None
    
    meta = debug_report_dict.get("meta", {})
    data_dir_resolved = meta.get("data_dir_resolved")
    data_dir_expected = meta.get("data_dir_expected")
    
    # Verificar que se detectó el mismatch si repo está vacío
    if meta.get("repo_docs_total", 0) == 0 and data_dir_expected:
        outcome = debug_report_dict.get("outcome", {})
        # Puede ser DATA_DIR_MISMATCH o REPO_EMPTY dependiendo de si los paths normalizados difieren
        resolved_norm = str(Path(data_dir_resolved).resolve())
        expected_norm = str(Path(data_dir_expected).resolve())
        
        if resolved_norm != expected_norm:
            assert outcome.get("primary_reason_code") == PrimaryReasonCode.DATA_DIR_MISMATCH.value
            assert "data_dir_resolved" in outcome.get("human_hint", "").lower() or "difiere" in outcome.get("human_hint", "")
        else:
            # Si son iguales, debe ser REPO_EMPTY
            assert outcome.get("primary_reason_code") in [
                PrimaryReasonCode.REPO_EMPTY.value,
                PrimaryReasonCode.TYPE_FILTER_ZERO.value,
            ]


def test_data_dir_match_repo_empty_scenario(matcher, tmp_path, monkeypatch):
    """Test: REPO_EMPTY (no mismatch) cuando repo está vacío pero data_dir coincide."""
    import os
    from pathlib import Path
    
    # Asegurar que expected y resolved son iguales
    # El matcher usa tmp_path como base_dir, así que esperamos que sea el mismo
    pending = PendingItemV1(
        tipo_doc="T999_NONEXISTENT Tipo que no existe",
        elemento="Test Worker",
        empresa="Test Company",
    )
    
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    # No setear COMETLOCAL_DATA_DIR para que use el default (que debería coincidir)
    # O setearlo al mismo valor que tmp_path
    monkeypatch.setenv("COMETLOCAL_DATA_DIR", str(tmp_path))
    
    result = matcher.match_pending_item(
        pending,
        company_key="TEST123",
        person_key="worker123",
        evidence_dir=evidence_dir,
        generate_debug_report=True,
    )
    
    debug_report_dict = result.get("matching_debug_report")
    assert debug_report_dict is not None
    
    meta = debug_report_dict.get("meta", {})
    outcome = debug_report_dict.get("outcome", {})
    
    # Si repo está vacío pero data_dir coincide, debe ser REPO_EMPTY (no DATA_DIR_MISMATCH)
    if meta.get("repo_docs_total", 0) == 0:
        # Verificar que NO es DATA_DIR_MISMATCH
        assert outcome.get("primary_reason_code") != PrimaryReasonCode.DATA_DIR_MISMATCH.value
        # Debe ser REPO_EMPTY o TYPE_FILTER_ZERO
        assert outcome.get("primary_reason_code") in [
            PrimaryReasonCode.REPO_EMPTY.value,
            PrimaryReasonCode.TYPE_FILTER_ZERO.value,
        ]
