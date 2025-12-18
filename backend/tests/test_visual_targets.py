"""
Tests para VisualTargetDetector.

v3.4.0: Tests para la detección de botones visuales usando OCR.
"""

import pytest
from backend.shared.models import BrowserObservation
from backend.vision.visual_targets import VisualTargetDetector, VisualTarget


def test_visual_target_detector_no_ocr_blocks_returns_empty():
    """VisualTargetDetector sin ocr_blocks debe devolver lista vacía."""
    detector = VisualTargetDetector(min_confidence=0.8)
    observation = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Some text",
        clickable_texts=[],
        input_hints=[],
    )
    
    targets = detector.find_targets(observation)
    assert targets == []


def test_visual_target_detector_detects_guardar_button():
    """VisualTargetDetector debe detectar botón 'guardar' con alta confianza."""
    detector = VisualTargetDetector(min_confidence=0.8)
    observation = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Some text",
        clickable_texts=[],
        input_hints=[],
        ocr_blocks=[
            {"text": "Guardar cambios", "x": 100, "y": 200, "width": 150, "height": 30},
        ],
    )
    
    targets = detector.find_targets(observation)
    assert len(targets) > 0
    
    guardar_targets = [t for t in targets if t.label == "guardar"]
    assert len(guardar_targets) > 0
    
    guardar_target = guardar_targets[0]
    assert guardar_target.label == "guardar"
    assert guardar_target.confidence >= 0.8
    assert guardar_target.x == 175  # 100 + 150/2 (centro)
    assert guardar_target.y == 215  # 200 + 30/2 (centro)
    assert guardar_target.text == "Guardar cambios"
    assert guardar_target.source == "ocr_block"


def test_visual_target_detector_detects_adjuntar_button():
    """VisualTargetDetector debe detectar botón 'adjuntar'."""
    detector = VisualTargetDetector(min_confidence=0.8)
    observation = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Some text",
        clickable_texts=[],
        input_hints=[],
        ocr_blocks=[
            {"text": "Adjuntar archivo", "x": 50, "y": 100, "width": 120, "height": 25},
        ],
    )
    
    targets = detector.find_targets(observation)
    adjuntar_targets = [t for t in targets if t.label == "adjuntar"]
    assert len(adjuntar_targets) > 0
    
    adjuntar_target = adjuntar_targets[0]
    assert adjuntar_target.label == "adjuntar"
    assert adjuntar_target.confidence >= 0.8
    assert adjuntar_target.x == 110  # 50 + 120/2
    assert adjuntar_target.y == 112  # 100 + 25/2


def test_visual_target_detector_requires_min_confidence():
    """VisualTargetDetector debe filtrar por confianza mínima."""
    detector = VisualTargetDetector(min_confidence=0.95)
    observation = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Some text",
        clickable_texts=[],
        input_hints=[],
        ocr_blocks=[
            {"text": "Texto que contiene guardar pero no es exacto", "x": 100, "y": 200},
        ],
    )
    
    targets = detector.find_targets(observation)
    # El texto parcial debería tener confianza menor que 0.95
    guardar_targets = [t for t in targets if t.label == "guardar"]
    assert len(guardar_targets) == 0  # No debe pasar el filtro de confianza


def test_visual_target_detector_no_coordinates_returns_target_without_xy():
    """VisualTargetDetector debe devolver target sin coordenadas si ocr_blocks no las tienen."""
    detector = VisualTargetDetector(min_confidence=0.8)
    observation = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Some text",
        clickable_texts=[],
        input_hints=[],
        ocr_blocks=[
            {"text": "Confirmar"},
        ],
    )
    
    targets = detector.find_targets(observation)
    confirmar_targets = [t for t in targets if t.label == "confirmar"]
    assert len(confirmar_targets) > 0
    
    confirmar_target = confirmar_targets[0]
    assert confirmar_target.label == "confirmar"
    assert confirmar_target.x is None
    assert confirmar_target.y is None
    assert confirmar_target.confidence >= 0.8


def test_visual_target_detector_multiple_buttons():
    """VisualTargetDetector debe detectar múltiples botones."""
    detector = VisualTargetDetector(min_confidence=0.8)
    observation = BrowserObservation(
        url="http://example.com",
        title="Example",
        visible_text_excerpt="Some text",
        clickable_texts=[],
        input_hints=[],
        ocr_blocks=[
            {"text": "Guardar", "x": 100, "y": 200, "width": 80, "height": 30},
            {"text": "Adjuntar archivo", "x": 200, "y": 200, "width": 120, "height": 30},
            {"text": "Confirmar", "x": 350, "y": 200, "width": 90, "height": 30},
        ],
    )
    
    targets = detector.find_targets(observation)
    assert len(targets) >= 3
    
    labels = {t.label for t in targets}
    assert "guardar" in labels
    assert "adjuntar" in labels
    assert "confirmar" in labels














