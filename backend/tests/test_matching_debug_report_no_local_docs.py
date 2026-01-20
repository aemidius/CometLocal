"""
SPRINT C2.34: Unit tests para matching_debug_report - caso NO_LOCAL_DOCS
"""

import pytest
from pathlib import Path
from backend.repository.document_matcher_v1 import DocumentMatcherV1, PendingItemV1
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.repository.matching_debug_codes_v1 import NO_LOCAL_DOCS


def test_build_matching_debug_report_no_local_docs(tmp_path):
    """Test que verifica que se genera report cuando no hay documentos locales."""
    # Setup: crear store vacío
    base_dir = tmp_path / "data"
    base_dir.mkdir()
    store = DocumentRepositoryStoreV1(base_dir=str(base_dir))
    matcher = DocumentMatcherV1(store, base_dir=str(base_dir))
    
    # Crear pending item
    pending = PendingItemV1(
        tipo_doc="T104.0",
        elemento="Recibo autónomos",
        empresa="Test Company",
        trabajador=None,
    )
    
    # Context
    context = {
        "company_key": "TEST_COMPANY",
        "person_key": None,
        "platform_key": "egestiona",
        "period_key": None,
    }
    
    # Match result con NO_MATCH
    match_result = {
        "decision": "NO_MATCH",
        "best_doc": None,
        "confidence": 0.0,
    }
    
    # Stage counts (sin documentos)
    stage_counts = {
        "local_docs_considered": 0,
        "local_docs_after_type": 0,
        "local_docs_after_scope": 0,
        "local_docs_after_company": 0,
        "local_docs_after_person": 0,
        "local_docs_after_period": 0,
        "local_docs_after_validity": 0,
    }
    
    # Type lookup info (tipo no encontrado)
    type_lookup_info = {
        "type_id": None,
        "found": False,
        "active": False,
        "scope": None,
    }
    
    alias_info = {
        "alias_received": "T104.0 Recibo autónomos",
        "matched": False,
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
    assert report["pending_id"] is not None
    assert "filters_applied" in report
    assert "reasons" in report
    assert len(report["reasons"]) >= 1
    
    # Verificar que hay al menos un reason con código NO_LOCAL_DOCS
    no_local_docs_reasons = [r for r in report["reasons"] if r["code"] == NO_LOCAL_DOCS]
    assert len(no_local_docs_reasons) > 0
    
    # Verificar counters
    assert "counters" in report
    assert report["counters"]["local_docs_considered"] == 0
    assert report["counters"]["local_docs_after_type"] == 0
    
    # Verificar orden determinista (reasons ordenados por code)
    reason_codes = [r["code"] for r in report["reasons"]]
    assert reason_codes == sorted(reason_codes)


def test_build_matching_debug_report_not_applicable_auto_upload(tmp_path):
    """Test que verifica que NO se genera report cuando decision es AUTO_UPLOAD."""
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
    
    # Match result con AUTO_UPLOAD (no debe generar report)
    match_result = {
        "decision": "AUTO_UPLOAD",
        "best_doc": {"doc_id": "test_doc"},
        "confidence": 0.9,
    }
    
    stage_counts = {
        "local_docs_considered": 1,
        "local_docs_after_type": 1,
        "local_docs_after_scope": 1,
        "local_docs_after_company": 1,
        "local_docs_after_person": 0,
        "local_docs_after_period": 1,
        "local_docs_after_validity": 1,
    }
    
    report = matcher.build_matching_debug_report(
        pending=pending,
        context=context,
        repo_docs=[],
        match_result=match_result,
        stage_counts=stage_counts,
        type_lookup_info=None,
        alias_info=None,
    )
    
    # No debe generar report para AUTO_UPLOAD
    assert report is None
