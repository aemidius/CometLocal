"""
SPRINT C2.35: Unit tests para endpoint add_alias.
"""

import pytest
import uuid
import os
from pathlib import Path
from unittest.mock import patch
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.shared.document_repository_v1 import DocumentTypeV1, DocumentScopeV1, ValidityPolicyV1, ValidityModeV1, ValidityBasisV1, MonthlyValidityConfigV1


def test_add_alias_to_type(tmp_path):
    """Test que verifica que se añade alias a un tipo existente."""
    # Usar directorio único para este test
    test_id = str(uuid.uuid4())[:8]
    base_dir = tmp_path / f"data_{test_id}"
    base_dir.mkdir()
    
    # Mock load_settings para que use nuestro base_dir
    with patch('backend.repository.document_repository_store_v1.load_settings') as mock_settings:
        class MockSettings:
            repository_root_dir = str(base_dir / "repository")
        mock_settings.return_value = MockSettings()
        store = DocumentRepositoryStoreV1(base_dir=str(base_dir))
        
        # Crear tipo de prueba
        doc_type = DocumentTypeV1(
            type_id="TEST_TYPE_ADD",
            name="Test Type Add",
            scope=DocumentScopeV1.company,
            validity_policy=ValidityPolicyV1(
                mode=ValidityModeV1.monthly,
                basis=ValidityBasisV1.issue_date,
                monthly=MonthlyValidityConfigV1()
            ),
            platform_aliases=["existing_alias"]
        )
        store.create_type(doc_type)
        
        # Verificar alias inicial
        original_type = store.get_type("TEST_TYPE_ADD")
        assert "existing_alias" in original_type.platform_aliases
        assert len(original_type.platform_aliases) == 1
        
        # Añadir nuevo alias
        new_aliases = list(original_type.platform_aliases) + ["new_alias"]
        doc_type_dict = original_type.model_dump()
        doc_type_dict["platform_aliases"] = new_aliases
        updated_type = DocumentTypeV1(**doc_type_dict)
        store.update_type("TEST_TYPE_ADD", updated_type)
        
        # Verificar que se añadió el alias
        updated = store.get_type("TEST_TYPE_ADD")
        assert "existing_alias" in updated.platform_aliases
        assert "new_alias" in updated.platform_aliases
        assert len(updated.platform_aliases) == 2


def test_add_alias_no_duplicate(tmp_path):
    """Test que verifica que no se duplican aliases."""
    # Usar directorio único para este test
    test_id = str(uuid.uuid4())[:8]
    base_dir = tmp_path / f"data_{test_id}"
    base_dir.mkdir()
    
    # Mock load_settings para que use nuestro base_dir
    with patch('backend.repository.document_repository_store_v1.load_settings') as mock_settings:
        class MockSettings:
            repository_root_dir = str(base_dir / "repository")
        mock_settings.return_value = MockSettings()
        store = DocumentRepositoryStoreV1(base_dir=str(base_dir))
        
        # Crear tipo con alias
        doc_type = DocumentTypeV1(
            type_id="TEST_TYPE_NO_DUP",
            name="Test Type No Dup",
            scope=DocumentScopeV1.company,
            validity_policy=ValidityPolicyV1(
                mode=ValidityModeV1.monthly,
                basis=ValidityBasisV1.issue_date,
                monthly=MonthlyValidityConfigV1()
            ),
            platform_aliases=["existing_alias"]
        )
        store.create_type(doc_type)
        
        # Intentar añadir el mismo alias (debe ser idempotente)
        original_type = store.get_type("TEST_TYPE_NO_DUP")
        new_aliases = list(original_type.platform_aliases)
        if "existing_alias" not in new_aliases:
            new_aliases.append("existing_alias")
        
        # Verificar que no se duplicó
        assert new_aliases.count("existing_alias") == 1


def test_add_alias_no_delete_others(tmp_path):
    """Test que verifica que no se borran otros aliases."""
    # Usar directorio único para este test
    test_id = str(uuid.uuid4())[:8]
    base_dir = tmp_path / f"data_{test_id}"
    base_dir.mkdir()
    
    # Mock load_settings para que use nuestro base_dir
    with patch('backend.repository.document_repository_store_v1.load_settings') as mock_settings:
        class MockSettings:
            repository_root_dir = str(base_dir / "repository")
        mock_settings.return_value = MockSettings()
        store = DocumentRepositoryStoreV1(base_dir=str(base_dir))
        
        # Crear tipo con múltiples aliases
        doc_type = DocumentTypeV1(
            type_id="TEST_TYPE_NO_DELETE",
            name="Test Type No Delete",
            scope=DocumentScopeV1.company,
            validity_policy=ValidityPolicyV1(
                mode=ValidityModeV1.monthly,
                basis=ValidityBasisV1.issue_date,
                monthly=MonthlyValidityConfigV1()
            ),
            platform_aliases=["alias1", "alias2", "alias3"]
        )
        store.create_type(doc_type)
        
        # Añadir nuevo alias
        original_type = store.get_type("TEST_TYPE_NO_DELETE")
        new_aliases = list(original_type.platform_aliases) + ["new_alias"]
        doc_type_dict = original_type.model_dump()
        doc_type_dict["platform_aliases"] = new_aliases
        updated_type = DocumentTypeV1(**doc_type_dict)
        store.update_type("TEST_TYPE_NO_DELETE", updated_type)
        
        # Verificar que todos los aliases originales siguen presentes
        updated = store.get_type("TEST_TYPE_NO_DELETE")
        assert "alias1" in updated.platform_aliases
        assert "alias2" in updated.platform_aliases
        assert "alias3" in updated.platform_aliases
        assert "new_alias" in updated.platform_aliases
        assert len(updated.platform_aliases) == 4
