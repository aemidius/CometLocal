"""
SPRINT C2.19A: Generador de hints desde Decision Packs.

Genera LearnedHintV1 cuando se aplica un Decision Pack con MARK_AS_MATCH.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional
from pathlib import Path

from backend.shared.learning_store import LearnedHintV1, LearningStore
from backend.shared.decision_pack import DecisionPackV1, ManualDecisionAction
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.repository.submission_history_utils import compute_pending_fingerprint
from backend.shared.text_normalizer import normalize_text
from backend.config import DATA_DIR


def generate_hints_from_decision_pack(
    plan_id: str,
    decision_pack: DecisionPackV1,
    plan_data: Dict[str, Any],
) -> List[str]:
    """
    Genera hints desde un Decision Pack aplicado.
    
    Args:
        plan_id: ID del plan
        decision_pack: Decision Pack aplicado
        plan_data: Datos del plan (snapshot + decisions originales)
    
    Returns:
        Lista de hint_ids creados
    """
    store = LearningStore()
    doc_store = DocumentRepositoryStoreV1()
    snapshot_items = plan_data.get("snapshot", {}).get("items", [])
    original_decisions = plan_data.get("decisions", [])
    
    # Crear mapa de items por pending_item_key
    items_map = {}
    for item in snapshot_items:
        item_key = item.get("pending_item_key") or item.get("item_id")
        if item_key:
            items_map[item_key] = item
    
    # Crear mapa de decisiones originales por pending_item_key
    decisions_map = {}
    for decision in original_decisions:
        item_key = decision.get("pending_item_key") or decision.get("item_id")
        if item_key:
            decisions_map[item_key] = decision
    
    hints = []
    
    # Procesar cada decisión MARK_AS_MATCH
    for manual_decision in decision_pack.decisions:
        if manual_decision.action != ManualDecisionAction.MARK_AS_MATCH:
            continue
        
        if not manual_decision.chosen_local_doc_id:
            continue
        
        # Validar que el doc existe
        doc = doc_store.get_document(manual_decision.chosen_local_doc_id)
        if not doc or not doc.stored_path:
            print(f"[Learning] WARNING: Doc {manual_decision.chosen_local_doc_id} no existe o no tiene stored_path, saltando hint")
            continue
        
        # Obtener item del snapshot
        item = items_map.get(manual_decision.item_id)
        if not item:
            print(f"[Learning] WARNING: Item {manual_decision.item_id} no encontrado en snapshot, saltando hint")
            continue
        
        # Obtener decisión original para contexto
        original_decision = decisions_map.get(manual_decision.item_id, {})
        
        # Construir pending_item_dict para fingerprint
        pending_item_dict = {
            "tipo_doc": item.get("tipo_doc") or item.get("type_id"),
            "elemento": item.get("elemento") or item.get("person_key"),
            "empresa": item.get("empresa") or item.get("company_key"),
        }
        
        # Calcular fingerprint
        # Normalizar campos para fingerprint
        from backend.repository.submission_history_utils import normalize_text_for_fingerprint
        normalized_dict = {
            "tipo_doc": normalize_text_for_fingerprint(pending_item_dict.get("tipo_doc", "")),
            "elemento": normalize_text_for_fingerprint(pending_item_dict.get("elemento", "")),
            "empresa": normalize_text_for_fingerprint(pending_item_dict.get("empresa", "")),
        }
        item_fingerprint = compute_pending_fingerprint(
            platform_key="egestiona",  # Por ahora hardcodeado, se puede extraer del plan
            coord_label=None,
            pending_item_dict=normalized_dict,
        )
        
        # Extraer type_id esperado
        type_id_expected = None
        # Intentar desde item
        if item.get("type_id"):
            type_id_expected = item.get("type_id")
        # Intentar desde tipo_doc normalizado
        elif item.get("tipo_doc"):
            # Normalizar tipo_doc para buscar type_id
            tipo_doc = item.get("tipo_doc")
            # Por ahora usar el tipo_doc como está, el matcher lo resolverá
            type_id_expected = tipo_doc
        
        # Extraer subject keys
        subject_key = item.get("empresa") or item.get("company_key")
        person_key = item.get("elemento") or item.get("person_key")
        
        # Extraer period_key
        period_key = item.get("periodo") or item.get("period_key")
        
        # Extraer portal label normalizado (si existe)
        portal_type_label_normalized = None
        tipo_doc_raw = item.get("tipo_doc")
        if tipo_doc_raw:
            # Normalizar básico (se puede mejorar)
            from backend.shared.text_normalizer import normalize_text
            portal_type_label_normalized = normalize_text(tipo_doc_raw)
        
        # Calcular doc fingerprint (basename + size si está disponible)
        local_doc_fingerprint = None
        if doc.stored_path:
            stored_path = Path(doc.stored_path)
            basename = stored_path.name
            # Intentar obtener size si está disponible
            try:
                if stored_path.exists():
                    size = stored_path.stat().st_size
                    local_doc_fingerprint = f"{basename}:{size}"
            except Exception:
                local_doc_fingerprint = basename
        
        # Crear hint
        hint = LearnedHintV1.create(
            plan_id=plan_id,
            decision_pack_id=decision_pack.decision_pack_id,
            item_fingerprint=item_fingerprint,
            type_id_expected=type_id_expected or "UNKNOWN",
            local_doc_id=manual_decision.chosen_local_doc_id,
            local_doc_fingerprint=local_doc_fingerprint,
            subject_key=subject_key,
            person_key=person_key,
            period_key=period_key,
            portal_type_label_normalized=portal_type_label_normalized,
            notes=manual_decision.reason,
        )
        
        hints.append(hint)
    
    # Guardar hints (idempotente)
    if hints:
        hint_ids = store.add_hints(hints)
        
        # Guardar evidencia
        evidence_path = Path(DATA_DIR) / "runs" / plan_id / "decision_packs" / f"{decision_pack.decision_pack_id}__learned_hints.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        
        evidence = {
            "plan_id": plan_id,
            "decision_pack_id": decision_pack.decision_pack_id,
            "hints_created": hint_ids,
            "hints_data": [h.model_dump(mode="json") for h in hints],
        }
        
        with open(evidence_path, "w", encoding="utf-8") as f:
            import json
            json.dump(evidence, f, indent=2, ensure_ascii=False)
        
        print(f"[Learning] Generados {len(hint_ids)} hints desde Decision Pack {decision_pack.decision_pack_id}")
        return hint_ids
    
    return []
