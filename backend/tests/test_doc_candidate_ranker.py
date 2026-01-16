"""
Tests para el ranker de candidatos de documentos.
"""

import pytest
from datetime import datetime, date, timedelta
from backend.cae.doc_candidate_ranker_v1 import rank_candidates, get_best_candidate


def test_best_candidate_exact_match():
    """Test que el mejor candidato es el que tiene coincidencia exacta en tipo, sujeto y período."""
    candidates = [
        {
            "doc_id": "doc-exact",
            "type_id": "TEST_TYPE",
            "scope": "worker",
            "company_key": "COMPANY1",
            "person_key": "PERSON1",
            "period_key": "2025-01",
            "status": "reviewed",
            "updated_at": "2025-01-15T10:00:00",
        },
        {
            "doc_id": "doc-partial",
            "type_id": "TEST_TYPE",
            "scope": "worker",
            "company_key": "COMPANY1",
            "person_key": "PERSON1",
            "period_key": "2025-02",  # Período distinto
            "status": "draft",
            "updated_at": "2025-01-10T10:00:00",
        },
    ]
    
    best_doc_id, best_reason = get_best_candidate(
        candidates=candidates,
        target_type_id="TEST_TYPE",
        target_scope="worker",
        target_company_key="COMPANY1",
        target_person_key="PERSON1",
        target_period_key="2025-01",
    )
    
    assert best_doc_id == "doc-exact"
    assert "Coincide tipo" in best_reason
    assert "Coincide trabajador" in best_reason
    assert "Coincide período" in best_reason


def test_best_candidate_fallback_period_penalty():
    """Test que cuando no hay coincidencia exacta de período, se selecciona el mejor disponible."""
    candidates = [
        {
            "doc_id": "doc-old-period",
            "type_id": "TEST_TYPE",
            "scope": "worker",
            "company_key": "COMPANY1",
            "person_key": "PERSON1",
            "period_key": "2024-12",  # Período distinto
            "status": "reviewed",
            "updated_at": "2024-12-15T10:00:00",
        },
        {
            "doc_id": "doc-newer-period",
            "type_id": "TEST_TYPE",
            "scope": "worker",
            "company_key": "COMPANY1",
            "person_key": "PERSON1",
            "period_key": "2025-02",  # Período distinto pero más reciente
            "status": "reviewed",
            "updated_at": "2025-02-10T10:00:00",
        },
    ]
    
    best_doc_id, best_reason = get_best_candidate(
        candidates=candidates,
        target_type_id="TEST_TYPE",
        target_scope="worker",
        target_company_key="COMPANY1",
        target_person_key="PERSON1",
        target_period_key="2025-01",  # No coincide con ninguno
    )
    
    # Debe seleccionar el más reciente (aunque el período no coincida)
    assert best_doc_id == "doc-newer-period"
    assert "Período distinto" in best_reason or "Período distinto" in best_reason


def test_best_candidate_prefers_recent_reviewed():
    """Test que se prefiere un documento revisado y reciente sobre uno draft antiguo."""
    today = date.today()
    recent = (today - timedelta(days=10)).isoformat()
    old = (today - timedelta(days=200)).isoformat()
    
    candidates = [
        {
            "doc_id": "doc-draft-recent",
            "type_id": "TEST_TYPE",
            "scope": "worker",
            "company_key": "COMPANY1",
            "person_key": "PERSON1",
            "period_key": "2025-01",
            "status": "draft",
            "updated_at": recent,
        },
        {
            "doc_id": "doc-reviewed-old",
            "type_id": "TEST_TYPE",
            "scope": "worker",
            "company_key": "COMPANY1",
            "person_key": "PERSON1",
            "period_key": "2025-01",
            "status": "reviewed",
            "updated_at": old,
        },
    ]
    
    best_doc_id, best_reason = get_best_candidate(
        candidates=candidates,
        target_type_id="TEST_TYPE",
        target_scope="worker",
        target_company_key="COMPANY1",
        target_person_key="PERSON1",
        target_period_key="2025-01",
    )
    
    # Debe preferir el revisado aunque sea más antiguo (tiene bonus de status)
    assert best_doc_id == "doc-reviewed-old"
    assert "Estado revisado" in best_reason


def test_best_candidate_no_candidates():
    """Test que devuelve None cuando no hay candidatos."""
    best_doc_id, best_reason = get_best_candidate(
        candidates=[],
        target_type_id="TEST_TYPE",
        target_scope="worker",
        target_company_key="COMPANY1",
        target_person_key="PERSON1",
        target_period_key="2025-01",
    )
    
    assert best_doc_id is None
    assert best_reason is None


def test_best_candidate_type_mismatch():
    """Test que candidatos con tipo distinto no son considerados."""
    candidates = [
        {
            "doc_id": "doc-wrong-type",
            "type_id": "OTHER_TYPE",  # Tipo distinto
            "scope": "worker",
            "company_key": "COMPANY1",
            "person_key": "PERSON1",
            "period_key": "2025-01",
            "status": "reviewed",
            "updated_at": "2025-01-15T10:00:00",
        },
    ]
    
    best_doc_id, best_reason = get_best_candidate(
        candidates=candidates,
        target_type_id="TEST_TYPE",
        target_scope="worker",
        target_company_key="COMPANY1",
        target_person_key="PERSON1",
        target_period_key="2025-01",
    )
    
    # No debe encontrar candidatos válidos (tipo no coincide)
    assert best_doc_id is None
    assert best_reason is None



