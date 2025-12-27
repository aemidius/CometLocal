from __future__ import annotations

import re
from datetime import date
from typing import Dict, List, Optional, Tuple

from backend.shared.document_repository_v1 import (
    DocumentTypeV1,
    DocumentInstanceV1,
    DocumentStatusV1,
)
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1


def normalize_text(text: str) -> str:
    """Normaliza texto para matching: lowercase, elimina espacios extra."""
    if not text:
        return ""
    # Convertir a lowercase y normalizar espacios
    normalized = re.sub(r'\s+', ' ', text.lower().strip())
    return normalized


def normalize_whitespace(text: str) -> str:
    """Normaliza espacios en blanco (múltiples espacios -> uno)."""
    return re.sub(r'\s+', ' ', text.strip())


class MatchResultV1:
    """Resultado de matching de un documento."""
    
    def __init__(
        self,
        doc: DocumentInstanceV1,
        score: float,
        reasons: List[str]
    ):
        self.doc = doc
        self.score = score
        self.reasons = reasons
    
    def to_dict(self) -> dict:
        # Usar validity_override si existe, sino computed_validity
        if self.doc.validity_override:
            valid_from = self.doc.validity_override.override_valid_from
            valid_to = self.doc.validity_override.override_valid_to
        else:
            valid_from = self.doc.computed_validity.valid_from
            valid_to = self.doc.computed_validity.valid_to
        
        return {
            "doc_id": self.doc.doc_id,
            "file_name": self.doc.file_name_original,
            "type_id": self.doc.type_id,
            "validity_from": valid_from.isoformat() if valid_from else None,
            "validity_to": valid_to.isoformat() if valid_to else None,
            "status": self.doc.status,
            "score": self.score,
            "reasons": self.reasons,
            "has_override": self.doc.validity_override is not None
        }


class PendingItemV1:
    """Item pendiente de eGestiona."""
    
    def __init__(
        self,
        tipo_doc: Optional[str] = None,
        elemento: Optional[str] = None,
        empresa: Optional[str] = None,
        trabajador: Optional[str] = None,
        fecha_inicio: Optional[date] = None,
        fecha_fin: Optional[date] = None,
        raw_data: Optional[dict] = None
    ):
        self.tipo_doc = tipo_doc
        self.elemento = elemento
        self.empresa = empresa
        self.trabajador = trabajador
        self.fecha_inicio = fecha_inicio
        self.fecha_fin = fecha_fin
        self.raw_data = raw_data or {}
    
    def get_base_text(self) -> str:
        """Obtiene texto base para matching: tipo_doc + elemento."""
        parts = []
        if self.tipo_doc:
            parts.append(self.tipo_doc)
        if self.elemento:
            parts.append(self.elemento)
        return " ".join(parts)
    
    def to_dict(self) -> dict:
        return {
            "tipo_doc": self.tipo_doc,
            "elemento": self.elemento,
            "empresa": self.empresa,
            "trabajador": self.trabajador,
            "fecha_inicio": self.fecha_inicio.isoformat() if self.fecha_inicio else None,
            "fecha_fin": self.fecha_fin.isoformat() if self.fecha_fin else None,
            "raw_data": self.raw_data
        }


