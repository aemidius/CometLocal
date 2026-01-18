"""
SPRINT C2.22B: Tests para DecisionPresetStore con tenant scoping.
"""
import pytest
import tempfile
import shutil
from pathlib import Path
import json

from backend.shared.decision_preset_store import DecisionPresetStore
from backend.shared.decision_preset import DecisionPresetV1, DecisionPresetScope, DecisionPresetDefaults
from backend.shared.decision_pack import ManualDecisionAction


@pytest.fixture
def temp_base_dir():
    """Fixture con directorio temporal."""
    temp_dir = tempfile.mkdtemp()
    base_dir = Path(temp_dir)
    yield base_dir
    shutil.rmtree(temp_dir)


def test_preset_store_write_creates_tenant_dir(temp_base_dir):
    """Test: Escritura crea carpeta tenant."""
    store = DecisionPresetStore(base_dir=temp_base_dir, tenant_id="tenantA")
    
    # Crear un preset
    preset = DecisionPresetV1.create(
        name="Test Preset",
        scope=DecisionPresetScope(
            platform="egestiona",
            type_id="T104",
            subject_key=None,
            period_key=None,
        ),
        action=ManualDecisionAction.SKIP,
        defaults=DecisionPresetDefaults(reason="Test reason"),
    )
    
    # Guardar preset
    preset_id = store.upsert_preset(preset)
    
    # Verificar que se creó en tenant path
    tenant_presets_dir = temp_base_dir / "tenants" / "tenantA" / "presets"
    assert tenant_presets_dir.exists()
    assert (tenant_presets_dir / "decision_presets_v1.json").exists()
    assert preset_id == preset.preset_id


def test_preset_store_read_uses_tenant_if_exists(temp_base_dir):
    """Test: Lectura usa tenant si existe."""
    # Crear preset en tenant path
    tenant_presets_dir = temp_base_dir / "tenants" / "tenantA" / "presets"
    tenant_presets_dir.mkdir(parents=True, exist_ok=True)
    
    preset = DecisionPresetV1.create(
        name="Test Preset",
        scope=DecisionPresetScope(
            platform="egestiona",
            type_id="T104",
            subject_key=None,
            period_key=None,
        ),
        action=ManualDecisionAction.SKIP,
        defaults=DecisionPresetDefaults(reason="Test reason"),
    )
    
    # Escribir directamente en tenant path
    presets_file = tenant_presets_dir / "decision_presets_v1.json"
    with open(presets_file, "w", encoding="utf-8") as f:
        json.dump({
            "presets": [preset.model_dump(mode="json")],
            "updated_at": "2025-01-01T00:00:00Z",
        }, f, indent=2)
    
    # Leer con store
    store = DecisionPresetStore(base_dir=temp_base_dir, tenant_id="tenantA")
    presets = store.list_presets()
    
    # Debe encontrar el preset del tenant
    assert len(presets) == 1
    assert presets[0].preset_id == preset.preset_id


def test_preset_store_read_fallback_legacy(temp_base_dir):
    """Test: Fallback legacy si tenant no existe."""
    # Crear preset en legacy path
    legacy_presets_dir = temp_base_dir / "presets"
    legacy_presets_dir.mkdir(parents=True, exist_ok=True)
    
    preset = DecisionPresetV1.create(
        name="Legacy Preset",
        scope=DecisionPresetScope(
            platform="egestiona",
            type_id="T105",
            subject_key=None,
            period_key=None,
        ),
        action=ManualDecisionAction.SKIP,
        defaults=DecisionPresetDefaults(reason="Legacy reason"),
    )
    
    # Escribir directamente en legacy path
    presets_file = legacy_presets_dir / "decision_presets_v1.json"
    with open(presets_file, "w", encoding="utf-8") as f:
        json.dump({
            "presets": [preset.model_dump(mode="json")],
            "updated_at": "2025-01-01T00:00:00Z",
        }, f, indent=2)
    
    # Leer con store (tenant no existe aún)
    store = DecisionPresetStore(base_dir=temp_base_dir, tenant_id="tenantB")
    presets = store.list_presets()
    
    # Debe encontrar el preset del legacy (fallback)
    assert len(presets) == 1
    assert presets[0].preset_id == preset.preset_id


def test_preset_store_no_mix_tenants(temp_base_dir):
    """Test: No mezcla datos entre tenants."""
    # Crear preset en tenantA
    store_a = DecisionPresetStore(base_dir=temp_base_dir, tenant_id="tenantA")
    preset_a = DecisionPresetV1.create(
        name="Preset A",
        scope=DecisionPresetScope(
            platform="egestiona",
            type_id="T104",
            subject_key=None,
            period_key=None,
        ),
        action=ManualDecisionAction.SKIP,
        defaults=DecisionPresetDefaults(reason="Reason A"),
    )
    store_a.upsert_preset(preset_a)
    
    # Crear preset en tenantB
    store_b = DecisionPresetStore(base_dir=temp_base_dir, tenant_id="tenantB")
    preset_b = DecisionPresetV1.create(
        name="Preset B",
        scope=DecisionPresetScope(
            platform="egestiona",
            type_id="T105",
            subject_key=None,
            period_key=None,
        ),
        action=ManualDecisionAction.SKIP,
        defaults=DecisionPresetDefaults(reason="Reason B"),
    )
    store_b.upsert_preset(preset_b)
    
    # Verificar aislamiento
    presets_a = store_a.list_presets()
    presets_b = store_b.list_presets()
    
    assert len(presets_a) == 1
    assert len(presets_b) == 1
    assert presets_a[0].preset_id == preset_a.preset_id
    assert presets_b[0].preset_id == preset_b.preset_id
    assert presets_a[0].preset_id != presets_b[0].preset_id


def test_preset_id_stable_hash(temp_base_dir):
    """Test: Hash estable no cambia con tenant."""
    # Mismo preset en diferentes tenants debe tener mismo preset_id
    preset_data = {
        "name": "Same Preset",
        "scope": DecisionPresetScope(
            platform="egestiona",
            type_id="T104",
            subject_key=None,
            period_key=None,
        ),
        "action": ManualDecisionAction.SKIP,
        "defaults": DecisionPresetDefaults(reason="Same reason"),
    }
    
    store_a = DecisionPresetStore(base_dir=temp_base_dir, tenant_id="tenantA")
    preset_a = DecisionPresetV1.create(**preset_data)
    preset_id_a = store_a.upsert_preset(preset_a)
    
    store_b = DecisionPresetStore(base_dir=temp_base_dir, tenant_id="tenantB")
    preset_b = DecisionPresetV1.create(**preset_data)
    preset_id_b = store_b.upsert_preset(preset_b)
    
    # preset_id debe ser el mismo (hash del contenido, no del tenant)
    assert preset_id_a == preset_id_b
    assert preset_a.preset_id == preset_b.preset_id
