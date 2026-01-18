"""
SPRINT C2.19A: Tests para Learning Store.
"""
import pytest
from pathlib import Path
import tempfile
import shutil
import json

from backend.shared.learning_store import (
    LearningStore,
    LearnedHintV1,
    HintStrength,
)
from backend.shared.decision_pack import ManualDecisionAction


@pytest.fixture
def temp_store(tmp_path):
    """Fixture con store temporal."""
    return LearningStore(base_dir=tmp_path)


def test_generate_hint_from_mark_as_match_idempotent(temp_store):
    """Test: Generar hint idempotente (no duplicar si ya existe)."""
    hint1 = LearnedHintV1.create(
        plan_id="plan_abc123",
        decision_pack_id="pack_def456",
        item_fingerprint="fingerprint123",
        type_id_expected="T104_AUTONOMOS_RECEIPT",
        local_doc_id="doc123",
        local_doc_fingerprint="test.pdf:1234",
        subject_key="COMPANY123",
        person_key="PERSON123",
        period_key="2025-01",
        portal_type_label_normalized="recibo ss",
        notes="Test hint",
    )
    
    # Añadir primera vez
    ids1 = temp_store.add_hints([hint1])
    assert len(ids1) == 1
    assert ids1[0] == hint1.hint_id
    
    # Añadir segunda vez (mismo hint_id)
    hint2 = LearnedHintV1.create(
        plan_id="plan_abc123",
        decision_pack_id="pack_def456",
        item_fingerprint="fingerprint123",
        type_id_expected="T104_AUTONOMOS_RECEIPT",
        local_doc_id="doc123",
        local_doc_fingerprint="test.pdf:1234",
        subject_key="COMPANY123",
        person_key="PERSON123",
        period_key="2025-01",
        portal_type_label_normalized="recibo ss",
        notes="Test hint",
    )
    
    # Debe ser idempotente (mismo hint_id)
    assert hint1.hint_id == hint2.hint_id
    
    # Añadir segunda vez
    ids2 = temp_store.add_hints([hint2])
    assert len(ids2) == 0  # No se añade porque ya existe
    
    # Verificar que solo hay uno
    all_hints = temp_store.list_hints()
    assert len(all_hints) == 1


def test_apply_exact_hint_resolves_match(temp_store, tmp_path):
    """Test: Hint EXACT resuelve match (convierte NO_MATCH en AUTO_UPLOAD candidate)."""
    from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
    from backend.repository.document_matcher_v1 import DocumentMatcherV1, PendingItemV1
    from backend.shared.document_repository_v1 import DocumentInstanceV1, DocumentStatusV1, DocumentScopeV1
    
    # Crear store temporal
    doc_store = DocumentRepositoryStoreV1(base_dir=str(tmp_path))
    
    # Crear tipo y documento
    doc_type = doc_store.get_type("T104_AUTONOMOS_RECEIPT")
    if not doc_type:
        pytest.skip("T104_AUTONOMOS_RECEIPT no existe en seed")
    
    doc = DocumentInstanceV1(
        doc_id="doc_hint_test",
        type_id="T104_AUTONOMOS_RECEIPT",
        file_name_original="test_hint.pdf",
        stored_path="test_hint.pdf",
        sha256="hint123",
        scope=DocumentScopeV1.worker,
        company_key="COMPANY123",
        person_key="PERSON123",
        period_key="2025-01",
        status=DocumentStatusV1.reviewed,
    )
    doc_store.save_document(doc)
    
    # Crear hint EXACT
    # Normalizar el tipo_doc para que coincida con lo que se buscará
    from backend.shared.text_normalizer import normalize_text
    tipo_doc_normalized = normalize_text("T104.0 Recibo autónomos")
    
    hint = LearnedHintV1.create(
        plan_id="plan_test",
        decision_pack_id="pack_test",
        item_fingerprint="fingerprint_test",
        type_id_expected="T104_AUTONOMOS_RECEIPT",
        local_doc_id="doc_hint_test",
        local_doc_fingerprint=None,
        subject_key="COMPANY123",
        person_key="PERSON123",
        period_key="2025-01",
        portal_type_label_normalized=tipo_doc_normalized,  # Usar el mismo valor normalizado
        notes="Test exact hint",
    )
    temp_store.add_hints([hint])
    
    # Crear pending que debería matchear con el hint
    # Usar un tipo_doc que matchee con T104_AUTONOMOS_RECEIPT
    # (normalmente sería algo como "T104.0 Recibo autónomos" o similar según aliases)
    pending = PendingItemV1(
        tipo_doc="T104.0 Recibo autónomos",  # Debe matchear con T104_AUTONOMOS_RECEIPT
        elemento="Test Person",
        empresa="Test Company",
    )
    
    # Pasar el mismo base_dir que el store para que LearningStore use el mismo directorio
    matcher = DocumentMatcherV1(store=doc_store, base_dir=str(tmp_path))
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    result = matcher.match_pending_item(
        pending,
        company_key="COMPANY123",
        person_key="PERSON123",
        evidence_dir=evidence_dir,
        generate_debug_report=True,
    )
    
    # Verificar que el hint se aplicó
    debug_report = result.get("matching_debug_report")
    assert debug_report is not None
    
    outcome = debug_report.get("outcome", {})
    applied_hints = outcome.get("applied_hints", [])
    
    # Debe haber un hint aplicado
    assert len(applied_hints) > 0
    hint_applied = applied_hints[0]
    assert hint_applied["hint_id"] == hint.hint_id
    assert hint_applied["effect"] in ["resolved", "boosted"]
    
    # Si se resolvió, debe haber best_doc
    if hint_applied["effect"] == "resolved":
        assert result.get("best_doc") is not None
        assert result.get("best_doc", {}).get("doc_id") == "doc_hint_test"


