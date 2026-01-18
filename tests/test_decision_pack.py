"""
SPRINT C2.18B: Tests para Decision Pack.
"""
import pytest
from pathlib import Path
import json
import tempfile
import shutil

from backend.shared.decision_pack import (
    DecisionPackV1,
    ManualDecisionV1,
    ManualDecisionAction,
)
from backend.shared.decision_pack_store import DecisionPackStore


@pytest.fixture
def temp_store(tmp_path):
    """Fixture con store temporal."""
    return DecisionPackStore(base_dir=tmp_path)


@pytest.fixture
def sample_plan_id():
    """Plan ID de ejemplo."""
    return "plan_abc123"


@pytest.fixture
def sample_plan_dir(tmp_path, sample_plan_id):
    """Crea un plan de ejemplo en tmp_path."""
    plan_dir = tmp_path / "runs" / sample_plan_id
    plan_dir.mkdir(parents=True, exist_ok=True)
    
    # Crear plan_response.json básico
    plan_data = {
        "snapshot": {
            "items": [
                {"pending_item_key": "item1", "tipo_doc": "T205.0"},
                {"pending_item_key": "item2", "tipo_doc": "T104"},
            ]
        },
        "decisions": [
            {
                "pending_item_key": "item1",
                "decision": "NO_MATCH",
                "reason": "No match found",
            },
            {
                "pending_item_key": "item2",
                "decision": "REVIEW_REQUIRED",
                "reason": "Low confidence",
            },
        ],
    }
    
    plan_path = plan_dir / "plan_response.json"
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan_data, f)
    
    return plan_dir


def test_create_decision_pack_stable_id(temp_store, sample_plan_id, sample_plan_dir):
    """Test: decision_pack_id debe ser estable para el mismo contenido."""
    decisions = [
        ManualDecisionV1(
            item_id="item1",
            action=ManualDecisionAction.SKIP,
            reason="Manual skip test",
        ),
    ]
    
    pack1 = DecisionPackV1.create(plan_id=sample_plan_id, decisions=decisions)
    pack2 = DecisionPackV1.create(plan_id=sample_plan_id, decisions=decisions)
    
    # Los IDs deben ser iguales
    assert pack1.decision_pack_id == pack2.decision_pack_id
    
    # Guardar y cargar
    temp_store.save_pack(pack1)
    loaded = temp_store.load_pack(sample_plan_id, pack1.decision_pack_id)
    
    assert loaded is not None
    assert loaded.decision_pack_id == pack1.decision_pack_id
    assert len(loaded.decisions) == 1
    assert loaded.decisions[0].item_id == "item1"
    assert loaded.decisions[0].action == ManualDecisionAction.SKIP


def test_apply_mark_as_match_override(temp_store, sample_plan_id, sample_plan_dir):
    """Test: MARK_AS_MATCH convierte NO_MATCH en AUTO_UPLOAD."""
    # Cargar decisiones del plan
    plan_path = sample_plan_dir / "plan_response.json"
    with open(plan_path, "r", encoding="utf-8") as f:
        plan_data = json.load(f)
    
    plan_decisions = plan_data["decisions"]
    
    # Crear override MARK_AS_MATCH para item1
    decisions = [
        ManualDecisionV1(
            item_id="item1",
            action=ManualDecisionAction.MARK_AS_MATCH,
            chosen_local_doc_id="doc123",
            reason="Manual match",
        ),
    ]
    
    pack = DecisionPackV1.create(plan_id=sample_plan_id, decisions=decisions)
    modified = pack.apply_to_decisions(plan_decisions)
    
    # item1 debe ser AUTO_UPLOAD
    item1_decision = next(d for d in modified if d.get("pending_item_key") == "item1")
    assert item1_decision["decision"] == "AUTO_UPLOAD"
    assert item1_decision["local_doc_id"] == "doc123"
    assert "manual_override" in item1_decision
    
    # item2 debe mantener su decisión original
    item2_decision = next(d for d in modified if d.get("pending_item_key") == "item2")
    assert item2_decision["decision"] == "REVIEW_REQUIRED"


