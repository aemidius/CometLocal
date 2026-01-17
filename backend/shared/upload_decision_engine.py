"""
Motor de decisión explícita para uploads.

SPRINT C2.17: Decisión consciente y trazable por documento.
Separa responsabilidades: PLAN → DECISION → EXECUTION
"""
from __future__ import annotations

from typing import Dict, Any, List, Optional
from enum import Enum
import hashlib
import json


class UploadDecision(str, Enum):
    """Decisiones explícitas permitidas."""
    AUTO_UPLOAD = "AUTO_UPLOAD"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    SKIPPED = "SKIPPED"
    NO_MATCH = "NO_MATCH"


def calculate_confidence(
    match_result: Dict[str, Any],
    has_file: bool,
    has_ambiguity: bool = False,
) -> float:
    """
    Calcula confianza de la decisión.
    
    Args:
        match_result: Resultado del matching
        has_file: Si el archivo local existe
        has_ambiguity: Si hay ambigüedad (múltiples matches similares)
    
    Returns:
        Confianza entre 0.0 y 1.0
    """
    if not match_result or not match_result.get("best_doc"):
        return 0.0
    
    base_confidence = match_result.get("confidence", 0.0)
    
    # Penalizar si no hay archivo
    if not has_file:
        base_confidence *= 0.5
    
    # Penalizar ambigüedad
    if has_ambiguity:
        base_confidence *= 0.7
    
    return min(1.0, max(0.0, base_confidence))


def make_upload_decision(
    pending_item: Dict[str, Any],
    match_result: Dict[str, Any],
    company_key: str,
    person_key: Optional[str] = None,
    only_target: bool = True,
    base_dir: str = "data",
    user_override: Optional[UploadDecision] = None,  # SPRINT C2.17: Override manual
) -> Dict[str, Any]:
    """
    Toma decisión explícita sobre un item del plan.
    
    SPRINT C2.17: Decisión consciente y trazable.
    
    Args:
        pending_item: Item pendiente del plan
        match_result: Resultado del matching
        company_key: Clave de empresa
        person_key: Clave de persona (opcional)
        only_target: Solo items target
        base_dir: Directorio base
        user_override: Decisión forzada por usuario (SKIPPED, etc.)
    
    Returns:
        {
            "decision": UploadDecision,
            "decision_reason": str,
            "confidence": float,
            "match_result": match_result,
            "local_doc_ref": {...} | None,
            "blocking_issues": List[str],
        }
    """
    # SPRINT C2.17: Si hay override manual, respetarlo
    if user_override:
        return {
            "decision": user_override.value,
            "decision_reason": f"User override: {user_override.value}",
            "confidence": 1.0 if user_override == UploadDecision.SKIPPED else 0.0,
            "match_result": match_result,
            "local_doc_ref": None,
            "blocking_issues": [],
        }
    
    # Regla 1: Sin match → NO_MATCH
    if not match_result or not match_result.get("best_doc"):
        return {
            "decision": UploadDecision.NO_MATCH.value,
            "decision_reason": "No matching document found in local repository",
            "confidence": 0.0,
            "match_result": match_result or {},
            "local_doc_ref": None,
            "blocking_issues": ["no_match"],
        }
    
    best_doc = match_result.get("best_doc", {})
    candidates = match_result.get("candidates", [])
    
    # Verificar que el archivo existe
    from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
    from backend.repository.data_bootstrap_v1 import ensure_data_layout
    
    ensure_data_layout(base_dir=base_dir)
    doc_repo = DocumentRepositoryStoreV1(base_dir=base_dir)
    
    doc_id = best_doc.get("doc_id")
    file_exists = False
    local_doc_ref = None
    
    if doc_id:
        doc = doc_repo.get_document(doc_id)
        if doc:
            file_path = doc.get("file_path")
            if file_path:
                from pathlib import Path
                file_exists = Path(file_path).exists()
                if file_exists:
                    local_doc_ref = {
                        "doc_id": doc_id,
                        "type_id": best_doc.get("type_id"),
                        "file_name": Path(file_path).name,
                        "file_path": file_path,
                    }
    
    # Regla 2: Sin archivo → REVIEW_REQUIRED
    if not file_exists:
        return {
            "decision": UploadDecision.REVIEW_REQUIRED.value,
            "decision_reason": f"Match found (confidence={match_result.get('confidence', 0.0):.2f}) but local file missing",
            "confidence": calculate_confidence(match_result, has_file=False),
            "match_result": match_result,
            "local_doc_ref": None,
            "blocking_issues": ["file_missing"],
        }
    
    # Regla 3: Ambigüedad (múltiples matches similares) → REVIEW_REQUIRED
    if len(candidates) >= 2:
        candidate_scores = []
        for cand in candidates[:2]:
            score = cand.get("score", 0.0) if isinstance(cand, dict) else 0.0
            candidate_scores.append(score)
        
        if len(candidate_scores) >= 2:
            top_confidence = candidate_scores[0]
            second_confidence = candidate_scores[1]
            
            # Si la diferencia es pequeña (< 0.1), considerar ambigüedad
            if abs(top_confidence - second_confidence) < 0.1:
                return {
                    "decision": UploadDecision.REVIEW_REQUIRED.value,
                    "decision_reason": f"Ambiguous match: multiple candidates with similar confidence ({top_confidence:.2f} vs {second_confidence:.2f})",
                    "confidence": calculate_confidence(match_result, has_file=True, has_ambiguity=True),
                    "match_result": match_result,
                    "local_doc_ref": local_doc_ref,
                    "blocking_issues": ["ambiguous_match"],
                }
    
    # Regla 4: Verificar scope (only_target)
    if only_target:
        tipo_doc = pending_item.get("tipo_doc", "").upper()
        # Verificar si es tipo target (lógica simplificada, puede mejorarse)
        # Por ahora, si hay match y archivo, asumimos que es target
        pass  # TODO: Validar scope más estrictamente si es necesario
    
    # Regla 5: Match exacto + archivo presente → AUTO_UPLOAD
    confidence = calculate_confidence(match_result, has_file=True, has_ambiguity=False)
    
    return {
        "decision": UploadDecision.AUTO_UPLOAD.value,
        "decision_reason": f"Exact match (confidence={match_result.get('confidence', 0.0):.2f}) + file present + valid dates",
        "confidence": confidence,
        "match_result": match_result,
        "local_doc_ref": local_doc_ref,
        "blocking_issues": [],
    }


