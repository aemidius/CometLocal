"""
Unit tests para upload_decision_engine.

SPRINT C2.17: Valida que las decisiones se toman correctamente.
"""
import pytest
from backend.shared.upload_decision_engine import (
    UploadDecision,
    make_upload_decision,
    calculate_confidence,
    apply_decisions_to_plan,
    generate_plan_id,
)


def test_calculate_confidence_no_match():
    """Test: confidence es 0.0 si no hay match."""
    confidence = calculate_confidence(match_result={}, has_file=False)
    assert confidence == 0.0


def test_calculate_confidence_with_match_and_file():
    """Test: confidence es alta si hay match y archivo."""
    match_result = {"best_doc": {"doc_id": "doc1"}, "confidence": 0.9}
    confidence = calculate_confidence(match_result=match_result, has_file=True)
    assert confidence > 0.8


def test_calculate_confidence_with_ambiguity():
    """Test: confidence se penaliza con ambigüedad."""
    match_result = {"best_doc": {"doc_id": "doc1"}, "confidence": 0.9}
    confidence = calculate_confidence(match_result=match_result, has_file=True, has_ambiguity=True)
    assert confidence < 0.9  # Penalizado


def test_make_upload_decision_no_match():
    """Test: NO_MATCH si no hay match."""
    result = make_upload_decision(
        pending_item={"tipo_doc": "Test", "elemento": "Test", "empresa": "Test"},
        match_result={},
        company_key="TEST",
        base_dir="data",
    )
    assert result["decision"] == UploadDecision.NO_MATCH.value
    assert result["confidence"] == 0.0


def test_make_upload_decision_user_override():
    """Test: SKIPPED si hay override manual."""
    result = make_upload_decision(
        pending_item={"tipo_doc": "Test", "elemento": "Test", "empresa": "Test"},
        match_result={"best_doc": {"doc_id": "doc1"}, "confidence": 0.9},
        company_key="TEST",
        user_override=UploadDecision.SKIPPED,
        base_dir="data",
    )
    assert result["decision"] == UploadDecision.SKIPPED.value
    assert result["confidence"] == 1.0


def test_generate_plan_id_stable():
    """Test: plan_id es estable (mismo contenido = mismo ID)."""
    plan_content = {
        "snapshot": {"items": [{"id": 1}]},
        "decisions": [{"decision": "AUTO_UPLOAD"}],
    }
    plan_id_1 = generate_plan_id(plan_content)
    plan_id_2 = generate_plan_id(plan_content)
    assert plan_id_1 == plan_id_2
    assert plan_id_1.startswith("plan_")


def test_generate_plan_id_different():
    """Test: plan_id es diferente si el contenido cambia."""
    plan_content_1 = {
        "snapshot": {"items": [{"id": 1}]},
        "decisions": [{"decision": "AUTO_UPLOAD"}],
    }
    plan_content_2 = {
        "snapshot": {"items": [{"id": 2}]},
        "decisions": [{"decision": "AUTO_UPLOAD"}],
    }
    plan_id_1 = generate_plan_id(plan_content_1)
    plan_id_2 = generate_plan_id(plan_content_2)
    assert plan_id_1 != plan_id_2
