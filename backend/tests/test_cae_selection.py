"""
Tests unitarios para selección y planificación CAE v1.5.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from pathlib import Path

from backend.cae.submission_models_v1 import (
    CAEScopeContextV1,
    CAESubmissionPlanV1,
    CAESubmissionItemV1,
)
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.shared.document_repository_v1 import DocumentInstanceV1, DocumentTypeV1
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.app import app


@pytest.fixture
def mock_store():
    """Mock del store de documentos."""
    store = Mock(spec=DocumentRepositoryStoreV1)
    return store


@pytest.fixture
def sample_doc():
    """Documento de ejemplo."""
    doc = Mock(spec=DocumentInstanceV1)
    doc.doc_id = "test-doc-001"
    doc.type_id = "T104_AUTONOMOS_RECEIPT"
    doc.file_name_original = "test.pdf"
    doc.issued_at = datetime(2025, 12, 1)
    doc.status = Mock()
    doc.status.value = "reviewed"
    doc.computed_validity = Mock()
    doc.computed_validity.valid_to = datetime(2026, 12, 31)
    doc.updated_at = datetime(2025, 12, 1)
    doc.file_sha256 = "abc123"
    doc.scope = Mock()
    doc.scope.value = "worker"
    doc.company_key = "TEDELAB"
    doc.person_key = "EMILIO"
    doc.period_key = "2025-12"
    return doc


@pytest.fixture
def sample_doc_type():
    """Tipo de documento de ejemplo."""
    doc_type = Mock(spec=DocumentTypeV1)
    doc_type.type_id = "T104_AUTONOMOS_RECEIPT"
    doc_type.name = "Recibo Autónomos"
    doc_type.validity_policy = Mock()
    doc_type.validity_policy.start_mode = Mock()
    doc_type.validity_policy.start_mode.value = "automatic"
    return doc_type


class TestDocCandidates:
    """Tests para GET /api/cae/doc_candidates."""
    
    def test_doc_candidates_filters_and_orders(self, tmp_path, sample_doc, sample_doc_type):
        """Test que doc_candidates filtra y ordena correctamente."""
        with patch('backend.cae.submission_routes.DATA_DIR', tmp_path):
            with patch('backend.repository.document_repository_store_v1.DocumentRepositoryStoreV1') as mock_store_class:
                mock_store = Mock()
                mock_store.list_documents.return_value = [sample_doc]
                mock_store.get_type.return_value = sample_doc_type
                pdf_path = Path(tmp_path / "test-doc-001.pdf")
                mock_store._get_doc_pdf_path.return_value = pdf_path
                mock_store_class.return_value = mock_store
                
                # Crear el PDF para que exista
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                pdf_path.write_bytes(b"fake pdf content")
                
                with patch('backend.repository.document_status_calculator_v1.calculate_document_status', return_value=(
                    Mock(value="VALID"), None, None, None, None
                )):
                    try:
                        client = TestClient(app)
                        response = client.get(
                            "/api/cae/doc_candidates",
                            params={
                                "type_id": "T104_AUTONOMOS_RECEIPT",
                                "scope": "worker",
                                "company_key": "TEDELAB",
                                "person_key": "EMILIO",
                                "period_key": "2025-12",
                            }
                        )
                        
                        assert response.status_code == 200
                        data = response.json()
                        assert data["candidates"] is not None
                        assert len(data["candidates"]) == 1
                        assert data["candidates"][0]["doc_id"] == "test-doc-001"
                        assert data["candidates"][0]["file_name_original"] == "test.pdf"
                        assert data["candidates"][0]["pdf_exists"] is True
                    finally:
                        # Limpiar
                        if pdf_path.exists():
                            pdf_path.unlink()
    
    def test_doc_candidates_validates_scope(self, tmp_path):
        """Test que doc_candidates valida el scope."""
        with patch('backend.cae.submission_routes.DATA_DIR', tmp_path):
            client = TestClient(app)
            
            # Scope inválido
            response = client.get(
                "/api/cae/doc_candidates",
                params={
                    "type_id": "T104_AUTONOMOS_RECEIPT",
                    "scope": "invalid",
                    "company_key": "TEDELAB",
                }
            )
            assert response.status_code == 400
            
            # Scope company sin company_key
            response = client.get(
                "/api/cae/doc_candidates",
                params={
                    "type_id": "T104_AUTONOMOS_RECEIPT",
                    "scope": "company",
                }
            )
            assert response.status_code == 400
            
            # Scope worker sin person_key
            response = client.get(
                "/api/cae/doc_candidates",
                params={
                    "type_id": "T104_AUTONOMOS_RECEIPT",
                    "scope": "worker",
                    "company_key": "TEDELAB",
                }
            )
            assert response.status_code == 400
    
    def test_doc_candidates_fallback_false_returns_empty(self, tmp_path, sample_doc, sample_doc_type):
        """Test que doc_candidates con allow_period_fallback=false devuelve [] cuando no hay docs con period_key."""
        with patch('backend.cae.submission_routes.DATA_DIR', tmp_path):
            with patch('backend.repository.document_repository_store_v1.DocumentRepositoryStoreV1') as mock_store_class:
                mock_store = Mock()
                # Primera llamada con period_key: devuelve []
                # Segunda llamada (fallback): no se llama porque allow_period_fallback=false
                mock_store.list_documents.return_value = []  # No hay documentos con ese period_key
                mock_store.get_type.return_value = sample_doc_type
                mock_store_class.return_value = mock_store
                
                client = TestClient(app)
                response = client.get(
                    "/api/cae/doc_candidates",
                    params={
                        "type_id": "T104_AUTONOMOS_RECEIPT",
                        "scope": "worker",
                        "company_key": "TEDELAB",
                        "person_key": "EMILIO",
                        "period_key": "2025-12",
                        "allow_period_fallback": "false",
                    }
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["candidates"] == []
                assert data["fallback_applied"] is False
                
                # Verificar que solo se llamó una vez (sin fallback)
                assert mock_store.list_documents.call_count == 1
                # Verificar que se llamó con period_key
                call_args = mock_store.list_documents.call_args
                assert call_args.kwargs.get("period_key") == "2025-12"
    
    def test_doc_candidates_fallback_true_returns_other_periods(self, tmp_path, sample_doc, sample_doc_type):
        """Test que doc_candidates con allow_period_fallback=true devuelve docs de otros periodos cuando no hay con period_key."""
        with patch('backend.cae.submission_routes.DATA_DIR', tmp_path):
            with patch('backend.repository.document_repository_store_v1.DocumentRepositoryStoreV1') as mock_store_class:
                mock_store = Mock()
                pdf_path = Path(tmp_path / "test-doc-001.pdf")
                mock_store._get_doc_pdf_path.return_value = pdf_path
                mock_store.get_type.return_value = sample_doc_type
                
                # Primera llamada con period_key: devuelve []
                # Segunda llamada sin period_key (fallback): devuelve [sample_doc]
                def list_documents_side_effect(**kwargs):
                    if kwargs.get("period_key") == "2025-12":
                        return []  # No hay documentos con ese period_key
                    elif kwargs.get("period_key") is None:
                        return [sample_doc]  # Fallback: devolver documento de otro periodo
                    return []
                
                mock_store.list_documents.side_effect = list_documents_side_effect
                mock_store_class.return_value = mock_store
                
                # Crear el PDF para que exista
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                pdf_path.write_bytes(b"fake pdf content")
                
                with patch('backend.repository.document_status_calculator_v1.calculate_document_status', return_value=(
                    Mock(value="VALID"), None, None, None, None
                )):
                    try:
                        client = TestClient(app)
                        response = client.get(
                            "/api/cae/doc_candidates",
                            params={
                                "type_id": "T104_AUTONOMOS_RECEIPT",
                                "scope": "worker",
                                "company_key": "TEDELAB",
                                "person_key": "EMILIO",
                                "period_key": "2025-12",
                                "allow_period_fallback": "true",
                            }
                        )
                        
                        assert response.status_code == 200
                        data = response.json()
                        assert len(data["candidates"]) == 1
                        assert data["candidates"][0]["doc_id"] == "test-doc-001"
                        assert data["fallback_applied"] is True
                        
                        # Verificar que se llamó dos veces (con period_key y sin period_key)
                        assert mock_store.list_documents.call_count == 2
                        # Primera llamada con period_key
                        assert mock_store.list_documents.call_args_list[0].kwargs.get("period_key") == "2025-12"
                        # Segunda llamada sin period_key (fallback)
                        assert mock_store.list_documents.call_args_list[1].kwargs.get("period_key") is None
                    finally:
                        # Limpiar
                        if pdf_path.exists():
                            pdf_path.unlink()
    
    def test_doc_candidates_fallback_not_applied_when_docs_exist(self, tmp_path, sample_doc, sample_doc_type):
        """Test que doc_candidates no aplica fallback cuando hay documentos con el period_key solicitado."""
        with patch('backend.cae.submission_routes.DATA_DIR', tmp_path):
            with patch('backend.repository.document_repository_store_v1.DocumentRepositoryStoreV1') as mock_store_class:
                mock_store = Mock()
                mock_store.list_documents.return_value = [sample_doc]  # Hay documentos con ese period_key
                mock_store.get_type.return_value = sample_doc_type
                pdf_path = Path(tmp_path / "test-doc-001.pdf")
                mock_store._get_doc_pdf_path.return_value = pdf_path
                mock_store_class.return_value = mock_store
                
                # Crear el PDF para que exista
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                pdf_path.write_bytes(b"fake pdf content")
                
                with patch('backend.repository.document_status_calculator_v1.calculate_document_status', return_value=(
                    Mock(value="VALID"), None, None, None, None
                )):
                    try:
                        client = TestClient(app)
                        response = client.get(
                            "/api/cae/doc_candidates",
                            params={
                                "type_id": "T104_AUTONOMOS_RECEIPT",
                                "scope": "worker",
                                "company_key": "TEDELAB",
                                "person_key": "EMILIO",
                                "period_key": "2025-12",
                                "allow_period_fallback": "true",
                            }
                        )
                        
                        assert response.status_code == 200
                        data = response.json()
                        assert len(data["candidates"]) == 1
                        assert data["fallback_applied"] is False
                        
                        # Verificar que solo se llamó una vez (sin fallback porque hay documentos)
                        assert mock_store.list_documents.call_count == 1
                    finally:
                        # Limpiar
                        if pdf_path.exists():
                            pdf_path.unlink()


class TestPlanFromSelection:
    """Tests para POST /api/cae/plan_from_selection."""
    
    def test_plan_from_selection_ready_when_all_have_suggested_doc_id(self, tmp_path):
        """Test que plan_from_selection retorna READY cuando todos tienen suggested_doc_id."""
        with patch('backend.cae.submission_routes.DATA_DIR', tmp_path):
            with patch('backend.repository.document_repository_store_v1.DocumentRepositoryStoreV1') as mock_store_class:
                mock_store = Mock()
                mock_doc = Mock()
                mock_doc.doc_id = "test-doc-001"
                mock_doc.type_id = "T104_AUTONOMOS_RECEIPT"
                mock_doc.issued_at = datetime(2025, 12, 1)
                mock_doc.computed_validity = Mock()
                mock_doc.computed_validity.valid_from = datetime(2025, 12, 1)
                mock_doc.computed_validity.valid_to = datetime(2026, 12, 31)
                mock_doc.status = Mock()
                mock_doc.status.value = "reviewed"
                mock_doc.scope = Mock()
                mock_doc.scope.value = "worker"
                mock_doc.extracted = None
                
                mock_doc_type = Mock()
                mock_doc_type.type_id = "T104_AUTONOMOS_RECEIPT"
                mock_doc_type.validity_policy = Mock()
                mock_doc_type.validity_policy.start_mode = Mock()
                mock_doc_type.validity_policy.start_mode.value = "automatic"
                
                pdf_path = Path(tmp_path / "test.pdf")
                # Crear el PDF para que exista
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                pdf_path.write_bytes(b"fake pdf content")
                
                mock_store.get_document.return_value = mock_doc
                mock_store.get_type.return_value = mock_doc_type
                mock_store._get_doc_pdf_path.return_value = pdf_path
                mock_store_class.return_value = mock_store
                
                try:
                    client = TestClient(app)
                    response = client.post(
                        "/api/cae/plan_from_selection",
                        json={
                            "scope": {
                                "platform_key": "egestiona",
                                "type_ids": [],
                                "company_key": "TEDELAB",
                                "person_key": "EMILIO",
                                "mode": "PREPARE_WRITE",
                            },
                            "selected_items": [
                                {
                                    "type_id": "T104_AUTONOMOS_RECEIPT",
                                    "scope": "worker",
                                    "company_key": "TEDELAB",
                                    "person_key": "EMILIO",
                                    "period_key": "2025-12",
                                    "suggested_doc_id": "test-doc-001",
                                },
                            ],
                        }
                    )
                    
                    assert response.status_code == 200
                    plan = response.json()
                    assert plan["decision"] == "READY"
                    assert len(plan["items"]) == 1
                    assert plan["items"][0]["suggested_doc_id"] == "test-doc-001"
                    assert plan["items"][0]["status"] == "PLANNED"
                finally:
                    # Limpiar
                    if pdf_path.exists():
                        pdf_path.unlink()
    
    def test_plan_from_selection_needs_confirmation_when_missing_doc_assignment(self, tmp_path):
        """Test que plan_from_selection retorna NEEDS_CONFIRMATION cuando falta asignación de doc."""
        with patch('backend.cae.submission_routes.DATA_DIR', tmp_path):
            client = TestClient(app)
            response = client.post(
                "/api/cae/plan_from_selection",
                json={
                    "scope": {
                        "platform_key": "egestiona",
                        "type_ids": [],
                        "company_key": "TEDELAB",
                        "person_key": "EMILIO",
                        "mode": "PREPARE_WRITE",
                    },
                    "selected_items": [
                        {
                            "type_id": "T104_AUTONOMOS_RECEIPT",
                            "scope": "worker",
                            "company_key": "TEDELAB",
                            "person_key": "EMILIO",
                            "period_key": "2025-12",
                            "suggested_doc_id": None,  # Sin asignación
                        },
                    ],
                }
            )
            
            assert response.status_code == 200
            plan = response.json()
            assert plan["decision"] == "NEEDS_CONFIRMATION"
            assert len(plan["items"]) == 1
            assert plan["items"][0]["status"] == "NEEDS_CONFIRMATION"
            assert "suggested_doc_id no asignado" in plan["items"][0]["reason"]
    
    def test_plan_from_selection_blocked_when_doc_not_found(self, tmp_path):
        """Test que plan_from_selection retorna BLOCKED cuando el documento no existe."""
        with patch('backend.cae.submission_routes.DATA_DIR', tmp_path):
            with patch('backend.repository.document_repository_store_v1.DocumentRepositoryStoreV1') as mock_store_class:
                mock_store = Mock()
                mock_store.get_document.return_value = None  # Documento no encontrado
                mock_store_class.return_value = mock_store
                
                client = TestClient(app)
                response = client.post(
                    "/api/cae/plan_from_selection",
                    json={
                        "scope": {
                            "platform_key": "egestiona",
                            "type_ids": [],
                            "company_key": "TEDELAB",
                            "person_key": "EMILIO",
                            "mode": "PREPARE_WRITE",
                        },
                        "selected_items": [
                            {
                                "type_id": "T104_AUTONOMOS_RECEIPT",
                                "scope": "worker",
                                "company_key": "TEDELAB",
                                "person_key": "EMILIO",
                                "period_key": "2025-12",
                                "suggested_doc_id": "non-existent-doc",
                            },
                        ],
                    }
                )
                
                assert response.status_code == 200
                plan = response.json()
                assert plan["decision"] == "BLOCKED"
                assert len(plan["items"]) == 1
                assert plan["items"][0]["status"] == "BLOCKED"
                assert "no encontrado" in plan["items"][0]["reason"].lower()
    
    def test_plan_from_selection_blocked_when_pdf_not_found(self, tmp_path):
        """Test que plan_from_selection retorna BLOCKED cuando el PDF no existe."""
        with patch('backend.cae.submission_routes.DATA_DIR', tmp_path):
            with patch('backend.repository.document_repository_store_v1.DocumentRepositoryStoreV1') as mock_store_class:
                mock_store = Mock()
                mock_doc = Mock()
                mock_doc.doc_id = "test-doc-001"
                mock_doc.type_id = "T104_AUTONOMOS_RECEIPT"
                
                pdf_path = Path(tmp_path / "test.pdf")
                # NO crear el PDF (para que no exista)
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                
                mock_store.get_document.return_value = mock_doc
                mock_store._get_doc_pdf_path.return_value = pdf_path
                mock_store_class.return_value = mock_store
                
                client = TestClient(app)
                response = client.post(
                    "/api/cae/plan_from_selection",
                    json={
                        "scope": {
                            "platform_key": "egestiona",
                            "type_ids": [],
                            "company_key": "TEDELAB",
                            "person_key": "EMILIO",
                            "mode": "PREPARE_WRITE",
                        },
                        "selected_items": [
                            {
                                "type_id": "T104_AUTONOMOS_RECEIPT",
                                "scope": "worker",
                                "company_key": "TEDELAB",
                                "person_key": "EMILIO",
                                "period_key": "2025-12",
                                "suggested_doc_id": "test-doc-001",
                            },
                        ],
                    }
                )
                
                assert response.status_code == 200
                plan = response.json()
                assert plan["decision"] == "BLOCKED"
                assert len(plan["items"]) == 1
                assert plan["items"][0]["status"] == "BLOCKED"
                assert "PDF no encontrado" in plan["items"][0]["reason"]

