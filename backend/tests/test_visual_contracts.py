"""
Tests para VisualContracts.

v3.6.0: Tests para la construcción de expectativas visuales y evaluación de contratos.
"""

import pytest
from backend.shared.models import VisualExpectation, VisualFlowState, VisualContractResult
from backend.agents.visual_contracts import build_visual_expectation_for_action, evaluate_visual_contract


def test_build_visual_expectation_for_upload():
    """build_visual_expectation_for_action debe crear expectativa para upload_file."""
    expectation = build_visual_expectation_for_action(
        action_type="upload_file",
        visual_flow_state_before=None,
    )
    
    assert expectation is not None
    assert expectation.expected_stage == "file_selected"
    assert "file_selected" in expectation.allowed_stages
    assert "uploaded" in expectation.allowed_stages
    assert expectation.severity == "normal"
    assert expectation.description is not None


def test_build_visual_expectation_for_click_after_upload():
    """build_visual_expectation_for_action debe crear expectativa para click después de upload."""
    previous_state = VisualFlowState(
        stage="file_selected",
        last_action="upload_file",
        pending_actions=["click_save_button"],
        notes="Archivo seleccionado",
        confidence=0.8,
    )
    
    expectation = build_visual_expectation_for_action(
        action_type="click",
        visual_flow_state_before=previous_state,
    )
    
    assert expectation is not None
    assert expectation.expected_stage == "saved"
    assert "saved" in expectation.allowed_stages
    assert "confirmed" in expectation.allowed_stages
    assert expectation.severity == "critical"


def test_build_visual_expectation_for_click_after_saved():
    """build_visual_expectation_for_action debe crear expectativa para click después de saved."""
    previous_state = VisualFlowState(
        stage="saved",
        last_action="click",
        pending_actions=["click_confirm_button"],
        notes="Cambios guardados",
        confidence=0.85,
    )
    
    expectation = build_visual_expectation_for_action(
        action_type="click",
        visual_flow_state_before=previous_state,
    )
    
    assert expectation is not None
    assert expectation.expected_stage == "confirmed"
    assert expectation.allowed_stages == ["confirmed"]
    assert expectation.severity == "critical"


def test_build_visual_expectation_returns_none_for_irrelevant_action():
    """build_visual_expectation_for_action debe devolver None para acciones no relevantes."""
    expectation = build_visual_expectation_for_action(
        action_type="open_url",
        visual_flow_state_before=None,
    )
    
    assert expectation is None


def test_evaluate_contract_match():
    """evaluate_visual_contract debe devolver 'match' cuando el estado coincide."""
    expectation = VisualExpectation(
        expected_stage="saved",
        allowed_stages=["saved", "confirmed"],
        expected_keywords=["guardado"],
        description="Esperamos estado saved",
        severity="critical",
    )
    
    state = VisualFlowState(
        stage="saved",
        last_action="click",
        pending_actions=[],
        notes="Cambios guardados correctamente",
        confidence=0.9,
    )
    
    result = evaluate_visual_contract(expectation, state)
    
    assert result.outcome == "match"
    assert result.expected_stage == "saved"
    assert result.actual_stage == "saved"
    assert result.severity == "critical"


def test_evaluate_contract_violation_on_error_stage():
    """evaluate_visual_contract debe devolver 'violation' cuando el estado es error."""
    expectation = VisualExpectation(
        expected_stage="saved",
        allowed_stages=["saved"],
        expected_keywords=[],
        description="Esperamos estado saved",
        severity="critical",
    )
    
    state = VisualFlowState(
        stage="error",
        last_action="click",
        pending_actions=[],
        notes="Error al guardar",
        confidence=0.8,
    )
    
    result = evaluate_visual_contract(expectation, state)
    
    assert result.outcome == "violation"
    assert result.actual_stage == "error"
    assert "error" in result.description.lower()


def test_evaluate_contract_mismatch():
    """evaluate_visual_contract debe devolver 'mismatch' cuando el estado no coincide."""
    expectation = VisualExpectation(
        expected_stage="saved",
        allowed_stages=["saved"],
        expected_keywords=[],
        description="Esperamos estado saved",
        severity="critical",
    )
    
    state = VisualFlowState(
        stage="file_selected",
        last_action="click",
        pending_actions=["click_save_button"],
        notes="Archivo seleccionado",
        confidence=0.7,
    )
    
    result = evaluate_visual_contract(expectation, state)
    
    assert result.outcome == "mismatch"
    assert result.expected_stage == "saved"
    assert result.actual_stage == "file_selected"


def test_evaluate_contract_unknown_when_no_state():
    """evaluate_visual_contract debe devolver 'unknown' cuando no hay estado."""
    expectation = VisualExpectation(
        expected_stage="saved",
        allowed_stages=["saved"],
        expected_keywords=[],
        description="Esperamos estado saved",
        severity="critical",
    )
    
    result = evaluate_visual_contract(expectation, None)
    
    assert result.outcome == "unknown"
    assert result.actual_stage is None


def test_evaluate_contract_match_with_allowed_stages():
    """evaluate_visual_contract debe devolver 'match' si el estado está en allowed_stages."""
    expectation = VisualExpectation(
        expected_stage="saved",
        allowed_stages=["saved", "confirmed"],
        expected_keywords=[],
        description="Esperamos saved o confirmed",
        severity="critical",
    )
    
    state = VisualFlowState(
        stage="confirmed",
        last_action="click",
        pending_actions=[],
        notes="Operación confirmada",
        confidence=0.9,
    )
    
    result = evaluate_visual_contract(expectation, state)
    
    assert result.outcome == "match"
    assert result.actual_stage == "confirmed"


def test_evaluate_contract_match_when_state_ahead():
    """evaluate_visual_contract debe devolver 'match' si el estado está más adelante que el esperado."""
    expectation = VisualExpectation(
        expected_stage="file_selected",
        allowed_stages=["file_selected", "uploaded", "saved", "confirmed"],
        expected_keywords=[],
        description="Esperamos file_selected o más adelante",
        severity="normal",
    )
    
    state = VisualFlowState(
        stage="saved",
        last_action="click",
        pending_actions=[],
        notes="Cambios guardados",
        confidence=0.9,
    )
    
    result = evaluate_visual_contract(expectation, state)
    
    # Debe ser match porque saved está en allowed_stages y está más adelante
    assert result.outcome == "match"















