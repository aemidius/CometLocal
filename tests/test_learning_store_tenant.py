"""
SPRINT C2.22B: Tests para LearningStore con tenant scoping.
"""
import pytest
import tempfile
import shutil
from pathlib import Path
import json

from backend.shared.learning_store import LearningStore, LearnedHintV1, HintStrength


@pytest.fixture
def temp_base_dir():
    """Fixture con directorio temporal."""
    temp_dir = tempfile.mkdtemp()
    base_dir = Path(temp_dir)
    yield base_dir
    shutil.rmtree(temp_dir)


def test_learning_store_write_creates_tenant_dir(temp_base_dir):
    """Test: Escritura crea carpeta tenant."""
    store = LearningStore(base_dir=temp_base_dir, tenant_id="tenantA")
    
    # Crear un hint
    hint = LearnedHintV1.create(
        plan_id="plan123",
        decision_pack_id="pack456",
        item_fingerprint="fingerprint123",
        type_id_expected="T104",
        local_doc_id="doc789",
        local_doc_fingerprint=None,
        subject_key="COMPANY123",
        person_key="PERSON123",
        period_key="2025-01",
        portal_type_label_normalized="T104",
    )
    
    # Añadir hint
    added_ids = store.add_hints([hint])
    
    # Verificar que se creó en tenant path
    tenant_learning_dir = temp_base_dir / "tenants" / "tenantA" / "learning"
    assert tenant_learning_dir.exists()
    assert (tenant_learning_dir / "hints_v1.jsonl").exists()
    assert len(added_ids) == 1


def test_learning_store_read_uses_tenant_if_exists(temp_base_dir):
    """Test: Lectura usa tenant si existe."""
    # Crear hint en tenant path
    tenant_learning_dir = temp_base_dir / "tenants" / "tenantA" / "learning"
    tenant_learning_dir.mkdir(parents=True, exist_ok=True)
    
    hint = LearnedHintV1.create(
        plan_id="plan123",
        decision_pack_id="pack456",
        item_fingerprint="fingerprint123",
        type_id_expected="T104",
        local_doc_id="doc789",
        local_doc_fingerprint=None,
        subject_key="COMPANY123",
        person_key="PERSON123",
        period_key="2025-01",
        portal_type_label_normalized="T104",
    )
    
    # Escribir directamente en tenant path
    hints_file = tenant_learning_dir / "hints_v1.jsonl"
    with open(hints_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(hint.model_dump(mode="json")) + "\n")
    
    # Leer con store
    store = LearningStore(base_dir=temp_base_dir, tenant_id="tenantA")
    hints = store.list_hints()
    
    # Debe encontrar el hint del tenant
    assert len(hints) == 1
    assert hints[0].hint_id == hint.hint_id


def test_learning_store_read_fallback_legacy(temp_base_dir):
    """Test: Fallback legacy si tenant no existe."""
    # Crear hint en legacy path
    legacy_learning_dir = temp_base_dir / "learning"
    legacy_learning_dir.mkdir(parents=True, exist_ok=True)
    
    hint = LearnedHintV1.create(
        plan_id="plan123",
        decision_pack_id="pack456",
        item_fingerprint="fingerprint123",
        type_id_expected="T104",
        local_doc_id="doc789",
        local_doc_fingerprint=None,
        subject_key="COMPANY123",
        person_key="PERSON123",
        period_key="2025-01",
        portal_type_label_normalized="T104",
    )
    
    # Escribir directamente en legacy path
    hints_file = legacy_learning_dir / "hints_v1.jsonl"
    with open(hints_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(hint.model_dump(mode="json")) + "\n")
    
    # Leer con store (tenant no existe aún)
    store = LearningStore(base_dir=temp_base_dir, tenant_id="tenantB")
    hints = store.list_hints()
    
    # Debe encontrar el hint del legacy (fallback)
    assert len(hints) == 1
    assert hints[0].hint_id == hint.hint_id


def test_learning_store_no_mix_tenants(temp_base_dir):
    """Test: No mezcla datos entre tenants."""
    # Crear hints en tenantA
    store_a = LearningStore(base_dir=temp_base_dir, tenant_id="tenantA")
    hint_a = LearnedHintV1.create(
        plan_id="planA",
        decision_pack_id="packA",
        item_fingerprint="fingerprintA",
        type_id_expected="T104",
        local_doc_id="docA",
        local_doc_fingerprint=None,
        subject_key="COMPANY_A",
        person_key="PERSON_A",
        period_key="2025-01",
        portal_type_label_normalized="T104",
    )
    store_a.add_hints([hint_a])
    
    # Crear hints en tenantB
    store_b = LearningStore(base_dir=temp_base_dir, tenant_id="tenantB")
    hint_b = LearnedHintV1.create(
        plan_id="planB",
        decision_pack_id="packB",
        item_fingerprint="fingerprintB",
        type_id_expected="T105",
        local_doc_id="docB",
        local_doc_fingerprint=None,
        subject_key="COMPANY_B",
        person_key="PERSON_B",
        period_key="2025-02",
        portal_type_label_normalized="T105",
    )
    store_b.add_hints([hint_b])
    
    # Verificar aislamiento
    hints_a = store_a.list_hints()
    hints_b = store_b.list_hints()
    
    assert len(hints_a) == 1
    assert len(hints_b) == 1
    assert hints_a[0].hint_id == hint_a.hint_id
    assert hints_b[0].hint_id == hint_b.hint_id
    assert hints_a[0].hint_id != hints_b[0].hint_id
