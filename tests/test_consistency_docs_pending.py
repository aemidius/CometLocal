"""
Test de consistencia entre /api/repository/docs y /api/repository/docs/pending.

Verifica que ambos endpoints devuelven los mismos documentos expirados y próximos a expirar.
"""
import pytest
import requests
from typing import List, Dict, Any


BASE_URL = "http://127.0.0.1:8000"


def get_expired_from_docs() -> List[Dict[str, Any]]:
    """Obtiene documentos expirados desde /api/repository/docs."""
    response = requests.get(f"{BASE_URL}/api/repository/docs?validity_status=EXPIRED")
    assert response.status_code == 200, f"Error en /docs: {response.status_code} - {response.text}"
    return response.json()


def get_expired_from_pending() -> List[Dict[str, Any]]:
    """Obtiene documentos expirados desde /api/repository/docs/pending."""
    response = requests.get(f"{BASE_URL}/api/repository/docs/pending?months_ahead=3")
    assert response.status_code == 200, f"Error en /docs/pending: {response.status_code} - {response.text}"
    data = response.json()
    assert isinstance(data, dict), f"Response debe ser dict, got {type(data)}"
    assert "expired" in data, f"Response debe tener 'expired', keys: {data.keys()}"
    return data.get("expired", [])


def get_expiring_soon_from_docs() -> List[Dict[str, Any]]:
    """Obtiene documentos próximos a expirar desde /api/repository/docs."""
    response = requests.get(f"{BASE_URL}/api/repository/docs?validity_status=EXPIRING_SOON")
    assert response.status_code == 200, f"Error en /docs: {response.status_code} - {response.text}"
    return response.json()


def get_expiring_soon_from_pending() -> List[Dict[str, Any]]:
    """Obtiene documentos próximos a expirar desde /api/repository/docs/pending."""
    response = requests.get(f"{BASE_URL}/api/repository/docs/pending?months_ahead=3")
    assert response.status_code == 200, f"Error en /docs/pending: {response.status_code} - {response.text}"
    data = response.json()
    assert isinstance(data, dict), f"Response debe ser dict, got {type(data)}"
    assert "expiring_soon" in data, f"Response debe tener 'expiring_soon', keys: {data.keys()}"
    return data.get("expiring_soon", [])


def test_consistency_expired_documents():
    """
    Test: Los documentos expirados en /docs deben coincidir con los de /pending.
    
    Si /docs devuelve N documentos con validity_status=EXPIRED,
    entonces /pending debe devolver expired_count == N.
    """
    expired_from_docs = get_expired_from_docs()
    expired_from_pending = get_expired_from_pending()
    
    # Extraer doc_ids
    doc_ids_from_docs = {doc.get("doc_id") for doc in expired_from_docs if doc.get("doc_id")}
    doc_ids_from_pending = {doc.get("doc_id") for doc in expired_from_pending if doc.get("doc_id")}
    
    # Verificar que los conteos coinciden
    assert len(expired_from_docs) == len(expired_from_pending), (
        f"Inconsistencia en conteo de expirados: "
        f"/docs tiene {len(expired_from_docs)}, /pending tiene {len(expired_from_pending)}"
    )
    
    # Verificar que los doc_ids coinciden
    assert doc_ids_from_docs == doc_ids_from_pending, (
        f"Inconsistencia en doc_ids de expirados:\n"
        f"En /docs pero no en /pending: {doc_ids_from_docs - doc_ids_from_pending}\n"
        f"En /pending pero no en /docs: {doc_ids_from_pending - doc_ids_from_docs}"
    )
    
    # Verificar que validity_status es EXPIRED en ambos
    for doc in expired_from_docs:
        assert doc.get("validity_status") == "EXPIRED", (
            f"Documento {doc.get('doc_id')} en /docs tiene validity_status={doc.get('validity_status')}, "
            f"debe ser EXPIRED"
        )
    
    for doc in expired_from_pending:
        assert doc.get("validity_status") == "EXPIRED", (
            f"Documento {doc.get('doc_id')} en /pending tiene validity_status={doc.get('validity_status')}, "
            f"debe ser EXPIRED"
        )


def test_consistency_expiring_soon_documents():
    """
    Test: Los documentos próximos a expirar en /docs deben coincidir con los de /pending.
    """
    expiring_from_docs = get_expiring_soon_from_docs()
    expiring_from_pending = get_expiring_soon_from_pending()
    
    # Extraer doc_ids
    doc_ids_from_docs = {doc.get("doc_id") for doc in expiring_from_docs if doc.get("doc_id")}
    doc_ids_from_pending = {doc.get("doc_id") for doc in expiring_from_pending if doc.get("doc_id")}
    
    # Verificar que los conteos coinciden
    assert len(expiring_from_docs) == len(expiring_from_pending), (
        f"Inconsistencia en conteo de próximos a expirar: "
        f"/docs tiene {len(expiring_from_docs)}, /pending tiene {len(expiring_from_pending)}"
    )
    
    # Verificar que los doc_ids coinciden
    assert doc_ids_from_docs == doc_ids_from_pending, (
        f"Inconsistencia en doc_ids de próximos a expirar:\n"
        f"En /docs pero no en /pending: {doc_ids_from_docs - doc_ids_from_pending}\n"
        f"En /pending pero no en /docs: {doc_ids_from_pending - doc_ids_from_docs}"
    )
    
    # Verificar que validity_status es EXPIRING_SOON en ambos
    for doc in expiring_from_docs:
        assert doc.get("validity_status") == "EXPIRING_SOON", (
            f"Documento {doc.get('doc_id')} en /docs tiene validity_status={doc.get('validity_status')}, "
            f"debe ser EXPIRING_SOON"
        )
    
    for doc in expiring_from_pending:
        assert doc.get("validity_status") == "EXPIRING_SOON", (
            f"Documento {doc.get('doc_id')} en /pending tiene validity_status={doc.get('validity_status')}, "
            f"debe ser EXPIRING_SOON"
        )


def test_pending_endpoint_structure():
    """Test: Verificar que /docs/pending devuelve la estructura correcta."""
    response = requests.get(f"{BASE_URL}/api/repository/docs/pending?months_ahead=3")
    assert response.status_code == 200, f"Error en /docs/pending: {response.status_code} - {response.text}"
    
    data = response.json()
    assert isinstance(data, dict), f"Response debe ser dict, got {type(data)}"
    
    required_keys = {"expired", "expiring_soon", "missing"}
    assert required_keys.issubset(data.keys()), (
        f"Response debe tener keys {required_keys}, got {data.keys()}"
    )
    
    # Verificar que son listas
    assert isinstance(data["expired"], list), f"'expired' debe ser lista, got {type(data['expired'])}"
    assert isinstance(data["expiring_soon"], list), f"'expiring_soon' debe ser lista, got {type(data['expiring_soon'])}"
    assert isinstance(data["missing"], list), f"'missing' debe ser lista, got {type(data['missing'])}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])