def generate_plan_id(plan_content: Dict[str, Any]) -> str:
    """
    Genera plan_id estable (hash del contenido).
    
    SPRINT C2.17: Plan congelado e inmutable.
    
    Args:
        plan_content: Contenido del plan (snapshot + decisions)
    
    Returns:
        plan_id (hash hexadecimal)
    """
    # Normalizar contenido para hash estable
    normalized = {
        "snapshot": plan_content.get("snapshot", {}),
        "decisions": plan_content.get("decisions", []),
    }
    
    # Convertir a JSON estable (sorted keys)
    json_str = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    
    # Hash SHA256
    hash_obj = hashlib.sha256(json_str.encode("utf-8"))
    plan_id = hash_obj.hexdigest()[:16]  # Primeros 16 caracteres
    
    return f"plan_{plan_id}"


def apply_decisions_to_plan(
    plan_items: List[Dict[str, Any]],
    match_results: List[Dict[str, Any]],
    company_key: str,
    person_key: Optional[str] = None,
    only_target: bool = True,
    base_dir: str = "data",
    user_overrides: Optional[Dict[str, UploadDecision]] = None,  # SPRINT C2.17: Overrides por pending_item_key
) -> List[Dict[str, Any]]:
    """
    Aplica decisiones a todos los items del plan.
    
    SPRINT C2.17: Congela decisiones en el plan.
    
    Args:
        plan_items: Items del plan
        match_results: Resultados de matching
        company_key: Clave de empresa
        person_key: Clave de persona (opcional)
        only_target: Solo items target
        base_dir: Directorio base
        user_overrides: Overrides manuales por pending_item_key
    
    Returns:
        Lista de decisiones [{pending_item_key, decision, decision_reason, confidence, ...}]
    """
    # Crear mapa de match_results por pending_item_key
    match_map = {}
    for match_item in match_results:
        pending_item = match_item.get("pending_item", {})
        pending_item_key = pending_item.get("pending_item_key")
        if pending_item_key:
            match_map[pending_item_key] = match_item.get("match_result", {})
    
    # También buscar en plan_items
    for plan_item in plan_items:
        pending_ref = plan_item.get("pending_ref", {})
        pending_item_key = pending_ref.get("pending_item_key") or plan_item.get("pending_item_key")
        if pending_item_key and pending_item_key not in match_map:
            matched_doc = plan_item.get("matched_doc", {})
            if matched_doc:
                match_map[pending_item_key] = {
                    "best_doc": matched_doc,
                    "confidence": matched_doc.get("validity", {}).get("confidence", 0.0),
                    "candidates": [],
                }
    
    decisions = []
    
    for plan_item in plan_items:
        pending_ref = plan_item.get("pending_ref", {})
        pending_item_key = pending_ref.get("pending_item_key") or plan_item.get("pending_item_key")
        
        if not pending_item_key:
            # Construir pending_item_key si no existe
            from backend.adapters.egestiona.grid_extract import canonicalize_row
            tipo_doc = pending_ref.get("tipo_doc", "")
            elemento = pending_ref.get("elemento", "")
            empresa = pending_ref.get("empresa", "")
            fallback_row = {
                "Tipo Documento": tipo_doc,
                "Elemento": elemento,
                "Empresa": empresa,
            }
            canonical = canonicalize_row(fallback_row)
            pending_item_key = canonical.get("pending_item_key")
        
        # Obtener match_result
        match_result = match_map.get(pending_item_key, {})
        
        # Construir pending_item dict
        pending_item_dict = {
            "tipo_doc": pending_ref.get("tipo_doc"),
            "elemento": pending_ref.get("elemento"),
            "empresa": pending_ref.get("empresa"),
        }
        
        # Obtener override si existe
        user_override = None
        if user_overrides and pending_item_key in user_overrides:
            user_override = user_overrides[pending_item_key]
        
        # Tomar decisión
        decision_result = make_upload_decision(
            pending_item=pending_item_dict,
            match_result=match_result,
            company_key=company_key,
            person_key=person_key,
            only_target=only_target,
            base_dir=base_dir,
            user_override=user_override,
        )
        
        # Añadir pending_item_key a la decisión
        decision_result["pending_item_key"] = pending_item_key
        
        decisions.append(decision_result)
    
    return decisions
