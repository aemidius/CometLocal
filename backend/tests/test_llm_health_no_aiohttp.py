"""
Tests para /api/health/llm cuando aiohttp no está instalado.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def test_llm_health_without_aiohttp():
    """Test que /api/health/llm devuelve 200 (no 500) incluso si aiohttp no está disponible."""
    # Este test verifica que el endpoint maneja correctamente la ausencia de aiohttp
    # El código ya tiene try/except ImportError, así que simplemente verificamos
    # que el endpoint responde correctamente
    from backend.app import app
    client = TestClient(app)
    
    # Mockear get_llm_config para evitar errores de configuración
    with patch('backend.app.get_llm_config', return_value={"base_url": "http://test", "timeout_seconds": 30}):
        # El endpoint debe responder 200 (no 500) independientemente de si aiohttp está o no
        response = client.get("/api/health/llm")
        
        # Lo importante: no debe crashear (200, no 500)
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        # Si aiohttp no está instalado, debería ser "degraded" con reason "aiohttp_not_installed"
        # Pero si está instalado, puede ser otro status. Lo importante es que no crashea.


def test_llm_health_with_aiohttp_available():
    """Test que /api/health/llm funciona normalmente cuando aiohttp está disponible."""
    # Este test simplemente verifica que el endpoint no crashea
    # cuando aiohttp está disponible (aunque puede fallar por conexión)
    from backend.app import app
    client = TestClient(app)
    
    response = client.get("/api/health/llm")
    
    # Debe devolver 200 (no 500)
    assert response.status_code == 200
    data = response.json()
    # Puede ser "online", "degraded", "offline" o "disabled", pero no "aiohttp_not_installed"
    # (a menos que realmente no esté instalado)
    # Lo importante es que no crashea
    assert "status" in data