def test_multiple_hints_no_auto_resolve(temp_store, tmp_path):
    """Test: Múltiples hints solo boost, no resuelven automáticamente."""
    from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
    from backend.repository.document_matcher_v1 import DocumentMatcherV1, PendingItemV1
    from backend.shared.document_repository_v1 import DocumentInstanceV1, DocumentStatusV1, DocumentScopeV1
    
    doc_store = DocumentRepositoryStoreV1(base_dir=str(tmp_path))
    
    # Crear tipo
    doc_type = doc_store.get_type("T104_AUTONOMOS_RECEIPT")
    if not doc_type:
        pytest.skip("T104_AUTONOMOS_RECEIPT no existe en seed")
    
    # Crear 2 documentos
    doc1 = DocumentInstanceV1(
        doc_id="doc1",
        type_id="T104_AUTONOMOS_RECEIPT",
        file_name_original="test1.pdf",
        stored_path="test1.pdf",
        sha256="abc1",
        scope=DocumentScopeV1.worker,
        company_key="COMPANY123",
        person_key="PERSON123",
        status=DocumentStatusV1.reviewed,
    )
    doc_store.save_document(doc1)
    
    doc2 = DocumentInstanceV1(
        doc_id="doc2",
        type_id="T104_AUTONOMOS_RECEIPT",
        file_name_original="test2.pdf",
        stored_path="test2.pdf",
        sha256="abc2",
        scope=DocumentScopeV1.worker,
        company_key="COMPANY123",
        person_key="PERSON123",
        status=DocumentStatusV1.reviewed,
    )
    doc_store.save_document(doc2)
    
    # Crear 2 hints EXACT para el mismo pending
    # Normalizar el tipo_doc para que coincida con lo que se buscará
    from backend.shared.text_normalizer import normalize_text
    tipo_doc_normalized = normalize_text("T104.0 Recibo autónomos")
    
    hint1 = LearnedHintV1.create(
        plan_id="plan_test",
        decision_pack_id="pack_test",
        item_fingerprint="fingerprint_test",
        type_id_expected="T104_AUTONOMOS_RECEIPT",
        local_doc_id="doc1",
        local_doc_fingerprint=None,
        subject_key="COMPANY123",
        person_key="PERSON123",
        period_key=None,
        portal_type_label_normalized=tipo_doc_normalized,  # Usar el mismo valor normalizado
        notes="Hint 1",
    )
    
    hint2 = LearnedHintV1.create(
        plan_id="plan_test",
        decision_pack_id="pack_test",
        item_fingerprint="fingerprint_test",
        type_id_expected="T104_AUTONOMOS_RECEIPT",
        local_doc_id="doc2",
        local_doc_fingerprint=None,
        subject_key="COMPANY123",
        person_key="PERSON123",
        period_key=None,
        portal_type_label_normalized=tipo_doc_normalized,  # Usar el mismo valor normalizado
        notes="Hint 2",
    )
    
    temp_store.add_hints([hint1, hint2])
    
    # Crear pending
    pending = PendingItemV1(
        tipo_doc="T104.0 Recibo autónomos",  # Debe matchear con T104_AUTONOMOS_RECEIPT
        elemento="Test Person",
        empresa="Test Company",
    )
    
    # Pasar el mismo base_dir que el store para que LearningStore use el mismo directorio
    matcher = DocumentMatcherV1(store=doc_store, base_dir=str(tmp_path))
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    result = matcher.match_pending_item(
        pending,
        company_key="COMPANY123",
        person_key="PERSON123",
        evidence_dir=evidence_dir,
        generate_debug_report=True,
    )
    
    # Verificar que se aplicaron hints pero no se resolvió automáticamente
    debug_report = result.get("matching_debug_report")
    assert debug_report is not None
    
    outcome = debug_report.get("outcome", {})
    applied_hints = outcome.get("applied_hints", [])
    
    # Debe haber hints aplicados
    assert len(applied_hints) > 0
    
    # Verificar que el efecto es "boosted" (no "resolved")
    for hint_applied in applied_hints:
        # Si hay múltiples hints, debe ser "boosted" o "ignored", no "resolved"
        assert hint_applied["effect"] in ["boosted", "ignored"]


def test_disable_hint_stops_application(temp_store):
    """Test: Desactivar hint impide su aplicación."""
    hint = LearnedHintV1.create(
        plan_id="plan_test",
        decision_pack_id="pack_test",
        item_fingerprint="fingerprint_test",
        type_id_expected="T104_AUTONOMOS_RECEIPT",
        local_doc_id="doc123",
        local_doc_fingerprint=None,
        subject_key="COMPANY123",
        person_key="PERSON123",
        period_key="2025-01",
        portal_type_label_normalized="recibo ss",
        notes="Test hint",
    )
    
    temp_store.add_hints([hint])
    
    # Verificar que está activo
    hints = temp_store.find_hints(
        platform="egestiona",
        subject_key="COMPANY123",
        person_key="PERSON123",
        period_key="2025-01",
    )
    assert len(hints) == 1
    assert hints[0].hint_id == hint.hint_id
    
    # Desactivar
    temp_store.disable_hint(hint.hint_id)
    
    # Verificar que ya no se encuentra
    hints_after = temp_store.find_hints(
        platform="egestiona",
        subject_key="COMPANY123",
        person_key="PERSON123",
        period_key="2025-01",
    )
    assert len(hints_after) == 0
    
    # Pero debe aparecer si include_disabled=True
    all_hints = temp_store.list_hints(include_disabled=True)
    assert len(all_hints) == 1
    assert all_hints[0].hint_id == hint.hint_id
