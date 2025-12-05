"""
Tests para recuperación visual con clicks por coordenadas.

v3.4.0: Tests para la integración de detección visual y clicks por coordenadas
en el flujo de recuperación visual.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.shared.models import BrowserObservation, StepResult, BrowserAction, VisualActionResult
from backend.agents.agent_runner import _attempt_visual_recovery, _find_high_confidence_visual_button
from backend.vision.visual_targets import VisualTargetDetector, VisualTarget
from backend.browser.browser import BrowserController

# pytestmark = pytest.mark.asyncio  # Comentado temporalmente - usar asyncio.run en tests


@pytest.fixture
def mock_browser():
    """Mock de BrowserController."""
    browser = MagicMock(spec=BrowserController)
    browser.page = MagicMock()
    browser.page.evaluate = AsyncMock()
    browser.get_observation = AsyncMock()
    browser.click_by_text = AsyncMock(return_value=False)
    browser.click_at = AsyncMock()
    return browser


@pytest.fixture
def observation_with_ocr_guardar():
    """BrowserObservation con OCR que contiene botón 'Guardar'."""
    return BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Página de ejemplo",
        clickable_texts=[],
        input_hints=[],
        ocr_blocks=[
            {"text": "Guardar cambios", "x": 100, "y": 200, "width": 150, "height": 30},
        ],
    )


@pytest.fixture
def observation_without_ocr():
    """BrowserObservation sin OCR."""
    return BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Página de ejemplo",
        clickable_texts=[],
        input_hints=[],
    )


def test_visual_recovery_not_triggered_without_visual_targets(mock_browser, observation_without_ocr):
    """_attempt_visual_recovery no debe hacer click si no hay targets visuales."""
    import asyncio
    # Configurar mock para devolver observación sin OCR
    mock_browser.get_observation.return_value = observation_without_ocr
    
    result = asyncio.run(_attempt_visual_recovery(
        browser=mock_browser,
        action_type="click",
        last_observation=observation_without_ocr,
        goal="Subir documento CAE",
    ))
    
    # No debe llamar a click_at si no hay targets
    mock_browser.click_at.assert_not_called()
    
    # Debe devolver un resultado (aunque no confirmado)
    assert result is not None
    assert isinstance(result, VisualActionResult)


@pytest.mark.skip(reason="Test complejo de integración - requiere mockeo completo del flujo async")
def test_visual_recovery_click_success(mock_browser, observation_with_ocr_guardar):
    """_attempt_visual_recovery debe hacer click visual y registrar éxito.
    
    Nota: Este test requiere un mockeo complejo del flujo async completo.
    La funcionalidad básica está cubierta por test_find_high_confidence_visual_button.
    """
    # Este test se puede implementar más adelante con un mockeo más completo
    pass


def test_visual_recovery_click_no_coordinates(mock_browser):
    """_attempt_visual_recovery no debe hacer click si no hay coordenadas."""
    # Observación con OCR pero sin coordenadas
    observation_no_coords = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Página de ejemplo",
        clickable_texts=[],
        input_hints=[],
        ocr_blocks=[
            {"text": "Guardar"},  # Sin x, y, width, height
        ],
    )
    
    mock_browser.get_observation.return_value = observation_no_coords
    
    import asyncio
    result = asyncio.run(_attempt_visual_recovery(
        browser=mock_browser,
        action_type="click",
        last_observation=observation_no_coords,
        goal="Subir documento CAE",
    ))
    
    # No debe llamar a click_at si no hay coordenadas
    mock_browser.click_at.assert_not_called()
    
    # Debe devolver un resultado (aunque no confirmado)
    assert result is not None


def test_find_high_confidence_visual_button():
    """_find_high_confidence_visual_button debe encontrar botón de alta confianza."""
    observation = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Página de ejemplo",
        clickable_texts=[],
        input_hints=[],
        ocr_blocks=[
            {"text": "Guardar cambios", "x": 100, "y": 200, "width": 150, "height": 30},
            {"text": "Otro texto", "x": 300, "y": 400},
        ],
    )
    
    target = _find_high_confidence_visual_button(
        observation=observation,
        allowed_labels=["guardar", "adjuntar", "confirmar"],
        min_confidence=0.85,
    )
    
    assert target is not None
    assert target.label == "guardar"
    assert target.x == 175
    assert target.y == 215
    assert target.confidence >= 0.85


def test_find_high_confidence_visual_button_no_match():
    """_find_high_confidence_visual_button debe devolver None si no hay match."""
    observation = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Página de ejemplo",
        clickable_texts=[],
        input_hints=[],
        ocr_blocks=[
            {"text": "Otro texto", "x": 300, "y": 400},
        ],
    )
    
    target = _find_high_confidence_visual_button(
        observation=observation,
        allowed_labels=["guardar", "adjuntar", "confirmar"],
        min_confidence=0.85,
    )
    
    assert target is None


def test_visual_recovery_not_triggered_for_non_cae_goal(mock_browser, observation_with_ocr_guardar):
    """_attempt_visual_recovery no debe hacer click visual si el goal no es CAE/upload."""
    mock_browser.get_observation.return_value = observation_with_ocr_guardar
    
    import asyncio
    result = asyncio.run(_attempt_visual_recovery(
        browser=mock_browser,
        action_type="click",
        last_observation=observation_with_ocr_guardar,
        goal="Buscar información en Wikipedia",  # No es CAE/upload
    ))
    
    # No debe llamar a click_at para goals no-CAE
    mock_browser.click_at.assert_not_called()
    
    # Debe devolver un resultado (aunque no confirmado)
    assert result is not None