class DocumentMatcherV1:
    """Matcher determinista de documentos del repositorio con pendientes de eGestiona."""
    
    def __init__(self, store: DocumentRepositoryStoreV1):
        self.store = store
    
    def find_matching_types(
        self,
        base_text: str
    ) -> List[Tuple[DocumentTypeV1, float]]:
        """
        Encuentra tipos que coinciden con el texto base usando platform_aliases.
        
        Retorna: Lista de (tipo, confidence) ordenada por confidence descendente.
        """
        base_normalized = normalize_text(base_text)
        if not base_normalized:
            return []
        
        matches: List[Tuple[DocumentTypeV1, float]] = []
        all_types = self.store.list_types(include_inactive=False)
        
        for doc_type in all_types:
            for alias in doc_type.platform_aliases:
                alias_normalized = normalize_text(alias)
                if alias_normalized and alias_normalized in base_normalized:
                    # Match encontrado
                    matches.append((doc_type, 0.6))  # Base confidence por alias match
                    break
        
        # Ordenar por confidence descendente
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches
    
    def score_document(
        self,
        doc: DocumentInstanceV1,
        doc_type: DocumentTypeV1,
        pending: PendingItemV1,
        base_score: float = 0.0
    ) -> Tuple[float, List[str]]:
        """
        Calcula score para un documento y retorna (score, reasons).
        
        Scoring:
        - +0.6 si type match por alias (ya incluido en base_score)
        - +0.3 si doc.status in (reviewed, ready_to_submit)
        - +0.2 si validity cubre el período de la solicitud (si hay fechas)
        - -0.2 si doc.status=draft
        """
        score = base_score
        reasons: List[str] = []
        
        if base_score > 0:
            reasons.append(f"type match by alias (base: {base_score:.2f})")
        
        # Status scoring
        if doc.status in (DocumentStatusV1.reviewed, DocumentStatusV1.ready_to_submit):
            score += 0.3
            reasons.append(f"status={doc.status.value} (+0.3)")
        elif doc.status == DocumentStatusV1.draft:
            score -= 0.2
            reasons.append(f"status=draft (-0.2)")
        
        # Validity period matching (si hay fechas en pending)
        if pending.fecha_inicio and pending.fecha_fin:
            if doc.computed_validity.valid_from and doc.computed_validity.valid_to:
                # Verificar si el período del doc cubre el período solicitado
                if (doc.computed_validity.valid_from <= pending.fecha_inicio and
                    doc.computed_validity.valid_to >= pending.fecha_fin):
                    score += 0.2
                    reasons.append("validity period covers requested period (+0.2)")
                elif (doc.computed_validity.valid_from <= pending.fecha_fin and
                      doc.computed_validity.valid_to >= pending.fecha_inicio):
                    # Overlap parcial
                    score += 0.1
                    reasons.append("validity period overlaps requested period (+0.1)")
        
        # Asegurar que score esté en [0, 1]
        score = max(0.0, min(1.0, score))
        
        return score, reasons
    
    def match_pending_item(
        self,
        pending: PendingItemV1,
        company_key: str,
        person_key: Optional[str] = None
    ) -> Dict:
        """
        Hace matching de un pending item con documentos del repositorio.
        
        Retorna:
        {
            "best_doc": MatchResultV1.to_dict() o None,
            "alternatives": [MatchResultV1.to_dict(), ...],
            "confidence": float,
            "reasons": List[str],
            "needs_operator": bool
        }
        """
        base_text = pending.get_base_text()
        base_normalized = normalize_text(base_text)
        
        # 1) Encontrar tipos candidatos
        matching_types = self.find_matching_types(base_text)
        
        if not matching_types:
            return {
                "best_doc": None,
                "alternatives": [],
                "confidence": 0.0,
                "reasons": [f"No type match found for text: '{base_text}'"],
                "needs_operator": True
            }
        
        # 2) Filtrar documentos por sujeto
        all_candidates: List[MatchResultV1] = []
        
        for doc_type, type_confidence in matching_types:
            # Filtrar docs por type_id, company_key, person_key
            docs = self.store.list_documents(
                type_id=doc_type.type_id,
                company_key=company_key,
                person_key=person_key
            )
            
            for doc in docs:
                score, reasons = self.score_document(doc, doc_type, pending, type_confidence)
                all_candidates.append(MatchResultV1(doc, score, reasons))
        
        if not all_candidates:
            return {
                "best_doc": None,
                "alternatives": [],
                "confidence": 0.0,
                "reasons": [f"No documents found for company={company_key}, person={person_key}"],
                "needs_operator": True
            }
        
        # 3) Ordenar por score descendente
        all_candidates.sort(key=lambda x: x.score, reverse=True)
        
        best = all_candidates[0]
        alternatives = all_candidates[1:4]  # Hasta 3 alternativas
        
        # 4) Determinar needs_operator
        needs_operator = False
        if best.score < 0.7:
            needs_operator = True
        if len(all_candidates) > 1 and abs(all_candidates[0].score - all_candidates[1].score) < 0.1:
            # Empate cercano
            needs_operator = True
        
        return {
            "best_doc": best.to_dict(),
            "alternatives": [alt.to_dict() for alt in alternatives],
            "confidence": best.score,
            "reasons": best.reasons,
            "needs_operator": needs_operator
        }

