"""
SPRINT C2.20A: Tests para Decision Presets.
"""
import pytest
from pathlib import Path
import tempfile
import shutil
import json

from backend.shared.decision_preset import (
    DecisionPresetV1,
    DecisionPresetScope,
    DecisionPresetDefaults,
)
from backend.shared.decision_pack import ManualDecisionAction
from backend.shared.decision_preset_store import DecisionPresetStore


@pytest.fixture
def temp_store(tmp_path):
    """Fixture con store temporal."""
    return DecisionPresetStore(base_dir=tmp_path)


def test_preset_id_stable_hash(temp_store):
    """Test: preset_id es estable (mismo contenido = mismo ID)."""
    scope1 = DecisionPresetScope(
        platform="egestiona",
        type_id="T104_AUTONOMOS_RECEIPT",
        subject_key=None,
        period_key=None,
    )
    
    preset1 = DecisionPresetV1.create(
        name="Skip T104",
        scope=scope1,
        action=ManualDecisionAction.SKIP,
        defaults=DecisionPresetDefaults(reason="No disponible"),
    )
    
    # Crear otro preset con mismo contenido
    scope2 = DecisionPresetScope(
        platform="egestiona",
        type_id="T104_AUTONOMOS_RECEIPT",
        subject_key=None,
        period_key=None,
    )
    
    preset2 = DecisionPresetV1.create(
        name="Skip T104 (otro nombre)",  # Nombre diferente, pero no afecta al hash
        scope=scope2,
        action=ManualDecisionAction.SKIP,
        defaults=DecisionPresetDefaults(reason="No disponible"),
    )
    
    # Debe tener el mismo preset_id
    assert preset1.preset_id == preset2.preset_id
    
    # Pero si cambia el scope o defaults, debe cambiar el ID
    scope3 = DecisionPresetScope(
        platform="egestiona",
        type_id="T104_AUTONOMOS_RECEIPT",
        subject_key="COMPANY123",  # Diferente
        period_key=None,
    )
    
    preset3 = DecisionPresetV1.create(
        name="Skip T104",
        scope=scope3,
        action=ManualDecisionAction.SKIP,
        defaults=DecisionPresetDefaults(reason="No disponible"),
    )
    
    assert preset1.preset_id != preset3.preset_id


def test_preset_store_upsert_and_list_filters(temp_store):
    """Test: Store puede crear/actualizar y listar con filtros."""
    scope = DecisionPresetScope(
        platform="egestiona",
        type_id="T104_AUTONOMOS_RECEIPT",
        subject_key="COMPANY123",
        period_key="2025-01",
    )
    
    preset = DecisionPresetV1.create(
        name="Skip T104 Company",
        scope=scope,
        action=ManualDecisionAction.SKIP,
        defaults=DecisionPresetDefaults(reason="No disponible"),
    )
    
    # Crear
    preset_id = temp_store.upsert_preset(preset)
    assert preset_id == preset.preset_id
    
    # Listar todos
    all_presets = temp_store.list_presets()
    assert len(all_presets) == 1
    assert all_presets[0].preset_id == preset_id
    
    # Filtrar por type_id
    filtered = temp_store.list_presets(type_id="T104_AUTONOMOS_RECEIPT")
    assert len(filtered) == 1
    
    filtered = temp_store.list_presets(type_id="T999_OTHER")
    assert len(filtered) == 0
    
    # Filtrar por subject_key
    filtered = temp_store.list_presets(subject_key="COMPANY123")
    assert len(filtered) == 1
    
    filtered = temp_store.list_presets(subject_key="COMPANY999")
    assert len(filtered) == 0
    
    # Filtrar por period_key
    filtered = temp_store.list_presets(period_key="2025-01")
    assert len(filtered) == 1
    
    # Actualizar (mismo preset_id)
    preset.name = "Skip T104 Company (Updated)"
    temp_store.upsert_preset(preset)
    
    updated = temp_store.list_presets()
    assert len(updated) == 1
    assert updated[0].name == "Skip T104 Company (Updated)"


def test_disable_preset(temp_store):
    """Test: Desactivar preset funciona correctamente."""
    scope = DecisionPresetScope(
        platform="egestiona",
        type_id="T104_AUTONOMOS_RECEIPT",
    )
    
    preset = DecisionPresetV1.create(
        name="Test Preset",
        scope=scope,
        action=ManualDecisionAction.SKIP,
    )
    
    preset_id = temp_store.upsert_preset(preset)
    
    # Verificar que está activo
    all_presets = temp_store.list_presets(include_disabled=False)
    assert len(all_presets) == 1
    
    # Desactivar
    success = temp_store.disable_preset(preset_id)
    assert success is True
    
    # Verificar que no aparece en lista normal
    all_presets = temp_store.list_presets(include_disabled=False)
    assert len(all_presets) == 0
    
    # Pero aparece si incluimos desactivados
    all_presets = temp_store.list_presets(include_disabled=True)
    assert len(all_presets) == 1
    assert all_presets[0].is_enabled is False


def test_preset_matches_item():
    """Test: matches_item funciona correctamente."""
    scope = DecisionPresetScope(
        platform="egestiona",
        type_id="T104_AUTONOMOS_RECEIPT",
        subject_key="COMPANY123",
        period_key="2025-01",
    )
    
    preset = DecisionPresetV1.create(
        name="Test Preset",
        scope=scope,
        action=ManualDecisionAction.SKIP,
    )
    
    # Match exacto
    assert preset.matches_item(
        item_type_id="T104_AUTONOMOS_RECEIPT",
        item_subject_key="COMPANY123",
        item_period_key="2025-01",
        platform="egestiona",
    ) is True
    
    # No match: type_id diferente
    assert preset.matches_item(
        item_type_id="T999_OTHER",
        item_subject_key="COMPANY123",
        item_period_key="2025-01",
        platform="egestiona",
    ) is False
    
    # No match: subject_key diferente
    assert preset.matches_item(
        item_type_id="T104_AUTONOMOS_RECEIPT",
        item_subject_key="COMPANY999",
        item_period_key="2025-01",
        platform="egestiona",
    ) is False
    
    # No match: period_key diferente
    assert preset.matches_item(
        item_type_id="T104_AUTONOMOS_RECEIPT",
        item_subject_key="COMPANY123",
        item_period_key="2025-02",
        platform="egestiona",
    ) is False
    
    # Preset sin subject_key: debe matchear cualquier subject
    scope2 = DecisionPresetScope(
        platform="egestiona",
        type_id="T104_AUTONOMOS_RECEIPT",
        subject_key=None,
        period_key=None,
    )
    
    preset2 = DecisionPresetV1.create(
        name="Test Preset 2",
        scope=scope2,
        action=ManualDecisionAction.SKIP,
    )
    
    assert preset2.matches_item(
        item_type_id="T104_AUTONOMOS_RECEIPT",
        item_subject_key="ANY_COMPANY",
        item_period_key="ANY_PERIOD",
        platform="egestiona",
    ) is True
