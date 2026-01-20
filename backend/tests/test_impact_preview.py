"""
SPRINT C2.36: Tests unitarios para Impact Preview Engine.
"""

import pytest
from pathlib import Path
from datetime import date
from unittest.mock import patch
import uuid

from backend.repository.impact_preview_v1 import (
    preview_assign_alias,
    preview_create_type,
    ImpactPreviewV1
)
from backend.repository.document_matcher_v1 import PendingItemV1
from backend.shared.document_repository_v1 import DocumentTypeV1, ValidityPolicyV1, MonthlyValidityConfigV1, DocumentScopeV1
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1


def test_preview_assign_alias_no_write(tmp_path):
    """Verificar que preview_assign_alias no escribe nada."""
    # Aislar datos por test usando UUID único
    test_id = str(uuid.uuid4())[:8]
    test_base_dir = tmp_path / f"data_{test_id}"
    test_base_dir.mkdir(parents=True, exist_ok=True)
    
    # Mock load_settings para usar directorio único
    with patch('backend.repository.document_repository_store_v1.load_settings') as mock_settings:
        class MockSettings:
            repository_root_dir = str(test_base_dir / "repository")
        mock_settings.return_value = MockSettings()
        store = DocumentRepositoryStoreV1(base_dir=str(test_base_dir))
        
        # Crear tipo de prueba
        test_type = DocumentTypeV1(
            type_id="TEST_TYPE",
            name="Test Type",
            scope=DocumentScopeV1.company,
            active=True,
            platform_aliases=["existing_alias"],
            validity_policy=ValidityPolicyV1(
                mode="monthly",
                basis="issue_date",
                monthly=MonthlyValidityConfigV1()
            ),
            required_fields=[],
            allow_late_submission=False,
            issue_date_required=True,
            validity_start_mode="issue_date"
        )
        
        store.create_type(test_type)
        
        # Crear pending item
        pending = PendingItemV1(
            tipo_doc="T205.0",
            elemento="Test Element",
            empresa="TEST_COMPANY",
            trabajador=None,
            fecha_inicio=date(2025, 1, 1),
            fecha_fin=date(2025, 1, 31)
        )
        
        # Obtener preview
        preview = preview_assign_alias(
            pending=pending,
            type_id="TEST_TYPE",
            alias="T205.0",
            platform_key="egestiona",
            context={
                "company_key": "TEST_COMPANY",
                "platform_key": "egestiona"
            },
            base_dir=test_base_dir
        )
        
        # Verificar que es read-only: el tipo no debe haber cambiado
        stored_type = store.get_type("TEST_TYPE")
        assert "T205.0" not in stored_type.platform_aliases  # No se añadió
        
        # Verificar estructura del preview
        assert isinstance(preview, ImpactPreviewV1)
        preview_dict = preview.to_dict()
        assert "will_affect" in preview_dict
        assert "will_add" in preview_dict
        assert "will_not_change" in preview_dict
        assert "confidence_notes" in preview_dict


def test_preview_assign_alias_already_exists(tmp_path):
    """Verificar que preview detecta cuando alias ya existe."""
    test_id = str(uuid.uuid4())[:8]
    test_base_dir = tmp_path / f"data_{test_id}"
    test_base_dir.mkdir(parents=True, exist_ok=True)
    
    with patch('backend.repository.document_repository_store_v1.load_settings') as mock_settings:
        class MockSettings:
            repository_root_dir = str(test_base_dir / "repository")
        mock_settings.return_value = MockSettings()
        store = DocumentRepositoryStoreV1(base_dir=str(test_base_dir))
        
        test_type = DocumentTypeV1(
            type_id="TEST_TYPE",
            name="Test Type",
            scope=DocumentScopeV1.company,
            active=True,
            platform_aliases=["T205.0"],  # Alias ya existe
            validity_policy=ValidityPolicyV1(
                mode="monthly",
                basis="issue_date",
                monthly=MonthlyValidityConfigV1()
            ),
            required_fields=[],
            allow_late_submission=False,
            issue_date_required=True,
            validity_start_mode="issue_date"
        )
        
        store.create_type(test_type)
        
        pending = PendingItemV1(
            tipo_doc="T205.0",
            elemento="Test Element"
        )
        
        preview = preview_assign_alias(
            pending=pending,
            type_id="TEST_TYPE",
            alias="T205.0",
            platform_key="egestiona",
            context={"company_key": "TEST_COMPANY"},
            base_dir=test_base_dir
        )
        
        # Debe indicar que no hay impacto (alias ya existe)
        assert preview.will_affect["pending_count"] == 0
        assert len(preview.will_add["aliases"]) == 0
        assert "Alias ya existe" in preview.confidence_notes[0]


