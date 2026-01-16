from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.shared.document_repository_v1 import (
    DocumentTypeV1,
    DocumentInstanceV1,
    DocumentStatusV1,
)
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.repository.rule_based_matcher_v1 import RuleBasedMatcherV1
from backend.repository.submission_rules_store_v1 import SubmissionRulesStoreV1
from backend.shared.text_normalizer import normalize_text as normalize_text_robust
from backend.repository.text_utils import normalize_whitespace

# Mantener compatibilidad: normalize_text para matching
def normalize_text(text: str) -> str:
    """Alias para compatibilidad con código existente."""
    return normalize_text_robust(text)


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
    
    def __init__(self, store: DocumentRepositoryStoreV1, base_dir: str | Path = "data"):
        self.store = store
        self.base_dir = base_dir
        # Inicializar rule matcher
        rules_store = SubmissionRulesStoreV1(base_dir=base_dir)
        self.rule_matcher = RuleBasedMatcherV1(rules_store)
        # Asegurar aliases para T104_AUTONOMOS_RECEIPT
        self._ensure_autonomos_aliases()
    
    def _ensure_autonomos_aliases(self) -> None:
        """Asegura que T104_AUTONOMOS_RECEIPT tiene los aliases necesarios para T205.0."""
        doc_type = self.store.get_type("T104_AUTONOMOS_RECEIPT")
        if not doc_type:
            return
        
        required_aliases = [
            "T205.0",
            "T205",
            "último recibo bancario pago cuota autónomos",
            "pago cuota autónomos",
            "cuota autónomos",
            "recibo bancario cuota autónomos",
        ]
        
        # Normalizar aliases existentes para comparación
        existing_normalized = {normalize_text(a) for a in doc_type.platform_aliases}
        
        # Añadir aliases faltantes
        aliases_to_add = []
        for alias in required_aliases:
            alias_normalized = normalize_text(alias)
            if alias_normalized and alias_normalized not in existing_normalized:
                aliases_to_add.append(alias)
        
        if aliases_to_add:
            # Actualizar tipo con nuevos aliases
            updated_aliases = list(doc_type.platform_aliases) + aliases_to_add
            # Crear nuevo tipo excluyendo platform_aliases del model_dump
            type_dict = doc_type.model_dump()
            type_dict["platform_aliases"] = updated_aliases
            updated_type = DocumentTypeV1(**type_dict)
            self.store.update_type("T104_AUTONOMOS_RECEIPT", updated_type)
    
    def find_matching_types(
        self,
        base_text: str
    ) -> List[Tuple[DocumentTypeV1, float]]:
        """
        Encuentra tipos que coinciden con el texto base usando platform_aliases.
        
        Mejoras:
        - Detecta códigos al inicio del texto (ej: "T205.0" -> match exacto con mayor confidence)
        - Fallback a contains normalized para aliases de texto
        
        Retorna: Lista de (tipo, confidence) ordenada por confidence descendente.
        """
        base_normalized = normalize_text(base_text)
        if not base_normalized:
            return []
        
        matches: List[Tuple[DocumentTypeV1, float]] = []
        all_types = self.store.list_types(include_inactive=False)
        
        # Extraer código al inicio (ej: "T205.0", "T205")
        code_match = re.match(r'^([Tt]\d+(?:\.\d+)?)', base_text)
        detected_code = code_match.group(1) if code_match else None
        
        for doc_type in all_types:
            best_confidence = 0.0
            match_reason = None
            
            for alias in doc_type.platform_aliases:
                alias_normalized = normalize_text(alias)
                if not alias_normalized:
                    continue
                
                # Match exacto por código al inicio (mayor confidence)
                if detected_code:
                    alias_code_match = re.match(r'^([Tt]\d+(?:\.\d+)?)', alias)
                    if alias_code_match:
                        alias_code = alias_code_match.group(1)
                        if alias_code.upper() == detected_code.upper():
                            best_confidence = max(best_confidence, 0.9)  # Alta confidence por código exacto
                            match_reason = f"exact_code_match:{alias_code}"
                            continue
                
                # Fallback: contains normalized
                if alias_normalized in base_normalized:
                    # Si el alias está al inicio del texto, mayor confidence
                    if base_normalized.startswith(alias_normalized):
                        confidence = 0.75
                    else:
                        confidence = 0.6
                    best_confidence = max(best_confidence, confidence)
                    if not match_reason:
                        match_reason = f"contains_alias:{alias}"
            
            if best_confidence > 0.0:
                matches.append((doc_type, best_confidence))
        
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
        person_key: Optional[str] = None,
        platform_key: str = "egestiona",
        coord_label: Optional[str] = None,
        evidence_dir: Optional[Path] = None
    ) -> Dict:
        """
        Hace matching de un pending item con documentos del repositorio.
        
        Args:
            evidence_dir: Directorio opcional donde guardar pending_match_debug.json
        
        Retorna:
        {
            "best_doc": MatchResultV1.to_dict() o None,
            "alternatives": [MatchResultV1.to_dict(), ...],
            "confidence": float,
            "reasons": List[str],
            "needs_operator": bool,
            "matched_rule": dict o None  # Si vino de regla, incluye rule.form
        }
        """
        # INSTRUMENTACIÓN: Preparar debug info
        debug_info = {
            "pending_text_original": pending.get_base_text(),
            "pending_tipo_doc": pending.tipo_doc,
            "pending_elemento": pending.elemento,
            "pending_empresa": pending.empresa,
            "pending_trabajador": pending.trabajador,
            "pending_fecha_inicio": pending.fecha_inicio.isoformat() if pending.fecha_inicio else None,
            "pending_fecha_fin": pending.fecha_fin.isoformat() if pending.fecha_fin else None,
        }
        
        # Detectar código y mes/año
        base_text = pending.get_base_text()
        code_match = re.match(r'^([Tt]\d+(?:\.\d+)?)', base_text)
        debug_info["pending_code_detected"] = code_match.group(1) if code_match else None
        
        # Detectar mes/año (ej: "Mayo 2023", "May 2023")
        month_year_match = re.search(r'(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})', base_text, re.IGNORECASE)
        pending_period_key = None
        if month_year_match:
            month_name = month_year_match.group(1).lower()
            year = int(month_year_match.group(2))
            # Mapear nombre de mes a número
            month_map = {
                "enero": 1, "january": 1,
                "febrero": 2, "february": 2,
                "marzo": 3, "march": 3,
                "abril": 4, "april": 4,
                "mayo": 5, "may": 5,
                "junio": 6, "june": 6,
                "julio": 7, "july": 7,
                "agosto": 8, "august": 8,
                "septiembre": 9, "september": 9,
                "octubre": 10, "october": 10,
                "noviembre": 11, "november": 11,
                "diciembre": 12, "december": 12,
            }
            month_num = month_map.get(month_name)
            if month_num:
                pending_period_key = f"{year}-{month_num:02d}"
            debug_info["pending_month_year_detected"] = f"{month_year_match.group(1)} {month_year_match.group(2)}"
            debug_info["pending_period_key"] = pending_period_key
        else:
            debug_info["pending_month_year_detected"] = None
            debug_info["pending_period_key"] = None
        
        base_normalized = normalize_text(base_text)
        debug_info["pending_title_normalized"] = base_normalized
        
        # 0) Intentar matching basado en reglas PRIMERO
        rule_match = self.rule_matcher.match_pending_item(
            pending=pending,
            platform_key=platform_key,
            coord_label=coord_label,
            empresa_text=pending.empresa
        )
        
        matched_rule = None
        if rule_match:
            rule, rule_confidence, rule_reasons = rule_match
            # Buscar documentos del tipo especificado por la regla
            doc_type = self.store.get_type(rule.document_type_id)
            if doc_type:
                # Si hay pending_period_key, usarlo también en reglas
                if pending_period_key:
                    docs = self.store.list_documents(
                        type_id=rule.document_type_id,
                        company_key=company_key,
                        person_key=person_key,
                        period_key=pending_period_key
                    )
                    # Fallback sin empresa si es worker
                    if not docs and doc_type.scope == "worker" and person_key:
                        docs = self.store.list_documents(
                            type_id=rule.document_type_id,
                            company_key=None,
                            person_key=person_key,
                            period_key=pending_period_key
                        )
                else:
                    docs = self.store.list_documents(
                        type_id=rule.document_type_id,
                        company_key=company_key,
                        person_key=person_key
                    )
                
                if docs:
                    # Usar el primer documento encontrado (o el mejor según scoring)
                    best_doc = docs[0]
                    # Score adicional basado en status y validez
                    score, reasons = self.score_document(best_doc, doc_type, pending, rule_confidence)
                    
                    # Construir match result con regla
                    match_result = MatchResultV1(best_doc, score, reasons + rule_reasons)
                    
                    return {
                        "best_doc": match_result.to_dict(),
                        "alternatives": [],
                        "confidence": score,
                        "reasons": reasons + rule_reasons,
                        "needs_operator": score < 0.75,
                        "matched_rule": {
                            "rule_id": rule.rule_id,
                            "form": rule.form.model_dump(mode="json")
                        }
                    }
                else:
                    # Regla matchea pero no hay documentos
                    reason = f"No documents found for type {rule.document_type_id}"
                    if pending_period_key:
                        reason = f"Missing document for period {pending_period_key}"
                    return {
                        "best_doc": None,
                        "alternatives": [],
                        "confidence": 0.0,
                        "reasons": rule_reasons + [reason],
                        "needs_operator": True,
                        "matched_rule": {
                            "rule_id": rule.rule_id,
                            "form": rule.form.model_dump(mode="json")
                        }
                    }
        
        # 1) Fallback: Encontrar tipos candidatos por aliases (método original)
        matching_types = self.find_matching_types(base_text)
        
        # INSTRUMENTACIÓN: Guardar type candidates
        debug_info["type_candidates"] = [
            {
                "type_id": doc_type.type_id,
                "name": doc_type.name,
                "confidence": conf,
                "aliases": doc_type.platform_aliases
            }
            for doc_type, conf in matching_types
        ]
        
        if not matching_types:
            debug_info["match_result"] = "NO_TYPE_MATCH"
            debug_info["reasons"] = [f"No type match found for text: '{base_text}'"]
            if evidence_dir:
                self._save_debug_info(evidence_dir, debug_info)
            return {
                "best_doc": None,
                "alternatives": [],
                "confidence": 0.0,
                "reasons": [f"No type match found for text: '{base_text}'"],
                "needs_operator": True
            }
        
        # 2) Filtrar documentos por sujeto (con fallback sin empresa)
        all_candidates: List[MatchResultV1] = []
        debug_info["document_queries"] = []
        
        for doc_type, type_confidence in matching_types:
            # Si hay pending_period_key, buscar exactamente ese período
            if pending_period_key:
                docs = self.store.list_documents(
                    type_id=doc_type.type_id,
                    company_key=company_key,
                    person_key=person_key,
                    period_key=pending_period_key
                )
                query_info = {
                    "type_id": doc_type.type_id,
                    "company_key": company_key,
                    "person_key": person_key,
                    "period_key": pending_period_key,
                    "docs_found": len(docs),
                    "query": "with_company_person_and_period"
                }
                debug_info["document_queries"].append(query_info)
                
                # Si no hay docs con periodo exacto y es scope worker, intentar sin empresa
                if not docs and doc_type.scope == "worker" and person_key:
                    docs = self.store.list_documents(
                        type_id=doc_type.type_id,
                        company_key=None,
                        person_key=person_key,
                        period_key=pending_period_key
                    )
                    query_info_fallback = {
                        "type_id": doc_type.type_id,
                        "company_key": None,
                        "person_key": person_key,
                        "period_key": pending_period_key,
                        "docs_found": len(docs),
                        "query": "fallback_without_company_with_period"
                    }
                    debug_info["document_queries"].append(query_info_fallback)
                
                # Si aún no hay docs, error explícito
                if not docs:
                    debug_info["match_result"] = "MISSING_DOC_FOR_PERIOD"
                    debug_info["reasons"] = [f"Missing document for period {pending_period_key}"]
                    if evidence_dir:
                        self._save_debug_info(evidence_dir, debug_info)
                    return {
                        "best_doc": None,
                        "alternatives": [],
                        "confidence": 0.0,
                        "reasons": [f"Missing document for period {pending_period_key}"],
                        "needs_operator": True
                    }
            else:
                # Sin period_key: Query 1: Con empresa y persona
                docs = self.store.list_documents(
                    type_id=doc_type.type_id,
                    company_key=company_key,
                    person_key=person_key
                )
                query_info = {
                    "type_id": doc_type.type_id,
                    "company_key": company_key,
                    "person_key": person_key,
                    "period_key": None,
                    "docs_found": len(docs),
                    "query": "with_company_and_person"
                }
                debug_info["document_queries"].append(query_info)
                
                # Si no hay docs y es scope worker, intentar sin empresa (fallback)
                if not docs and doc_type.scope == "worker" and person_key:
                    docs = self.store.list_documents(
                        type_id=doc_type.type_id,
                        company_key=None,  # Sin empresa
                        person_key=person_key
                    )
                    query_info_fallback = {
                        "type_id": doc_type.type_id,
                        "company_key": None,
                        "person_key": person_key,
                        "period_key": None,
                        "docs_found": len(docs),
                        "query": "fallback_without_company"
                    }
                    debug_info["document_queries"].append(query_info_fallback)
            
            for doc in docs:
                score, reasons = self.score_document(doc, doc_type, pending, type_confidence)
                all_candidates.append(MatchResultV1(doc, score, reasons))
        
        # INSTRUMENTACIÓN: Guardar info de documentos candidatos
        debug_info["candidates_found"] = len(all_candidates)
        debug_info["candidates_details"] = [
            {
                "doc_id": c.doc.doc_id,
                "file_name": c.doc.file_name_original,
                "score": c.score,
                "reasons": c.reasons
            }
            for c in all_candidates[:5]  # Primeros 5
        ]
        
        if not all_candidates:
            debug_info["match_result"] = "NO_DOCUMENTS_FOUND"
            debug_info["reasons"] = [f"No documents found for company={company_key}, person={person_key}"]
            if evidence_dir:
                self._save_debug_info(evidence_dir, debug_info)
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
        
        # INSTRUMENTACIÓN: Guardar resultado final
        debug_info["match_result"] = "MATCH_FOUND" if best.score >= 0.7 else "LOW_CONFIDENCE_MATCH"
        debug_info["best_doc"] = best.to_dict()
        debug_info["confidence"] = best.score
        debug_info["reasons"] = best.reasons
        debug_info["needs_operator"] = needs_operator
        
        if evidence_dir:
            self._save_debug_info(evidence_dir, debug_info)
        
        return {
            "best_doc": best.to_dict(),
            "alternatives": [alt.to_dict() for alt in alternatives],
            "confidence": best.score,
            "reasons": best.reasons,
            "needs_operator": needs_operator,
            "matched_rule": None  # No vino de regla
        }
    
    def _save_debug_info(self, evidence_dir: Path, debug_info: dict) -> None:
        """Guarda pending_match_debug.json en evidence_dir."""
        try:
            debug_path = evidence_dir / "pending_match_debug.json"
            # Si ya existe, leer y añadir a lista
            if debug_path.exists():
                try:
                    existing = json.loads(debug_path.read_text(encoding="utf-8"))
                    if isinstance(existing, list):
                        existing.append(debug_info)
                        debug_data = existing
                    else:
                        debug_data = [existing, debug_info]
                except Exception:
                    debug_data = [debug_info]
            else:
                debug_data = [debug_info]
            
            debug_path.write_text(
                json.dumps(debug_data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            # No fallar si no se puede guardar debug
            pass