def test_apply_skip_override(temp_store, sample_plan_id, sample_plan_dir):
    """Test: SKIP convierte cualquier decisión en DO_NOT_UPLOAD."""
    plan_path = sample_plan_dir / "plan_response.json"
    with open(plan_path, "r", encoding="utf-8") as f:
        plan_data = json.load(f)
    
    plan_decisions = plan_data["decisions"]
    
    decisions = [
        ManualDecisionV1(
            item_id="item2",
            action=ManualDecisionAction.SKIP,
            reason="Manual skip",
        ),
    ]
    
    pack = DecisionPackV1.create(plan_id=sample_plan_id, decisions=decisions)
    modified = pack.apply_to_decisions(plan_decisions)
    
    item2_decision = next(d for d in modified if d.get("pending_item_key") == "item2")
    assert item2_decision["decision"] == "DO_NOT_UPLOAD"
    assert "manual_override" in item2_decision


def test_apply_force_upload_override(temp_store, sample_plan_id, sample_plan_dir):
    """Test: FORCE_UPLOAD convierte en AUTO_UPLOAD con chosen_file_path."""
    plan_path = sample_plan_dir / "plan_response.json"
    with open(plan_path, "r", encoding="utf-8") as f:
        plan_data = json.load(f)
    
    plan_decisions = plan_data["decisions"]
    
    decisions = [
        ManualDecisionV1(
            item_id="item1",
            action=ManualDecisionAction.FORCE_UPLOAD,
            chosen_file_path="/path/to/file.pdf",
            reason="Force upload",
        ),
    ]
    
    pack = DecisionPackV1.create(plan_id=sample_plan_id, decisions=decisions)
    modified = pack.apply_to_decisions(plan_decisions)
    
    item1_decision = next(d for d in modified if d.get("pending_item_key") == "item1")
    assert item1_decision["decision"] == "AUTO_UPLOAD"
    assert item1_decision["chosen_file_path"] == "/path/to/file.pdf"


def test_plan_id_stability_with_decision_pack(temp_store, sample_plan_id, sample_plan_dir):
    """Test: El plan_id no cambia aunque se cree un Decision Pack."""
    from backend.shared.upload_decision_engine import generate_plan_id
    
    plan_path = sample_plan_dir / "plan_response.json"
    with open(plan_path, "r", encoding="utf-8") as f:
        plan_data = json.load(f)
    
    # Generar plan_id original
    plan_id_1 = generate_plan_id({
        "snapshot": plan_data["snapshot"],
        "decisions": plan_data["decisions"],
    })
    
    # Crear Decision Pack
    decisions = [
        ManualDecisionV1(
            item_id="item1",
            action=ManualDecisionAction.SKIP,
            reason="Skip",
        ),
    ]
    pack = DecisionPackV1.create(plan_id=sample_plan_id, decisions=decisions)
    temp_store.save_pack(pack)
    
    # Aplicar overrides
    modified_decisions = pack.apply_to_decisions(plan_data["decisions"])
    
    # El plan_id debe seguir siendo el mismo (no se modifica el plan original)
    plan_id_2 = generate_plan_id({
        "snapshot": plan_data["snapshot"],
        "decisions": plan_data["decisions"],  # Decisiones originales, no modificadas
    })
    
    assert plan_id_1 == plan_id_2  # El plan_id no cambia


def test_list_packs(temp_store, sample_plan_id, sample_plan_dir):
    """Test: list_packs devuelve lista de packs."""
    decisions1 = [
        ManualDecisionV1(
            item_id="item1",
            action=ManualDecisionAction.SKIP,
            reason="Skip 1",
        ),
    ]
    pack1 = DecisionPackV1.create(plan_id=sample_plan_id, decisions=decisions1)
    temp_store.save_pack(pack1)
    
    decisions2 = [
        ManualDecisionV1(
            item_id="item2",
            action=ManualDecisionAction.SKIP,
            reason="Skip 2",
        ),
    ]
    pack2 = DecisionPackV1.create(plan_id=sample_plan_id, decisions=decisions2)
    temp_store.save_pack(pack2)
    
    packs = temp_store.list_packs(sample_plan_id)
    assert len(packs) == 2
    pack_ids = {p["decision_pack_id"] for p in packs}
    assert pack1.decision_pack_id in pack_ids
    assert pack2.decision_pack_id in pack_ids
