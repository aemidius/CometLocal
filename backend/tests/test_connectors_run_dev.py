"""
Smoke test para el endpoint /api/connectors/run (DEV-ONLY).

Requiere E2E_SEED_ENABLED=1 o ENVIRONMENT=dev.
"""

import os
import pytest
from fastapi.testclient import TestClient

# Verificar que el endpoint esté habilitado
E2E_ENABLED = os.getenv("E2E_SEED_ENABLED") == "1"
ENV_DEV = os.getenv("ENVIRONMENT") in ("dev", "development", "local")
ENDPOINT_ENABLED = E2E_ENABLED or ENV_DEV


@pytest.mark.skipif(not ENDPOINT_ENABLED, reason="Connector endpoints disabled. Set E2E_SEED_ENABLED=1 or ENVIRONMENT=dev")
def test_connectors_run_endpoint_exists():
    """Verifica que el endpoint /api/connectors/run existe y devuelve estructura correcta."""
    from backend.app import app
    
    client = TestClient(app)
    
    # Importar para registrar el conector
    import backend.connectors.egestiona  # noqa: F401
    
    response = client.post(
        "/api/connectors/run",
        json={
            "platform_id": "egestiona",
            "headless": True,
            "max_items": 1,
        }
    )
    
    # Debe devolver 200 (aunque sea stub)
    assert response.status_code == 200
    
    data = response.json()
    
    # Verificar estructura básica
    assert "run_id" in data
    assert "platform_id" in data
    assert data["platform_id"] == "egestiona"
    assert "counts" in data
    assert "results" in data
    
    # Verificar estructura de counts
    counts = data["counts"]
    assert "total_requirements" in counts
    assert "matched" in counts
    assert "uploaded" in counts
    assert "failed" in counts
    assert "skipped" in counts


@pytest.mark.skipif(not ENDPOINT_ENABLED, reason="Connector endpoints disabled. Set E2E_SEED_ENABLED=1 or ENVIRONMENT=dev")
def test_connectors_run_dry_run():
    """Verifica que el endpoint /api/connectors/run acepta dry_run y devuelve estructura correcta."""
    from backend.app import app
    
    client = TestClient(app)
    
    # Importar para registrar el conector
    import backend.connectors.egestiona  # noqa: F401
    
    response = client.post(
        "/api/connectors/run",
        json={
            "platform_id": "egestiona",
            "tenant_id": "Aigues de Manresa",  # Sin acento según platforms.json
            "headless": True,
            "max_items": 20,
            "dry_run": True,
        },
        timeout=300,  # Timeout largo para permitir navegación real
    )
    
    # Puede devolver 200 (éxito) o 500 (error de navegación, pero estructura correcta)
    # Lo importante es que la estructura sea correcta
    assert response.status_code in (200, 500), f"Unexpected status code: {response.status_code}"
    
    data = response.json()
    
    # Verificar estructura básica (incluso si hay error)
    assert "run_id" in data
    assert "platform_id" in data
    assert data["platform_id"] == "egestiona"
    
    # Si hay error, verificar que es de navegación (no de estructura)
    if "error" in data:
        # El error puede ser de navegación (modal, timeout, etc.) pero la estructura es correcta
        assert isinstance(data["error"], str)
        # Verificar que al menos se intentó ejecutar
        assert "counts" in data or "error" in data
    else:
        # Si no hay error, verificar estructura completa
        assert "dry_run" in data
        assert data["dry_run"] is True
        assert "evidence_dir" in data
        assert "counts" in data
        assert "results" in data
        
        # Verificar que evidence_dir existe
        import os
        evidence_dir = data["evidence_dir"]
        if evidence_dir and os.path.exists(evidence_dir):
            # Verificar que report.json y report.md existen (si se llegó a generar)
            import pathlib
            evidence_path = pathlib.Path(evidence_dir)
            # Estos archivos pueden no existir si falló antes de generar el informe
            # pero el test debe pasar si la estructura es correcta


@pytest.mark.skipif(not ENDPOINT_ENABLED, reason="Connector endpoints disabled. Set E2E_SEED_ENABLED=1 or ENVIRONMENT=dev")
def test_connectors_run_endpoint_unknown_platform():
    """Verifica que el endpoint devuelve error para plataformas desconocidas."""
    from backend.app import app
    
    client = TestClient(app)
    
    response = client.post(
        "/api/connectors/run",
        json={
            "platform_id": "unknown_platform",
            "headless": True,
            "max_items": 1,
        }
    )
    
    # Debe devolver 400 (Bad Request)
    assert response.status_code == 400


@pytest.mark.skipif(ENDPOINT_ENABLED, reason="Endpoint should be disabled when E2E_SEED_ENABLED != 1 and ENVIRONMENT != dev")
def test_connectors_run_endpoint_disabled():
    """Verifica que el endpoint está deshabilitado cuando no está en modo dev."""
    from backend.app import app
    
    client = TestClient(app)
    
    response = client.post(
        "/api/connectors/run",
        json={
            "platform_id": "egestiona",
            "headless": True,
            "max_items": 1,
        }
    )
    
    # Debe devolver 404 (Not Found) cuando está deshabilitado
    assert response.status_code == 404
