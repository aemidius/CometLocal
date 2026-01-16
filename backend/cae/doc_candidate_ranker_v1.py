"""
Ranker de candidatos de documentos para sugerencia automática.

Scoring determinista:
- exact_type_match (obligatorio): +100
- exact_subject_match (company/person): +50
- exact_period_match: +30
- recency (más reciente): +10 por mes de antigüedad (máx 60)
- status_bonus: reviewed/submitted +20, draft +0

El mejor candidato es el que tiene mayor score.
"""

from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass
class CandidateScore:
    """Score y razón para un candidato."""
    doc_id: str
    score: int
    reason_parts: List[str]
    
    def get_reason(self) -> str:
        """Genera una razón legible del score."""
        if not self.reason_parts:
            return "Sin coincidencias específicas"
        return "; ".join(self.reason_parts)


def rank_candidates(
    candidates: List[Dict[str, Any]],
    target_type_id: str,
    target_scope: str,
    target_company_key: Optional[str] = None,
    target_person_key: Optional[str] = None,
    target_period_key: Optional[str] = None,
) -> List[CandidateScore]:
    """
    Rankea candidatos según su relevancia para el target.
    
    Args:
        candidates: Lista de dicts con doc_id, type_id, scope, company_key, person_key, period_key, updated_at, status
        target_type_id: Tipo de documento objetivo
        target_scope: "company" | "worker"
        target_company_key: Empresa objetivo (opcional)
        target_person_key: Trabajador objetivo (opcional)
        target_period_key: Período objetivo en formato "YYYY-MM" (opcional)
    
    Returns:
        Lista de CandidateScore ordenada por score descendente.
    """
    scored: List[CandidateScore] = []
    
    for cand in candidates:
        doc_id = cand.get("doc_id", "")
        cand_type_id = cand.get("type_id", "")
        cand_scope = cand.get("scope", "")
        cand_company_key = cand.get("company_key")
        cand_person_key = cand.get("person_key")
        cand_period_key = cand.get("period_key")
        updated_at_str = cand.get("updated_at")
        status = cand.get("status", "").lower()
        
        score = 0
        reason_parts: List[str] = []
        
        # 1. Exact type match (obligatorio)
        if cand_type_id == target_type_id:
            score += 100
            reason_parts.append("Coincide tipo")
        else:
            # Si no coincide el tipo, no es candidato válido
            continue
        
        # 2. Exact subject match
        if target_scope == "worker":
            if cand_person_key and target_person_key and cand_person_key == target_person_key:
                score += 50
                reason_parts.append("Coincide trabajador")
            elif cand_company_key and target_company_key and cand_company_key == target_company_key:
                # Trabajador específico pero documento de empresa (menos relevante)
                score += 25
                reason_parts.append("Coincide empresa (trabajador específico)")
        elif target_scope == "company":
            if cand_company_key and target_company_key and cand_company_key == target_company_key:
                score += 50
                reason_parts.append("Coincide empresa")
        
        # 3. Exact period match
        if target_period_key and cand_period_key:
            if cand_period_key == target_period_key:
                score += 30
                reason_parts.append("Coincide período")
            else:
                # Periodo distinto (se puede usar fallback, pero con penalización implícita)
                reason_parts.append("Período distinto")
        
        # 4. Recency (más reciente = mejor)
        if updated_at_str:
            try:
                # Intentar parsear fecha
                if isinstance(updated_at_str, str):
                    # Formato ISO o similar
                    if 'T' in updated_at_str:
                        updated_dt = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
                    else:
                        updated_dt = datetime.fromisoformat(updated_at_str)
                else:
                    updated_dt = updated_at_str
                
                # Calcular meses desde updated_at hasta hoy
                try:
                    today = date.today()
                    if isinstance(updated_dt, datetime):
                        updated_date = updated_dt.date()
                    elif isinstance(updated_dt, date):
                        updated_date = updated_dt
                    else:
                        updated_date = updated_dt
                    
                    months_ago = (today.year - updated_date.year) * 12 + (today.month - updated_date.month)
                    recency_bonus = max(0, 60 - (months_ago * 10))  # Máximo 60 puntos, -10 por mes
                    score += recency_bonus
                except (AttributeError, TypeError):
                    # Si no se puede calcular, ignorar recency
                    pass
                
                if months_ago == 0:
                    reason_parts.append("Muy reciente")
                elif months_ago <= 3:
                    reason_parts.append("Reciente")
            except (ValueError, AttributeError):
                # Si no se puede parsear, ignorar recency
                pass
        
        # 5. Status bonus
        if status in ("reviewed", "submitted", "valid"):
            score += 20
            reason_parts.append("Estado revisado")
        elif status == "draft":
            # Sin bonus
            pass
        
        scored.append(CandidateScore(
            doc_id=doc_id,
            score=score,
            reason_parts=reason_parts,
        ))
    
    # Ordenar por score descendente
    scored.sort(key=lambda x: x.score, reverse=True)
    
    return scored


def get_best_candidate(
    candidates: List[Dict[str, Any]],
    target_type_id: str,
    target_scope: str,
    target_company_key: Optional[str] = None,
    target_person_key: Optional[str] = None,
    target_period_key: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """
    Obtiene el mejor candidato y su razón.
    
    Returns:
        (best_doc_id, best_reason) o (None, None) si no hay candidatos válidos.
    """
    if not candidates:
        return None, None
    
    ranked = rank_candidates(
        candidates=candidates,
        target_type_id=target_type_id,
        target_scope=target_scope,
        target_company_key=target_company_key,
        target_person_key=target_person_key,
        target_period_key=target_period_key,
    )
    
    if not ranked:
        return None, None
    
    best = ranked[0]
    return best.doc_id, best.get_reason()