def test_preview_create_type_no_write(tmp_path):
    """Verificar que preview_create_type no escribe nada."""
    test_id = str(uuid.uuid4())[:8]
    test_base_dir = tmp_path / f"data_{test_id}"
    test_base_dir.mkdir(parents=True, exist_ok=True)
    
    with patch('backend.repository.document_repository_store_v1.load_settings') as mock_settings:
        class MockSettings:
            repository_root_dir = str(test_base_dir / "repository")
        mock_settings.return_value = MockSettings()
        store = DocumentRepositoryStoreV1(base_dir=str(test_base_dir))
        
        pending = PendingItemV1(
            tipo_doc="NEW_TYPE",
            elemento="New Element"
        )
        
        draft_type = DocumentTypeV1(
            type_id="NEW_TYPE",
            name="New Type",
            scope=DocumentScopeV1.company,
            active=True,
            platform_aliases=["NEW_TYPE"],
            validity_policy=ValidityPolicyV1(
                mode="monthly",
                basis="issue_date",
                monthly=MonthlyValidityConfigV1()
            ),
            required_fields=[],
            allow_late_submission=False,
            issue_date_required=True,
            validity_start_mode="issue_date"
        )
        
        preview = preview_create_type(
            pending=pending,
            draft_type=draft_type,
            platform_key="egestiona",
            context={"company_key": "TEST_COMPANY"},
            base_dir=test_base_dir
        )
        
        # Verificar que no se creó el tipo
        stored_type = store.get_type("NEW_TYPE")
        assert stored_type is None  # No debe existir
        
        # Verificar estructura del preview
        assert isinstance(preview, ImpactPreviewV1)
        preview_dict = preview.to_dict()
        assert "will_affect" in preview_dict
        assert "will_add" in preview_dict
        assert preview.will_add["type_id"] == "NEW_TYPE"


def test_preview_deterministic(tmp_path):
    """Verificar que preview es determinista: mismo input → mismo output."""
    test_id = str(uuid.uuid4())[:8]
    test_base_dir = tmp_path / f"data_{test_id}"
    test_base_dir.mkdir(parents=True, exist_ok=True)
    
    with patch('backend.repository.document_repository_store_v1.load_settings') as mock_settings:
        class MockSettings:
            repository_root_dir = str(test_base_dir / "repository")
        mock_settings.return_value = MockSettings()
        store = DocumentRepositoryStoreV1(base_dir=str(test_base_dir))
        
        test_type = DocumentTypeV1(
            type_id="TEST_TYPE",
            name="Test Type",
            scope=DocumentScopeV1.company,
            active=True,
            platform_aliases=[],
            validity_policy=ValidityPolicyV1(
                mode="monthly",
                basis="issue_date",
                monthly=MonthlyValidityConfigV1()
            ),
            required_fields=[],
            allow_late_submission=False,
            issue_date_required=True,
            validity_start_mode="issue_date"
        )
        
        store.create_type(test_type)
        
        pending = PendingItemV1(
            tipo_doc="T205.0",
            elemento="Test Element"
        )
        
        # Ejecutar preview dos veces
        preview1 = preview_assign_alias(
            pending=pending,
            type_id="TEST_TYPE",
            alias="T205.0",
            platform_key="egestiona",
            context={"company_key": "TEST_COMPANY"},
            base_dir=test_base_dir
        )
        
        preview2 = preview_assign_alias(
            pending=pending,
            type_id="TEST_TYPE",
            alias="T205.0",
            platform_key="egestiona",
            context={"company_key": "TEST_COMPANY"},
            base_dir=test_base_dir
        )
        
        # Deben ser idénticos
        assert preview1.to_dict() == preview2.to_dict()
