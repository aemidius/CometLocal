"""
Tests para el servicio OCR (v3.3.0).
"""

import pytest
from backend.vision.ocr_service import OCRService, OCRResult, OCRBlock
from backend.shared.models import BrowserObservation
from backend.agents.agent_runner import _maybe_enrich_observation_with_ocr


def test_analyze_screenshot_disabled_returns_none():
    """Test que OCRService devuelve None cuando está deshabilitado."""
    import asyncio
    service = OCRService(enabled=False)
    result = asyncio.run(service.analyze_screenshot("fake_path.png"))
    assert result is None


def test_ocr_service_stats():
    """Test que OCRService registra estadísticas correctamente."""
    import asyncio
    service = OCRService(enabled=True)
    asyncio.run(service.analyze_screenshot("fake_path.png"))
    stats = service.get_stats()
    assert stats["calls"] == 1
    assert stats["failures"] == 1


def test_ocr_result_model():
    """Test que OCRResult se serializa correctamente."""
    result = OCRResult(
        full_text="Texto completo",
        blocks=[OCRBlock(text="Bloque 1"), OCRBlock(text="Bloque 2")]
    )
    
    assert result.full_text == "Texto completo"
    assert len(result.blocks) == 2
    
    # Test serialización
    result_dict = result.model_dump()
    assert result_dict["full_text"] == "Texto completo"
    assert len(result_dict["blocks"]) == 2

