"""
Política de decisión para AUTO-UPLOAD.

SPRINT C2.15: Clasifica items en AUTO_UPLOAD, REVIEW_REQUIRED, NO_MATCH
de forma pura (sin side-effects) y testeable.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import date as dt_date

from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.config import DATA_DIR


def evaluate_upload_policy(
    pending_item: Dict[str, Any],
    match_result: Dict[str, Any],
    company_key: str,
    person_key: Optional[str],
    only_target: bool,
    base_dir: str | Path = "data",
) -> Dict[str, Any]:
    """
    Evalúa política de decisión para determinar si un item puede ser auto-subido.
    
    Args:
        pending_item: Item pendiente con tipo_doc, elemento, empresa, etc.
        match_result: Resultado del matching con best_doc, candidates, confidence, etc.
        company_key: Clave de empresa para validar scope
        person_key: Clave de persona para validar scope (opcional)
        only_target: Si True, validar que el item pertenece al scope solicitado
        base_dir: Directorio base para acceder al repositorio
    
    Returns:
        Dict con:
        - decision: "AUTO_UPLOAD" | "REVIEW_REQUIRED" | "NO_MATCH"
        - reason_code: string estable (ej: "no_local_match", "match_ok", "missing_local_file")
        - reason: string humana (1 línea)
        - confidence: 0..1
        - required_inputs: [] (si hace falta algo)
        - local_doc_ref: Dict con doc_id, type_id, file_name (si hay match)
    """
    best_doc = match_result.get("best_doc")
    confidence = match_result.get("confidence", 0.0)
    candidates = match_result.get("candidates", [])
    
    # Inicializar resultado
    result = {
        "decision": "NO_MATCH",
        "reason_code": "no_local_match",
        "reason": "No matching document found in local repository",
        "confidence": 0.0,
        "required_inputs": [],
        "local_doc_ref": None,
    }
    
    # Regla 1: Si NO hay match local -> NO_MATCH
    if not best_doc:
        # Verificar si hay múltiples candidatos (ambigüedad)
        if len(candidates) > 1:
            result["decision"] = "REVIEW_REQUIRED"
            result["reason_code"] = "ambiguous_match"
            result["reason"] = f"Multiple potential matches found ({len(candidates)} candidates), requires manual review"
            result["confidence"] = confidence
        else:
            result["decision"] = "NO_MATCH"
            result["reason_code"] = "no_local_match"
            result["reason"] = "No matching document found in local repository"
            result["confidence"] = 0.0
        return result
    
    # Hay match, obtener información del documento
    doc_id = best_doc.get("doc_id")
    type_id = best_doc.get("type_id")
    file_name = best_doc.get("file_name")
    
    if not doc_id:
        result["decision"] = "REVIEW_REQUIRED"
        result["reason_code"] = "missing_doc_id"
        result["reason"] = "Match found but document ID is missing"
        result["confidence"] = confidence
        return result
    
    # Regla 2: Si hay match pero falta archivo / path inválido -> REVIEW_REQUIRED
    repo_store = DocumentRepositoryStoreV1(base_dir=base_dir)
    try:
        # Verificar que el documento existe en el repositorio
        doc = repo_store.get_document(doc_id)
        if not doc:
            result["decision"] = "REVIEW_REQUIRED"
            result["reason_code"] = "missing_local_file"
            result["reason"] = f"Document {doc_id} not found in repository"
            result["confidence"] = confidence
            result["local_doc_ref"] = {
                "doc_id": doc_id,
                "type_id": type_id,
                "file_name": file_name,
            }
            return result
        
        # Verificar que el archivo PDF existe
        pdf_path = repo_store._get_doc_pdf_path(doc_id)
        if not pdf_path or not pdf_path.exists():
            result["decision"] = "REVIEW_REQUIRED"
            result["reason_code"] = "missing_local_file"
            result["reason"] = f"PDF file not found for document {doc_id} at {pdf_path}"
            result["confidence"] = confidence
            result["local_doc_ref"] = {
                "doc_id": doc_id,
                "type_id": type_id,
                "file_name": file_name,
            }
            return result
    except Exception as e:
        result["decision"] = "REVIEW_REQUIRED"
        result["reason_code"] = "repo_error"
        result["reason"] = f"Error accessing repository: {str(e)}"
        result["confidence"] = confidence
        return result
    
    # Regla 3: Validar scope (si only_target=True)
    if only_target:
        # Verificar que el item pertenece al scope solicitado
        empresa = pending_item.get("empresa") or ""
        elemento = pending_item.get("elemento") or ""
        
        # Validar empresa
        from backend.shared.text_normalizer import extract_company_code, normalize_company_name, normalize_text, text_contains
        
        empresa_match = True
        if company_key and empresa:
            company_code = extract_company_code(empresa)
            if company_code:
                company_key_upper = company_key.strip().upper().replace(' ', '')
                if company_key_upper != company_code:
                    empresa_norm = normalize_company_name(empresa)
                    company_key_norm = normalize_text(company_key)
                    empresa_match = text_contains(empresa_norm, company_key_norm)
            else:
                empresa_norm = normalize_company_name(empresa)
                company_key_norm = normalize_text(company_key)
                empresa_match = text_contains(empresa_norm, company_key_norm)
        
        # Validar persona (si person_key está presente)
        elemento_match = True
        if person_key and elemento:
            elemento_norm = normalize_text(elemento)
            person_key_norm = normalize_text(person_key)
            elemento_match = text_contains(elemento_norm, person_key_norm)
        
        if not empresa_match or not elemento_match:
            result["decision"] = "NO_MATCH"
            result["reason_code"] = "scope_mismatch"
            result["reason"] = f"Item does not match requested scope (company={company_key}, person={person_key})"
            result["confidence"] = 0.0
            return result
    
    # Regla 4: Si hay ambigüedad (múltiples matches / conflicto de fechas / tipo dudoso) -> REVIEW_REQUIRED
    # Verificar si hay múltiples matches con confianza similar
    if len(candidates) >= 2:
        # Obtener scores de los candidatos
        candidate_scores = []
        for cand in candidates[:2]:  # Solo los primeros 2
            score = cand.get("score", 0.0) if isinstance(cand, dict) else 0.0
            candidate_scores.append(score)
        
        if len(candidate_scores) >= 2:
            top_confidence = candidate_scores[0]
            second_confidence = candidate_scores[1]
            
            # Si la diferencia es pequeña (< 0.1), considerar ambigüedad
            if abs(top_confidence - second_confidence) < 0.1:
                result["decision"] = "REVIEW_REQUIRED"
                result["reason_code"] = "ambiguous_match"
                result["reason"] = f"Multiple matches with similar confidence ({top_confidence:.2f} vs {second_confidence:.2f})"
                result["confidence"] = confidence
                result["local_doc_ref"] = {
                    "doc_id": doc_id,
                    "type_id": type_id,
                    "file_name": file_name,
                }
                return result
    
    # Regla 5: Si hay match y el tipo está permitido y el archivo existe -> AUTO_UPLOAD
    # (Ya verificamos que el archivo existe arriba)
    result["decision"] = "AUTO_UPLOAD"
    result["reason_code"] = "match_ok"
    result["reason"] = f"Match found with confidence {confidence:.2f}, file exists and ready for upload"
    result["confidence"] = confidence
    result["local_doc_ref"] = {
        "doc_id": doc_id,
        "type_id": type_id,
        "file_name": file_name,
    }
    
    return result
