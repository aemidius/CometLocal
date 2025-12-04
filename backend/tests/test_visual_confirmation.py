"""
Tests para confirmación visual de acciones (v3.2.0).
"""

import pytest
from backend.shared.models import BrowserObservation, VisualActionResult
from backend.agents.agent_runner import _verify_action_visually


def test_verify_action_visually_success():
    """Test que _verify_action_visually detecta confirmación cuando encuentra keywords."""
    observation = BrowserObservation(
        url="https://example.com",
        title="Test Page",
        visible_text_excerpt="El documento ha sido guardado correctamente en el sistema.",
        clickable_texts=[],
        input_hints=[],
    )
    
    result = _verify_action_visually(
        observation=observation,
        expected_effect="Confirmar que se guardó el documento",
        keywords=["guardado", "guardado correctamente", "saved", "saved successfully"],
    )
    
    assert result.confirmed is True
    assert result.confidence > 0.5
    assert result.evidence is not None
    assert "guardado" in result.evidence.lower()


def test_verify_action_visually_failure():
    """Test que _verify_action_visually no confirma cuando no encuentra keywords."""
    observation = BrowserObservation(
        url="https://example.com",
        title="Test Page",
        visible_text_excerpt="Esta es una página normal sin mensajes de confirmación.",
        clickable_texts=[],
        input_hints=[],
    )
    
    result = _verify_action_visually(
        observation=observation,
        expected_effect="Confirmar que se guardó el documento",
        keywords=["guardado", "guardado correctamente", "saved"],
    )
    
    assert result.confirmed is False
    assert result.confidence < 0.5
    assert result.evidence is not None


def test_verify_action_visually_multiple_keywords():
    """Test que múltiples keywords aumentan la confianza."""
    observation = BrowserObservation(
        url="https://example.com",
        title="Test Page",
        visible_text_excerpt="El archivo ha sido guardado correctamente. Cambios guardados con éxito.",
        clickable_texts=[],
        input_hints=[],
    )
    
    result = _verify_action_visually(
        observation=observation,
        expected_effect="Confirmar que se guardó",
        keywords=["guardado", "guardado correctamente", "cambios guardados", "saved"],
    )
    
    assert result.confirmed is True
    # Con múltiples matches, la confianza debería ser mayor
    assert result.confidence >= 0.7


def test_verify_action_visually_no_text():
    """Test que _verify_action_visually maneja correctamente observaciones sin texto."""
    observation = BrowserObservation(
        url="https://example.com",
        title="Test Page",
        visible_text_excerpt="",
        clickable_texts=[],
        input_hints=[],
    )
    
    result = _verify_action_visually(
        observation=observation,
        expected_effect="Confirmar acción",
        keywords=["guardado", "saved"],
    )
    
    assert result.confirmed is False
    assert result.confidence < 0.5
    assert "texto disponible" in result.evidence.lower() or "no se encontró" in result.evidence.lower()


def test_visual_action_result_model():
    """Test que VisualActionResult se serializa correctamente."""
    result = VisualActionResult(
        action_type="click",
        expected_effect="Confirmar que se guardó",
        confirmed=True,
        confidence=0.85,
        evidence="El documento ha sido guardado correctamente",
    )
    
    assert result.action_type == "click"
    assert result.confirmed is True
    assert result.confidence == 0.85
    assert result.evidence is not None
    
    # Test serialización a dict
    result_dict = result.model_dump()
    assert result_dict["action_type"] == "click"
    assert result_dict["confirmed"] is True
    assert result_dict["confidence"] == 0.85

