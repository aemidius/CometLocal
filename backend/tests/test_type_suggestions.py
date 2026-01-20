"""
SPRINT C2.36: Tests unitarios para Type Suggestions Engine.
"""

import pytest
from pathlib import Path
from datetime import date
import uuid
from unittest.mock import patch

from backend.repository.type_suggestions_v1 import suggest_types, TypeSuggestionV1
from backend.repository.document_matcher_v1 import PendingItemV1
from backend.shared.document_repository_v1 import (
    DocumentTypeV1,
    ValidityPolicyV1,
    MonthlyValidityConfigV1,
    DocumentScopeV1
)
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1


def test_suggest_types_scoring(tmp_path):
    """Verificar que el scoring es determinista y explicable."""
    test_id = str(uuid.uuid4())[:8]
    test_base_dir = tmp_path / f"data_{test_id}"
    test_base_dir.mkdir(parents=True, exist_ok=True)
    
    with patch('backend.repository.document_repository_store_v1.load_settings') as mock_settings:
        class MockSettings:
            repository_root_dir = str(test_base_dir / "repository")
        mock_settings.return_value = MockSettings()
        store = DocumentRepositoryStoreV1(base_dir=str(test_base_dir))
        
        # Crear tipos de prueba
        type1 = DocumentTypeV1(
            type_id="TYPE_1",
            name="Recibo Autónomos",  # Nombre similar
            scope=DocumentScopeV1.worker,
            active=True,
            platform_aliases=["T205.0"],  # Alias coincide
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
        
        type2 = DocumentTypeV1(
            type_id="TYPE_2",
            name="Otro Tipo",  # Nombre no similar
            scope=DocumentScopeV1.company,
            active=True,
            platform_aliases=[],
            validity_policy=ValidityPolicyV1(
                mode="annual",
                basis="issue_date",
                annual={"months": 12, "valid_from": "issue_date", "valid_to": "issue_date_plus_months"}
            ),
            required_fields=[],
            allow_late_submission=False,
            issue_date_required=True,
            validity_start_mode="issue_date"
        )
        
        store.create_type(type1)
        store.create_type(type2)
        
        # Crear pending item que coincide con type1
        pending = PendingItemV1(
            tipo_doc="T205.0",
            elemento="Recibo Autónomos",
            trabajador="WORKER_123",
            fecha_inicio=date(2025, 1, 1),
            fecha_fin=date(2025, 1, 31)
        )
        
        suggestions = suggest_types(
            pending=pending,
            context={
                "person_key": "WORKER_123",
                "platform_key": "egestiona"
            },
            limit=3,
            base_dir=test_base_dir
        )
        
        # Verificar que type1 tiene mayor score que type2
        assert len(suggestions) > 0
        type1_suggestion = next((s for s in suggestions if s.type_id == "TYPE_1"), None)
        type2_suggestion = next((s for s in suggestions if s.type_id == "TYPE_2"), None)
        
        if type1_suggestion and type2_suggestion:
            assert type1_suggestion.score > type2_suggestion.score
        
        # Verificar que type1 tiene razones explicables
        if type1_suggestion:
            assert len(type1_suggestion.reasons) > 0
            # Debe tener razón de alias o nombre
            has_alias_reason = any("Alias coincide" in r for r in type1_suggestion.reasons)
            has_name_reason = any("Nombre coincide" in r for r in type1_suggestion.reasons)
            assert has_alias_reason or has_name_reason


def test_suggestions_deterministic(tmp_path):
    """Verificar que las sugerencias son deterministas."""
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
            platform_aliases=["T205.0"],
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
        
        # Ejecutar dos veces
        suggestions1 = suggest_types(
            pending=pending,
            context={"company_key": "TEST_COMPANY"},
            limit=3,
            base_dir=test_base_dir
        )
        
        suggestions2 = suggest_types(
            pending=pending,
            context={"company_key": "TEST_COMPANY"},
            limit=3,
            base_dir=test_base_dir
        )
        
        # Deben ser idénticos
        assert len(suggestions1) == len(suggestions2)
        for s1, s2 in zip(suggestions1, suggestions2):
            assert s1.type_id == s2.type_id
            assert s1.score == s2.score


def test_suggestions_limit(tmp_path):
    """Verificar que se respeta el límite de sugerencias."""
    test_id = str(uuid.uuid4())[:8]
    test_base_dir = tmp_path / f"data_{test_id}"
    test_base_dir.mkdir(parents=True, exist_ok=True)
    
    with patch('backend.repository.document_repository_store_v1.load_settings') as mock_settings:
        class MockSettings:
            repository_root_dir = str(test_base_dir / "repository")
        mock_settings.return_value = MockSettings()
        store = DocumentRepositoryStoreV1(base_dir=str(test_base_dir))
        
        # Crear múltiples tipos
        for i in range(5):
            test_type = DocumentTypeV1(
                type_id=f"TYPE_{i}",
                name=f"Type {i}",
                scope=DocumentScopeV1.company,
                active=True,
                platform_aliases=[f"T{i}"],
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
            tipo_doc="T0",
            elemento="Test"
        )
        
        suggestions = suggest_types(
            pending=pending,
            context={"company_key": "TEST_COMPANY"},
            limit=3,
            base_dir=test_base_dir
        )
        
        # Debe respetar el límite
        assert len(suggestions) <= 3
