"""
Tests para el analizador CAE OCR (v3.3.0).
"""

import pytest
from backend.agents.cae_ocr_analyzer import extract_cae_status_from_text


def test_extract_cae_status_vigente():
    """Test que detecta estado vigente/apto."""
    text = "El trabajador está apto y el certificado está vigente hasta el 01/02/2025."
    
    result = extract_cae_status_from_text(text)
    
    assert result["status"] == "vigente"
    assert len(result["expiry_dates"]) > 0
    assert "01/02/2025" in result["raw_dates"] or "2025-02-01" in result["expiry_dates"]


def test_extract_cae_status_caducado():
    """Test que detecta estado caducado."""
    text = "El certificado ha caducado el 15/01/2024. Está vencido y fuera de plazo."
    
    result = extract_cae_status_from_text(text)
    
    assert result["status"] == "caducado"
    assert len(result["evidence_snippets"]) > 0


def test_extract_cae_status_pendiente():
    """Test que detecta estado pendiente."""
    text = "El documento está pendiente de revisión. En proceso de tramitación."
    
    result = extract_cae_status_from_text(text)
    
    assert result["status"] == "pendiente"
    assert len(result["evidence_snippets"]) > 0


def test_extract_cae_status_no_apto():
    """Test que detecta estado no apto."""
    text = "El trabajador no está apto. Certificado rechazado."
    
    result = extract_cae_status_from_text(text)
    
    assert result["status"] == "no_apto"
    assert len(result["evidence_snippets"]) > 0


def test_extract_cae_status_unknown():
    """Test que devuelve desconocido cuando no hay indicadores claros."""
    text = "Esta es una página normal sin información de estado CAE."
    
    result = extract_cae_status_from_text(text)
    
    assert result["status"] == "desconocido"
    assert len(result["expiry_dates"]) == 0
    assert len(result["evidence_snippets"]) == 0


def test_extract_cae_status_extracts_dates():
    """Test que extrae fechas en múltiples formatos."""
    text = """
    Certificado vigente hasta 31/12/2025.
    También hay otra fecha: 2024-06-15.
    Y otra más: 15-06-2024.
    """
    
    result = extract_cae_status_from_text(text)
    
    assert len(result["raw_dates"]) >= 2
    assert len(result["expiry_dates"]) > 0


def test_extract_cae_status_empty_text():
    """Test que maneja texto vacío correctamente."""
    result = extract_cae_status_from_text("")
    
    assert result["status"] == "desconocido"
    assert len(result["expiry_dates"]) == 0
    assert len(result["raw_dates"]) == 0
    assert len(result["evidence_snippets"]) == 0

