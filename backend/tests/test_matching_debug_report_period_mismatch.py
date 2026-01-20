"""
SPRINT C2.34: Unit tests para matching_debug_report - caso PERIOD_MISMATCH
"""

import pytest
from pathlib import Path
from backend.repository.document_matcher_v1 import DocumentMatcherV1, PendingItemV1
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.repository.matching_debug_codes_v1 import PERIOD_MISMATCH


def test_build_matching_debug_report_period_mismatch(tmp_path):
    """Test que verifica que se genera report cuando hay mismatch de periodo."""
    # Setup: crear store con documentos pero sin el periodo correcto
    base_dir = tmp_path / "data"
    base_dir.mkdir()
    store = DocumentRepositoryStoreV1(base_dir=str(base_dir))
    matcher = DocumentMatcherV1(store, base_dir=str(base_dir))
    
    # Crear pending item con periodo específico
    pending = PendingItemV1(
        tipo_doc="T104.0",
        elemento="Recibo autónomos",
        empresa="Test Company",
        trabajador=None,
    )
    
    # Context con period_key
    context = {
        "company_key": "TEST_COMPANY",
        "person_key": None,
        "platform_key": "egestiona",
        "period_key": "2024-01",  # Periodo buscado
    }
    
    # Match result con NO_MATCH
    match_result = {
        "decision": "NO_MATCH",
        "best_doc": None,
        "confidence": 0.0,
    }
    
    # Stage counts: hay docs del tipo y empresa, pero no del periodo
    stage_counts = {
        "local_docs_considered": 10,
        "local_docs_after_type": 5,  # Hay docs del tipo
        "local_docs_after_scope": 5,
        "local_docs_after_company": 3,  # Hay docs de la empresa
        "local_docs_after_person": 0,
        "local_docs_after_period": 0,  # Pero no del periodo
        "local_docs_after_validity": 0,
    }
    
    # Type lookup info (tipo encontrado y activo)
    type_lookup_info = {
        "type_id": "T104_AUTONOMOS_RECEIPT",
        "found": True,
        "active": True,
        "scope": "company",
    }
    
    alias_info = {
        "alias_received": "T104.0 Recibo autónomos",
        "matched": True,
    }
    
    # Generar report
    report = matcher.build_matching_debug_report(
        pending=pending,
        context=context,
        repo_docs=[],
        match_result=match_result,
        stage_counts=stage_counts,
        type_lookup_info=type_lookup_info,
        alias_info=alias_info,
    )
    
    # Verificaciones
    assert report is not None
    assert report["decision"] == "NO_MATCH"
    assert report["filters_applied"]["period_key"] == "2024-01"
    
    # Verificar que hay al menos un reason con código PERIOD_MISMATCH
    period_mismatch_reasons = [r for r in report["reasons"] if r["code"] == PERIOD_MISMATCH]
    assert len(period_mismatch_reasons) > 0
    
    # Verificar que el reason tiene hint y meta
    period_reason = period_mismatch_reasons[0]
    assert "hint" in period_reason
    assert "meta" in period_reason
    assert period_reason["meta"]["period_key_searched"] == "2024-01"
    
    # Verificar counters
    assert report["counters"]["local_docs_after_company"] == 3
    assert report["counters"]["local_docs_after_period"] == 0


def test_build_matching_debug_report_review_required(tmp_path):
    """Test que verifica que se genera report cuando decision es REVIEW_REQUIRED."""
    base_dir = tmp_path / "data"
    base_dir.mkdir()
    store = DocumentRepositoryStoreV1(base_dir=str(base_dir))
    matcher = DocumentMatcherV1(store, base_dir=str(base_dir))
    
    pending = PendingItemV1(
        tipo_doc="T104.0",
        elemento="Recibo autónomos",
        empresa="Test Company",
    )
    
    context = {
        "company_key": "TEST_COMPANY",
        "person_key": None,
        "platform_key": "egestiona",
        "period_key": None,
    }
    
    # Match result con REVIEW_REQUIRED
    match_result = {
        "decision": "REVIEW_REQUIRED",
        "best_doc": None,
        "confidence": 0.6,
    }
    
    stage_counts = {
        "local_docs_considered": 5,
        "local_docs_after_type": 3,
        "local_docs_after_scope": 3,
        "local_docs_after_company": 2,
        "local_docs_after_person": 0,
        "local_docs_after_period": 2,
        "local_docs_after_validity": 2,
    }
    
    type_lookup_info = {
        "type_id": "T104_AUTONOMOS_RECEIPT",
        "found": True,
        "active": True,
        "scope": "company",
    }
    
    report = matcher.build_matching_debug_report(
        pending=pending,
        context=context,
        repo_docs=[],
        match_result=match_result,
        stage_counts=stage_counts,
        type_lookup_info=type_lookup_info,
        alias_info=None,
    )
    
    # Debe generar report para REVIEW_REQUIRED
    assert report is not None
    assert report["decision"] == "REVIEW_REQUIRED"
    assert len(report["reasons"]) >= 1
