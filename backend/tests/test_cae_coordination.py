"""
Tests unitarios para coordinación CAE v1.6.
"""

import pytest
import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from backend.app import app
from backend.cae.coordination_models_v1 import CoordinationScopeV1, CoordinationSnapshotV1, PlatformPendingItemV1
from backend.config import DATA_DIR


@pytest.fixture
def mock_snapshot_data():
    """Datos de snapshot de ejemplo."""
    return {
        "snapshot_id": "CAESNAP-20250101-120000-test",
        "created_at": datetime.utcnow().isoformat(),
        "scope": {
            "platform_key": "egestiona",
            "coordination_label": "Kern",
            "company_key": "TEDELAB",
            "person_key": None,
            "type_ids": None,
            "period_keys": None,
        },
        "platform": {
            "label": "Kern",
            "client_code": "TEST_CLIENT",
        },
        "pending_items": [
            {
                "platform_item_id": "ITEM_001",
                "type_id": None,
                "platform_type_label": "Tipo Test 1",
                "type_alias_candidates": ["TEST_TYPE_1"],
                "company_key": "TEDELAB",
                "person_key": None,
                "period_key": "2025-12",
                "raw_label": "Pendiente Test 1",
                "raw_metadata": {"index": 0},
                "status": "PENDING",
            },
        ],
        "evidence_path": "docs/evidence/cae_snapshots/CAESNAP-20250101-120000-test.json",
    }


class TestCoordinationSnapshot:
    """Tests para creación y lectura de snapshots."""
    
    def test_snapshot_saved_without_secrets(self, tmp_path, mock_snapshot_data):
        """Test que el snapshot se guarda sin secretos."""
        with patch('backend.cae.coordination_routes.DATA_DIR', tmp_path):
            # Crear directorio de evidencia
            evidence_dir = tmp_path.parent / "docs" / "evidence" / "cae_snapshots"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            
            # Crear snapshot FAKE
            with patch.dict(os.environ, {'CAE_COORDINATION_MODE': 'FAKE'}):
                client = TestClient(app)
                response = client.post(
                    "/api/cae/coordination/snapshot",
                    json={
                        "platform_key": "egestiona",
                        "coordination_label": "Kern",
                        "company_key": "TEDELAB",
                    }
                )
                
                assert response.status_code == 200
                snapshot = response.json()
                
                # Verificar que no contiene secretos
                assert "password" not in json.dumps(snapshot).lower()
                assert "password_ref" not in json.dumps(snapshot).lower()
                assert "secret" not in json.dumps(snapshot).lower()
                
                # Verificar que contiene platform info sin secretos
                assert "platform" in snapshot
                assert "label" in snapshot["platform"]
                assert "client_code" in snapshot["platform"]
    
    def test_get_snapshot_not_found(self, tmp_path):
        """Test que GET snapshot devuelve 404 si no existe."""
        with patch('backend.cae.coordination_routes.DATA_DIR', tmp_path):
            client = TestClient(app)
            response = client.get("/api/cae/coordination/snapshot/NONEXISTENT")
            
            assert response.status_code == 404
    
    def test_snapshot_doc_candidates(self, tmp_path, mock_snapshot_data):
        """Test que doc_candidates funciona con snapshot."""
        with patch('backend.cae.coordination_routes.DATA_DIR', tmp_path):
            # Crear snapshot file
            evidence_dir = tmp_path.parent / "docs" / "evidence" / "cae_snapshots"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            snapshot_path = evidence_dir / f"{mock_snapshot_data['snapshot_id']}.json"
            
            with open(snapshot_path, 'w', encoding='utf-8') as f:
                json.dump(mock_snapshot_data, f, indent=2)
            
            # Mock doc_candidates
            with patch('backend.cae.coordination_routes.get_doc_candidates') as mock_get_candidates:
                mock_response = Mock()
                mock_response.model_dump.return_value = {
                    "candidates": [
                        {"doc_id": "test-doc-001", "file_name_original": "test.pdf"}
                    ],
                    "fallback_applied": False,
                }
                mock_get_candidates.return_value = mock_response
                
                client = TestClient(app)
                response = client.get(
                    f"/api/cae/coordination/snapshot/{mock_snapshot_data['snapshot_id']}/doc_candidates",
                    params={"pending_index": 0, "allow_period_fallback": "true"}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert "candidates" in data
                assert "fallback_applied" in data


class TestPlanFromSnapshotSelection:
    """Tests para generar plan desde selección de snapshot."""
    
    def test_plan_from_snapshot_selection_builds_items_correctly(self, tmp_path, mock_snapshot_data):
        """Test que plan_from_snapshot_selection construye items correctamente."""
        with patch('backend.cae.coordination_routes.DATA_DIR', tmp_path):
            # Crear snapshot file
            evidence_dir = tmp_path.parent / "docs" / "evidence" / "cae_snapshots"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            snapshot_path = evidence_dir / f"{mock_snapshot_data['snapshot_id']}.json"
            
            with open(snapshot_path, 'w', encoding='utf-8') as f:
                json.dump(mock_snapshot_data, f, indent=2)
            
            # Mock create_plan_from_selection
            with patch('backend.cae.coordination_routes.create_plan_from_selection') as mock_create_plan:
                mock_plan = Mock()
                mock_plan.model_dump.return_value = {
                    "plan_id": "TEST_PLAN",
                    "decision": "READY",
                    "items": [],
                }
                mock_create_plan.return_value = mock_plan
                
                client = TestClient(app)
                response = client.post(
                    "/api/cae/coordination/plan_from_snapshot_selection",
                    json={
                        "snapshot_id": mock_snapshot_data['snapshot_id'],
                        "selected": [
                            {"pending_index": 0, "suggested_doc_id": "test-doc-001"}
                        ],
                        "scope": {
                            "platform_key": "egestiona",
                            "type_ids": [],
                            "company_key": "TEDELAB",
                            "person_key": None,
                            "period_keys": None,
                            "mode": "PREPARE_WRITE",
                        },
                    }
                )
                
                assert response.status_code == 200
                
                # Verificar que se llamó con los items correctos
                assert mock_create_plan.called
                call_args = mock_create_plan.call_args[0][0]
                assert len(call_args.selected_items) == 1
                assert call_args.selected_items[0].suggested_doc_id == "test-doc-001"



