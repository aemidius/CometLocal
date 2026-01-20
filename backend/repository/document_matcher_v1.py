from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

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
from backend.shared.matching_debug_report import (
    MatchingDebugReportV1,
    PipelineStep,
    CandidateTop,
    MatchingOutcome,
    PrimaryReasonCode,
)
from backend.repository.matching_debug_codes_v1 import (
    make_reason,
    NO_LOCAL_DOCS,
    TYPE_NOT_FOUND,
    TYPE_INACTIVE,
    ALIAS_NOT_MATCHING,
    SCOPE_MISMATCH,
    PERIOD_MISMATCH,
    COMPANY_MISMATCH,
    PERSON_MISMATCH,
    VALIDITY_MISMATCH,
)

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
            "T104.0 Recibo autónomos",
            "T104.0",
            "T104",
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
        evidence_dir: Optional[Path] = None,
        generate_debug_report: bool = True,  # SPRINT C2.18A: Generar reporte estructurado
    ) -> Dict:
        """
        Hace matching de un pending item con documentos del repositorio.
        
        Args:
            evidence_dir: Directorio opcional donde guardar pending_match_debug.json
            generate_debug_report: SPRINT C2.18A: Si True, genera MatchingDebugReportV1 estructurado
        
        Retorna:
        {
            "best_doc": MatchResultV1.to_dict() o None,
            "alternatives": [MatchResultV1.to_dict(), ...],
            "confidence": float,
            "reasons": List[str],
            "needs_operator": bool,
            "matched_rule": dict o None,  # Si vino de regla, incluye rule.form
            "matching_debug_report": MatchingDebugReportV1 o None  # SPRINT C2.18A
        }
        """
        # SPRINT C2.18A: Inicializar reporte de debug estructurado
        debug_report: Optional[MatchingDebugReportV1] = None
        # SPRINT C2.19A: Inicializar applied_hints al inicio
        applied_hints: List[Dict[str, Any]] = []
        if generate_debug_report:
            # SPRINT C2.18A.1: Usar base_dir del store (que es el data_dir, no el repo_dir)
            # El repo_dir es data_dir/repository, pero queremos el data_dir
            data_dir_resolved = str(self.store.base_dir.resolve())
            debug_report = MatchingDebugReportV1.create_empty(
                data_dir_resolved=data_dir_resolved,
                platform=platform_key,
                company_key=company_key,
                person_key=person_key,
                pending_label=f"{pending.tipo_doc} | {pending.elemento}",
                pending_text=pending.get_base_text(),
            )
            # Paso 0: start: all_docs
            all_docs = self.store.list_documents()  # Sin filtros
            debug_report.pipeline.append(PipelineStep(
                step_name="start: all_docs",
                input_count=0,  # No hay input previo
                output_count=len(all_docs),
                rule="load_all_documents",
                dropped_sample=[],
            ))
        
        # INSTRUMENTACIÓN: Preparar debug info (legacy, mantener compatibilidad)
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
        
        # SPRINT C2.18A: Actualizar period_key en debug_report
        if debug_report:
            debug_report.meta["request_context"]["period_key"] = pending_period_key
        
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
                
                # SPRINT C2.18A: Si hay debug_report, actualizar con info de regla
                if debug_report:
                    debug_report.meta["request_context"]["matched_rule_id"] = rule.rule_id
                    debug_report.meta["request_context"]["type_ids"] = [rule.document_type_id]
                    if not docs:
                        # Regla matchea pero no hay docs - determinar causa específica
                        # SPRINT C2.18A.1: Verificar DATA_DIR_MISMATCH primero
                        primary_reason = PrimaryReasonCode.SUBJECT_FILTER_ZERO
                        human_hint = f"Regla {rule.rule_id} matchea pero no hay documentos del tipo {rule.document_type_id}."
                        
                        # Si repo está vacío, verificar mismatch
                        if debug_report.meta["repo_docs_total"] == 0:
                            data_dir_resolved = debug_report.meta.get("data_dir_resolved")
                            data_dir_expected = debug_report.meta.get("data_dir_expected")
                            
                            if data_dir_expected:
                                from pathlib import Path
                                resolved_norm = str(Path(data_dir_resolved).resolve())
                                expected_norm = str(Path(data_dir_expected).resolve())
                                
                                if resolved_norm != expected_norm:
                                    primary_reason = PrimaryReasonCode.DATA_DIR_MISMATCH
                                    expected_source = debug_report.meta.get("data_dir_expected_source", "unknown")
                                    human_hint = (
                                        f"El repositorio local parece vacío porque data_dir_resolved ({data_dir_resolved}) "
                                        f"difiere de data_dir_expected ({data_dir_expected}) "
                                        f"(fuente: {expected_source}). "
                                        f"Revisa variables de entorno o configuración."
                                    )
                        elif pending_period_key:
                            primary_reason = PrimaryReasonCode.PERIOD_FILTER_ZERO
                            human_hint = f"Regla {rule.rule_id} matchea pero no hay documentos del tipo {rule.document_type_id} para el período {pending_period_key}."
                        
                        # SPRINT C2.19A: applied_hints vacío aquí (aún no se han aplicado)
                        from backend.shared.matching_debug_report import AppliedHint
                        applied_hints_models = []
                        
                        debug_report.outcome = MatchingOutcome(
                            decision="NO_MATCH",
                            local_docs_considered=0,
                            primary_reason_code=primary_reason,
                            human_hint=human_hint,
                            applied_hints=applied_hints_models,
                        )
                        if evidence_dir:
                            self._save_debug_report(evidence_dir, pending, debug_report)
                
                if docs:
                    # Usar el primer documento encontrado (o el mejor según scoring)
                    best_doc = docs[0]
                    # Score adicional basado en status y validez
                    score, reasons = self.score_document(best_doc, doc_type, pending, rule_confidence)
                    
                    # Construir match result con regla
                    match_result = MatchResultV1(best_doc, score, reasons + rule_reasons)
                    
                    # SPRINT C2.18A: Actualizar outcome si hay debug_report
                    if debug_report:
                        decision = "AUTO_UPLOAD" if score >= 0.7 else "REVIEW_REQUIRED"
                        # Añadir candidato top
                        debug_report.candidates_top.append(CandidateTop(
                            doc_id=best_doc.doc_id,
                            type_id=best_doc.type_id,
                            company_key=best_doc.company_key,
                            person_key=best_doc.person_key,
                            period_key=best_doc.period_key,
                            file_path=best_doc.file_name_original,
                            status=best_doc.status.value,
                            score_breakdown={
                                "final_confidence": score,
                                "rule_confidence": rule_confidence,
                            },
                            reject_reason=None,  # Match exitoso
                        ))
                        # SPRINT C2.19A: applied_hints vacío aquí (match por regla, no por hint)
                        from backend.shared.matching_debug_report import AppliedHint
                        applied_hints_models = []
                        
                        debug_report.outcome = MatchingOutcome(
                            decision=decision,
                            local_docs_considered=len(docs),
                            primary_reason_code=PrimaryReasonCode.UNKNOWN,  # Match exitoso
                            human_hint=f"Match encontrado mediante regla {rule.rule_id} (confidence={score:.2f}).",
                            applied_hints=applied_hints_models,
                        )
                        if evidence_dir:
                            self._save_debug_report(evidence_dir, pending, debug_report)
                    
                    return {
                        "best_doc": match_result.to_dict(),
                        "alternatives": [],
                        "confidence": score,
                        "reasons": reasons + rule_reasons,
                        "needs_operator": score < 0.75,
                        "matched_rule": {
                            "rule_id": rule.rule_id,
                            "form": rule.form.model_dump(mode="json")
                        },
                        "matching_debug_report": debug_report.model_dump(mode="json") if debug_report else None,  # SPRINT C2.18A
                    }
                else:
                    # Regla matchea pero no hay documentos
                    reason = f"No documents found for type {rule.document_type_id}"
                    if pending_period_key:
                        reason = f"Missing document for period {pending_period_key}"
                    # SPRINT C2.18A: Ya se actualizó debug_report arriba si existe
                    
                    # SPRINT C2.34: Generar matching_debug_report
                    stage_counts = {
                        "local_docs_considered": len(all_docs) if 'all_docs' in locals() else 0,
                        "local_docs_after_type": 0,
                        "local_docs_after_scope": 0,
                        "local_docs_after_company": 0,
                        "local_docs_after_person": 0,
                        "local_docs_after_period": 0,
                        "local_docs_after_validity": 0,
                    }
                    context = {
                        "company_key": company_key,
                        "person_key": person_key,
                        "platform_key": platform_key,
                        "period_key": pending_period_key,
                    }
                    type_lookup_info = {
                        "type_id": rule.document_type_id,
                        "found": True,
                        "active": True,
                        "scope": doc_type.scope.value if hasattr(doc_type.scope, 'value') else str(doc_type.scope),
                    }
                    alias_info = {"alias_received": base_text, "matched": True} if base_text else None
                    match_result_dict = {"decision": "NO_MATCH", "best_doc": None, "confidence": 0.0}
                    matching_debug_report_c234 = self.build_matching_debug_report(
                        pending=pending, context=context, repo_docs=[], match_result=match_result_dict,
                        stage_counts=stage_counts, type_lookup_info=type_lookup_info, alias_info=alias_info
                    )
                    
                    return {
                        "best_doc": None,
                        "alternatives": [],
                        "confidence": 0.0,
                        "reasons": rule_reasons + [reason],
                        "needs_operator": True,
                        "matched_rule": {
                            "rule_id": rule.rule_id,
                            "form": rule.form.model_dump(mode="json")
                        },
                        "matching_debug_report": debug_report.model_dump(mode="json") if debug_report else None,  # SPRINT C2.18A
                        "matching_debug_report_c234": matching_debug_report_c234,  # SPRINT C2.34
                    }
        
        # 1) Fallback: Encontrar tipos candidatos por aliases (método original)
        matching_types = self.find_matching_types(base_text)
        
        # SPRINT C2.18A: Paso 1: filter: active types
        if debug_report:
            all_types = self.store.list_types(include_inactive=True)
            active_types = self.store.list_types(include_inactive=False)
            debug_report.pipeline.append(PipelineStep(
                step_name="filter: active",
                input_count=len(all_types),
                output_count=len(active_types),
                rule="include_inactive=False",
                dropped_sample=[],
            ))
        
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
        
        # SPRINT C2.18A: Paso 2: filter: type_id (matching por aliases)
        if debug_report:
            type_ids = [t[0].type_id for t in matching_types]
            debug_report.meta["request_context"]["type_ids"] = type_ids
            if not matching_types:
                # No hay tipos que matcheen
                debug_report.pipeline.append(PipelineStep(
                    step_name="filter: type_id",
                    input_count=len(active_types) if 'active_types' in locals() else 0,
                    output_count=0,
                    rule=f"type_match_by_alias: no match for '{base_text}'",
                    dropped_sample=[],
                ))
                # SPRINT C2.19A: applied_hints vacío aquí (aún no se han aplicado)
                from backend.shared.matching_debug_report import AppliedHint
                applied_hints_models = []
                
                debug_report.outcome = MatchingOutcome(
                    decision="NO_MATCH",
                    local_docs_considered=0,
                    primary_reason_code=PrimaryReasonCode.TYPE_FILTER_ZERO,
                    human_hint=f"No se encontró tipo de documento que coincida con '{base_text}'. Verificar aliases en tipos.",
                    applied_hints=applied_hints_models,
                )
                if evidence_dir:
                    self._save_debug_report(evidence_dir, pending, debug_report)
                debug_info["match_result"] = "NO_TYPE_MATCH"
                debug_info["reasons"] = [f"No type match found for text: '{base_text}'"]
                if evidence_dir:
                    self._save_debug_info(evidence_dir, debug_info)
                
                # SPRINT C2.34: Generar matching_debug_report
                stage_counts = {
                    "local_docs_considered": len(all_docs) if 'all_docs' in locals() else 0,
                    "local_docs_after_type": 0,
                    "local_docs_after_scope": 0,
                    "local_docs_after_company": 0,
                    "local_docs_after_person": 0,
                    "local_docs_after_period": 0,
                    "local_docs_after_validity": 0,
                }
                context = {
                    "company_key": company_key,
                    "person_key": person_key,
                    "platform_key": platform_key,
                    "period_key": pending_period_key,
                }
                type_lookup_info = {"type_id": None, "found": False, "active": False, "scope": None}
                alias_info = {"alias_received": base_text, "matched": False} if base_text else None
                match_result_dict = {"decision": "NO_MATCH", "best_doc": None, "confidence": 0.0}
                matching_debug_report_c234 = self.build_matching_debug_report(
                    pending=pending, context=context, repo_docs=[], match_result=match_result_dict,
                    stage_counts=stage_counts, type_lookup_info=type_lookup_info, alias_info=alias_info
                )
                
                return {
                    "best_doc": None,
                    "alternatives": [],
                    "confidence": 0.0,
                    "reasons": [f"No type match found for text: '{base_text}'"],
                    "needs_operator": True,
                    "matching_debug_report": debug_report.model_dump(mode="json") if debug_report else None,  # SPRINT C2.18A
                    "matching_debug_report_c234": matching_debug_report_c234,  # SPRINT C2.34
                }
        
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
                "needs_operator": True,
                "matching_debug_report": debug_report.model_dump(mode="json") if debug_report else None,  # SPRINT C2.18A
            }
        
        # 2) Filtrar documentos por sujeto (con fallback sin empresa)
        all_candidates: List[MatchResultV1] = []
        debug_info["document_queries"] = []
        docs_after_subject_filter = 0  # SPRINT C2.18A: Contador para pipeline
        total_docs_after_type_filter = 0  # SPRINT C2.18A: Contador para pipeline
        
        # SPRINT C2.18A: Paso 3: filter: type_id (después de matching por aliases)
        if debug_report:
            # Contar docs por cada type_id candidato (sin filtros de subject/period)
            docs_by_type_before_subject = {}
            for doc_type, _ in matching_types:
                docs_by_type_before_subject[doc_type.type_id] = len(
                    self.store.list_documents(type_id=doc_type.type_id)
                )
            total_docs_after_type_filter = sum(docs_by_type_before_subject.values())
            debug_report.pipeline.append(PipelineStep(
                step_name="filter: type_id",
                input_count=len(all_docs) if 'all_docs' in locals() else debug_report.meta["repo_docs_total"],
                output_count=total_docs_after_type_filter,
                rule=f"type_id in {[t[0].type_id for t in matching_types]}",
                dropped_sample=[],
            ))
        
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
                    # SPRINT C2.18A: Actualizar debug_report si existe
                    if debug_report:
                        # SPRINT C2.19A: applied_hints vacío aquí (aún no se han aplicado)
                        from backend.shared.matching_debug_report import AppliedHint
                        applied_hints_models = []
                        
                        debug_report.outcome = MatchingOutcome(
                            decision="NO_MATCH",
                            local_docs_considered=0,
                            primary_reason_code=PrimaryReasonCode.PERIOD_FILTER_ZERO,
                            human_hint=f"No hay documentos para el período {pending_period_key}.",
                            applied_hints=applied_hints_models,
                        )
                        if evidence_dir:
                            self._save_debug_report(evidence_dir, pending, debug_report)
                    debug_info["match_result"] = "MISSING_DOC_FOR_PERIOD"
                    debug_info["reasons"] = [f"Missing document for period {pending_period_key}"]
                    if evidence_dir:
                        self._save_debug_info(evidence_dir, debug_info)
                    
                    # SPRINT C2.34: Generar matching_debug_report
                    stage_counts = {
                        "local_docs_considered": len(all_docs) if 'all_docs' in locals() else 0,
                        "local_docs_after_type": total_docs_after_type_filter if 'total_docs_after_type_filter' in locals() else 0,
                        "local_docs_after_scope": 0,
                        "local_docs_after_company": 0,
                        "local_docs_after_person": 0,
                        "local_docs_after_period": 0,
                        "local_docs_after_validity": 0,
                    }
                    context = {
                        "company_key": company_key,
                        "person_key": person_key,
                        "platform_key": platform_key,
                        "period_key": pending_period_key,
                    }
                    type_lookup_info = {
                        "type_id": doc_type.type_id,
                        "found": True,
                        "active": True,
                        "scope": doc_type.scope.value if hasattr(doc_type.scope, 'value') else str(doc_type.scope),
                    }
                    alias_info = {"alias_received": base_text, "matched": True} if base_text else None
                    match_result_dict = {"decision": "NO_MATCH", "best_doc": None, "confidence": 0.0}
                    matching_debug_report_c234 = self.build_matching_debug_report(
                        pending=pending, context=context, repo_docs=[], match_result=match_result_dict,
                        stage_counts=stage_counts, type_lookup_info=type_lookup_info, alias_info=alias_info
                    )
                    
                    return {
                        "best_doc": None,
                        "alternatives": [],
                        "confidence": 0.0,
                        "reasons": [f"Missing document for period {pending_period_key}"],
                        "needs_operator": True,
                        "matching_debug_report": debug_report.model_dump(mode="json") if debug_report else None,  # SPRINT C2.18A
                        "matching_debug_report_c234": matching_debug_report_c234,  # SPRINT C2.34
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
            
            docs_after_subject_filter += len(docs)  # SPRINT C2.18A: Acumular docs después de filtro subject
            
            for doc in docs:
                score, reasons = self.score_document(doc, doc_type, pending, type_confidence)
                all_candidates.append(MatchResultV1(doc, score, reasons))
        
        # SPRINT C2.18A: Paso 4: filter: subject (company_key/person_key)
        if debug_report:
            total_docs_after_type = total_docs_after_type_filter if 'total_docs_after_type_filter' in locals() else 0
            debug_report.pipeline.append(PipelineStep(
                step_name="filter: subject",
                input_count=total_docs_after_type,
                output_count=docs_after_subject_filter,
                rule=f"company_key={company_key}, person_key={person_key}",
                dropped_sample=[],
            ))
        
        # SPRINT C2.18A: Paso 5: filter: period_key (si aplica)
        if debug_report and pending_period_key:
            docs_after_period_filter = len(all_candidates)  # Ya filtrados por period en queries
            debug_report.pipeline.append(PipelineStep(
                step_name="filter: period_key",
                input_count=docs_after_subject_filter,
                output_count=docs_after_period_filter,
                rule=f"period_key={pending_period_key}",
                dropped_sample=[],
            ))
        
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
        
        # SPRINT C2.19A: Aplicar hints de aprendizaje ANTES del ranking final
        # (applied_hints ya inicializado al inicio de la función)
        try:
            from backend.shared.learning_store import LearningStore
            from backend.shared.learning_store import HintStrength
            from backend.shared.text_normalizer import normalize_text as normalize_text_for_hint
            
            # Usar el mismo base_dir que el store para que los tests funcionen
            learning_store = LearningStore(base_dir=self.base_dir)
            
            # Construir portal label normalizado
            portal_type_label_normalized = None
            tipo_doc = pending.tipo_doc
            if tipo_doc:
                portal_type_label_normalized = normalize_text_for_hint(tipo_doc)
            
            # Buscar hints aplicables
            hints = learning_store.find_hints(
                platform="egestiona",  # Por ahora hardcodeado
                type_id=None,  # No filtrar por type_id aquí, el hint lo tiene
                subject_key=company_key,
                person_key=person_key,
                period_key=pending_period_key,
                portal_label_norm=portal_type_label_normalized,
            )
            
            if hints:
                # Filtrar por type_id esperado (si tenemos matching_types)
                matching_type_ids = {t[0].type_id for t in matching_types} if matching_types else set()
                applicable_hints = []
                for hint in hints:
                    expected_type = hint.learned_mapping.get("type_id_expected")
                    # Aplicar hint si:
                    # 1. No tiene type_id esperado (hint genérico)
                    # 2. Es UNKNOWN
                    # 3. Coincide con alguno de los matching_types encontrados
                    # 4. O si no hay matching_types pero el hint tiene un type_id válido (permite resolver casos donde el tipo no se detecta automáticamente)
                    if not expected_type or expected_type == "UNKNOWN" or expected_type in matching_type_ids or (not matching_type_ids and expected_type):
                        applicable_hints.append(hint)
                
                if applicable_hints:
                    # Si hay 1 hint EXACT que apunta a un doc que existe
                    exact_hints = [h for h in applicable_hints if h.strength == HintStrength.EXACT]
                    if len(exact_hints) == 1:
                        hint = exact_hints[0]
                        target_doc_id = hint.learned_mapping.get("local_doc_id")
                        
                        # Buscar el doc en all_candidates o en el store
                        target_doc = None
                        for candidate in all_candidates:
                            if candidate.doc.doc_id == target_doc_id:
                                target_doc = candidate.doc
                                break
                        
                        if not target_doc:
                            # Intentar cargar desde store
                            target_doc = self.store.get_document(target_doc_id)
                        
                        if target_doc:
                            # Verificar condiciones estrictas
                            type_match = not hint.learned_mapping.get("type_id_expected") or target_doc.type_id == hint.learned_mapping.get("type_id_expected")
                            subject_match = not hint.conditions.get("subject_key") or target_doc.company_key == hint.conditions.get("subject_key")
                            period_match = True
                            if hint.conditions.get("period_key") and pending_period_key:
                                period_match = target_doc.period_key == hint.conditions.get("period_key")
                            
                            if type_match and subject_match and period_match:
                                # Resolver directamente
                                score = 1.0
                                reasons = [f"Resolved by learned hint {hint.hint_id}"]
                                hint_result = MatchResultV1(target_doc, score, reasons)
                                
                                # Reemplazar all_candidates con este único candidato
                                all_candidates = [hint_result]
                                
                                applied_hints.append({
                                    "hint_id": hint.hint_id,
                                    "strength": hint.strength.value,
                                    "effect": "resolved",
                                    "reason": "EXACT hint matched, doc verified",
                                })
                            else:
                                applied_hints.append({
                                    "hint_id": hint.hint_id,
                                    "strength": hint.strength.value,
                                    "effect": "ignored",
                                    "reason": f"Conditions mismatch: type={type_match}, subject={subject_match}, period={period_match}",
                                })
                        else:
                            applied_hints.append({
                                "hint_id": hint.hint_id,
                                "strength": hint.strength.value,
                                "effect": "ignored",
                                "reason": f"Target doc {target_doc_id} not found",
                            })
                    elif len(applicable_hints) > 1:
                        # Múltiples hints: solo boost, no resolver
                        for hint in applicable_hints:
                            target_doc_id = hint.learned_mapping.get("local_doc_id")
                            # Buscar en candidates y boostear score
                            for candidate in all_candidates:
                                if candidate.doc.doc_id == target_doc_id:
                                    # Boost suave: +0.2 al score
                                    candidate.score = min(1.0, candidate.score + 0.2)
                                    candidate.reasons.append(f"Boosted by hint {hint.hint_id}")
                                    applied_hints.append({
                                        "hint_id": hint.hint_id,
                                        "strength": hint.strength.value,
                                        "effect": "boosted",
                                        "reason": "Multiple hints, soft boost applied",
                                    })
                                    break
        except Exception as e:
            print(f"[DocumentMatcher] WARNING: Error applying learning hints: {e}")
            # Continuar sin hints si hay error
        
        if not all_candidates:
            # SPRINT C2.18A: Detectar causa específica de NO_MATCH
            if debug_report:
                # Determinar primary_reason_code
                primary_reason = PrimaryReasonCode.UNKNOWN
                human_hint = "No se encontraron documentos después de aplicar filtros."
                
                # SPRINT C2.18A.1: Detectar DATA_DIR_MISMATCH primero (si repo está vacío)
                if debug_report.meta["repo_docs_total"] == 0:
                    data_dir_resolved = debug_report.meta.get("data_dir_resolved")
                    data_dir_expected = debug_report.meta.get("data_dir_expected")
                    
                    # Heurística DATA_DIR_MISMATCH
                    if data_dir_expected:
                        from pathlib import Path
                        resolved_norm = str(Path(data_dir_resolved).resolve())
                        expected_norm = str(Path(data_dir_expected).resolve())
                        
                        if resolved_norm != expected_norm:
                            primary_reason = PrimaryReasonCode.DATA_DIR_MISMATCH
                            expected_source = debug_report.meta.get("data_dir_expected_source", "unknown")
                            human_hint = (
                                f"El repositorio local parece vacío porque data_dir_resolved ({data_dir_resolved}) "
                                f"difiere de data_dir_expected ({data_dir_expected}) "
                                f"(fuente: {expected_source}). "
                                f"Revisa variables de entorno o configuración."
                            )
                        else:
                            primary_reason = PrimaryReasonCode.REPO_EMPTY
                            human_hint = "El repositorio está vacío. No hay documentos disponibles."
                    else:
                        primary_reason = PrimaryReasonCode.REPO_EMPTY
                        human_hint = "El repositorio está vacío. No hay documentos disponibles."
                elif 'total_docs_after_type_filter' in locals() and total_docs_after_type_filter == 0:
                    type_ids_list = debug_report.meta["request_context"].get("type_ids", [])
                    primary_reason = PrimaryReasonCode.TYPE_FILTER_ZERO
                    human_hint = f"No hay documentos del tipo requerido. Tipos buscados: {type_ids_list}."
                elif 'docs_after_subject_filter' in locals() and docs_after_subject_filter == 0:
                    primary_reason = PrimaryReasonCode.SUBJECT_FILTER_ZERO
                    human_hint = f"No hay documentos para company_key={company_key}, person_key={person_key}."
                elif pending_period_key and len(all_candidates) == 0:
                    primary_reason = PrimaryReasonCode.PERIOD_FILTER_ZERO
                    human_hint = f"No hay documentos para el período {pending_period_key}."
                
                # SPRINT C2.19A: Añadir applied_hints al outcome
                from backend.shared.matching_debug_report import AppliedHint
                applied_hints_models = [AppliedHint(**h) for h in applied_hints] if applied_hints else []
                
                debug_report.outcome = MatchingOutcome(
                    decision="NO_MATCH",
                    local_docs_considered=0,
                    primary_reason_code=primary_reason,
                    human_hint=human_hint,
                    applied_hints=applied_hints_models,
                )
                if evidence_dir:
                    self._save_debug_report(evidence_dir, pending, debug_report)
            
            debug_info["match_result"] = "NO_DOCUMENTS_FOUND"
            debug_info["reasons"] = [f"No documents found for company={company_key}, person={person_key}"]
            if evidence_dir:
                self._save_debug_info(evidence_dir, debug_info)
            
            # SPRINT C2.34: Generar matching_debug_report
            stage_counts = {
                "local_docs_considered": len(all_docs) if 'all_docs' in locals() else 0,
                "local_docs_after_type": total_docs_after_type_filter if 'total_docs_after_type_filter' in locals() else 0,
                "local_docs_after_scope": 0,
                "local_docs_after_company": 0,
                "local_docs_after_person": 0,
                "local_docs_after_period": 0,
                "local_docs_after_validity": 0,
            }
            context = {
                "company_key": company_key,
                "person_key": person_key,
                "platform_key": platform_key,
                "period_key": pending_period_key,
            }
            type_lookup_info = None
            if matching_types:
                first_type, _ = matching_types[0]
                type_lookup_info = {
                    "type_id": first_type.type_id,
                    "found": True,
                    "active": True,
                    "scope": first_type.scope.value if hasattr(first_type.scope, 'value') else str(first_type.scope),
                }
            alias_info = {"alias_received": base_text, "matched": len(matching_types) > 0} if base_text else None
            match_result_dict = {"decision": "NO_MATCH", "best_doc": None, "confidence": 0.0}
            matching_debug_report_c234 = self.build_matching_debug_report(
                pending=pending, context=context, repo_docs=[], match_result=match_result_dict,
                stage_counts=stage_counts, type_lookup_info=type_lookup_info, alias_info=alias_info
            )
            
            return {
                "best_doc": None,
                "alternatives": [],
                "confidence": 0.0,
                "reasons": [f"No documents found for company={company_key}, person={person_key}"],
                "needs_operator": True,
                "matching_debug_report": debug_report.model_dump(mode="json") if debug_report else None,  # SPRINT C2.18A
                "matching_debug_report_c234": matching_debug_report_c234,  # SPRINT C2.34
            }
        
        # 3) Ordenar por score descendente
        all_candidates.sort(key=lambda x: x.score, reverse=True)
        
        # SPRINT C2.18A: Paso 6: rank: compute confidence
        if debug_report:
            debug_report.pipeline.append(PipelineStep(
                step_name="rank: compute confidence",
                input_count=len(all_candidates),
                output_count=len(all_candidates),  # Todos pasan, solo se ordenan
                rule="sort_by_score_descending",
                dropped_sample=[],
            ))
        
        best = all_candidates[0]
        alternatives = all_candidates[1:4]  # Hasta 3 alternativas
        
        # SPRINT C2.18A: Paso 7: threshold: min_confidence (0.7)
        threshold = 0.7
        if debug_report:
            candidates_above_threshold = [c for c in all_candidates if c.score >= threshold]
            debug_report.pipeline.append(PipelineStep(
                step_name="threshold: min_confidence",
                input_count=len(all_candidates),
                output_count=len(candidates_above_threshold),
                rule=f"confidence >= {threshold}",
                dropped_sample=[
                    {
                        "doc_id": c.doc.doc_id,
                        "reason": f"confidence_below_threshold ({c.score:.2f} < {threshold})"
                    }
                    for c in all_candidates if c.score < threshold
                ][:5],  # Hasta 5 ejemplos
            ))
            
            # Añadir candidatos top al reporte
            for cand in all_candidates[:5]:
                debug_report.candidates_top.append(CandidateTop(
                    doc_id=cand.doc.doc_id,
                    type_id=cand.doc.type_id,
                    company_key=cand.doc.company_key,
                    person_key=cand.doc.person_key,
                    period_key=cand.doc.period_key,
                    file_path=cand.doc.file_name_original,
                    status=cand.doc.status.value,
                    score_breakdown={
                        "final_confidence": cand.score,
                    },
                    reject_reason=f"confidence_below_threshold ({cand.score:.2f} < {threshold})" if cand.score < threshold else None,
                ))
        
        # 4) Determinar needs_operator
        needs_operator = False
        if best.score < 0.7:
            needs_operator = True
        if len(all_candidates) > 1 and abs(all_candidates[0].score - all_candidates[1].score) < 0.1:
            # Empate cercano
            needs_operator = True
        
        # SPRINT C2.18A: Determinar outcome final
        if debug_report:
            decision = "AUTO_UPLOAD" if best.score >= 0.7 and not needs_operator else "REVIEW_REQUIRED" if best.score >= 0.5 else "NO_MATCH"
            primary_reason = PrimaryReasonCode.UNKNOWN
            human_hint = ""
            
            if decision == "NO_MATCH":
                if best.score < threshold:
                    primary_reason = PrimaryReasonCode.CONFIDENCE_TOO_LOW
                    human_hint = f"Se encontraron candidatos pero ninguno supera el umbral de confianza ({threshold}). Mejor score: {best.score:.2f}."
                else:
                    primary_reason = PrimaryReasonCode.UNKNOWN
                    human_hint = "No se pudo determinar la causa específica."
            elif decision == "REVIEW_REQUIRED":
                primary_reason = PrimaryReasonCode.CONFIDENCE_TOO_LOW
                human_hint = f"Match encontrado pero requiere revisión (confidence={best.score:.2f} < {threshold})."
            else:  # AUTO_UPLOAD
                primary_reason = PrimaryReasonCode.UNKNOWN  # No aplica, hay match
                human_hint = f"Match encontrado con alta confianza (confidence={best.score:.2f})."
            
            # SPRINT C2.19A: Añadir applied_hints al outcome
            from backend.shared.matching_debug_report import AppliedHint
            applied_hints_models = [AppliedHint(**h) for h in applied_hints] if applied_hints else []
            
            debug_report.outcome = MatchingOutcome(
                decision=decision,
                local_docs_considered=len(all_candidates),
                primary_reason_code=primary_reason,
                human_hint=human_hint,
                applied_hints=applied_hints_models,
            )
            if evidence_dir:
                self._save_debug_report(evidence_dir, pending, debug_report)
        
        # SPRINT C2.34: Determinar decision y generar matching_debug_report si aplica
        decision = "AUTO_UPLOAD" if best.score >= 0.7 and not needs_operator else "REVIEW_REQUIRED" if best.score >= 0.5 else "NO_MATCH"
        
        # Recopilar stage_counts para matching_debug_report
        stage_counts = {
            "local_docs_considered": len(all_docs) if 'all_docs' in locals() else 0,
            "local_docs_after_type": total_docs_after_type_filter if 'total_docs_after_type_filter' in locals() else 0,
            "local_docs_after_scope": docs_after_subject_filter if 'docs_after_subject_filter' in locals() else 0,
            "local_docs_after_company": docs_after_subject_filter if 'docs_after_subject_filter' in locals() else 0,  # Aproximación
            "local_docs_after_person": docs_after_subject_filter if 'docs_after_subject_filter' in locals() and person_key else 0,  # Aproximación
            "local_docs_after_period": len(all_candidates) if pending_period_key else len(all_candidates),
            "local_docs_after_validity": len(all_candidates),  # Aproximación: todos los candidatos pasaron validity
        }
        
        # Construir context para matching_debug_report
        context = {
            "company_key": company_key,
            "person_key": person_key,
            "platform_key": platform_key,
            "period_key": pending_period_key,
        }
        
        # Construir type_lookup_info
        type_lookup_info = None
        if matching_types:
            first_type, _ = matching_types[0]
            type_lookup_info = {
                "type_id": first_type.type_id,
                "found": True,
                "active": True,
                "scope": first_type.scope.value if hasattr(first_type.scope, 'value') else str(first_type.scope),
            }
        else:
            # Intentar obtener type_id desde pending si es posible
            type_lookup_info = {
                "type_id": None,
                "found": False,
                "active": False,
                "scope": None,
            }
        
        # Construir alias_info
        alias_info = None
        if base_text:
            alias_info = {
                "alias_received": base_text,
                "matched": len(matching_types) > 0,
            }
        
        # Generar matching_debug_report si decision es NO_MATCH o REVIEW_REQUIRED
        matching_debug_report_c234 = None
        if decision in ("NO_MATCH", "REVIEW_REQUIRED"):
            match_result_dict = {
                "decision": decision,
                "best_doc": best.to_dict() if best else None,
                "confidence": best.score if best else 0.0,
            }
            matching_debug_report_c234 = self.build_matching_debug_report(
                pending=pending,
                context=context,
                repo_docs=all_candidates if all_candidates else [],
                match_result=match_result_dict,
                stage_counts=stage_counts,
                type_lookup_info=type_lookup_info,
                alias_info=alias_info,
            )
        
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
            "matched_rule": None,  # No vino de regla
            "matching_debug_report": debug_report.model_dump(mode="json") if debug_report else None,  # SPRINT C2.18A
            "matching_debug_report_c234": matching_debug_report_c234,  # SPRINT C2.34: Nuevo formato simplificado
        }
    
    def _save_debug_info(self, evidence_dir: Path, debug_info: dict) -> None:
        """Guarda pending_match_debug.json en evidence_dir (legacy)."""
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
    
    def _save_debug_report(self, evidence_dir: Path, pending: PendingItemV1, debug_report: MatchingDebugReportV1) -> None:
        """SPRINT C2.18A: Guarda MatchingDebugReportV1 estructurado en evidence_dir."""
        try:
            # Crear subdirectorio matching_debug
            matching_debug_dir = evidence_dir / "matching_debug"
            matching_debug_dir.mkdir(parents=True, exist_ok=True)
            
            # Generar item_id desde pending_item_key o hash del pending
            import hashlib
            pending_key = f"{pending.tipo_doc}|{pending.elemento}|{pending.empresa}"
            item_id_hash = hashlib.md5(pending_key.encode("utf-8")).hexdigest()[:8]
            item_id = f"item_{item_id_hash}"
            
            # Guardar reporte individual
            report_path = matching_debug_dir / f"{item_id}__debug.json"
            report_path.write_text(
                debug_report.model_dump_json(indent=2, exclude_none=True),
                encoding="utf-8"
            )
            
            # Actualizar índice
            index_path = matching_debug_dir / "index.json"
            index_data = {}
            if index_path.exists():
                try:
                    index_data = json.loads(index_path.read_text(encoding="utf-8"))
                except Exception:
                    index_data = {}
            
            if "items" not in index_data:
                index_data["items"] = []
            
            # Añadir o actualizar entrada
            existing_idx = next((i for i, item in enumerate(index_data["items"]) if item.get("item_id") == item_id), None)
            item_entry = {
                "item_id": item_id,
                "pending_label": debug_report.meta["request_context"]["pending_label"],
                "pending_text": debug_report.meta["request_context"]["pending_text"],
                "outcome": {
                    "decision": debug_report.outcome.decision,
                    "local_docs_considered": debug_report.outcome.local_docs_considered,
                    "primary_reason_code": debug_report.outcome.primary_reason_code.value,
                    "human_hint": debug_report.outcome.human_hint,
                },
                "report_path": str(report_path.relative_to(evidence_dir)),
                "created_at": debug_report.meta["created_at"],
            }
            
            if existing_idx is not None:
                index_data["items"][existing_idx] = item_entry
            else:
                index_data["items"].append(item_entry)
            
            # Actualizar resumen
            index_data["summary"] = {
                "total_items": len(index_data["items"]),
                "no_match_count": len([i for i in index_data["items"] if i["outcome"]["decision"] == "NO_MATCH"]),
                "review_required_count": len([i for i in index_data["items"] if i["outcome"]["decision"] == "REVIEW_REQUIRED"]),
                "auto_upload_count": len([i for i in index_data["items"] if i["outcome"]["decision"] == "AUTO_UPLOAD"]),
                "repo_empty_count": len([i for i in index_data["items"] if i["outcome"]["primary_reason_code"] == "REPO_EMPTY"]),
                "type_filter_zero_count": len([i for i in index_data["items"] if i["outcome"]["primary_reason_code"] == "TYPE_FILTER_ZERO"]),
                "subject_filter_zero_count": len([i for i in index_data["items"] if i["outcome"]["primary_reason_code"] == "SUBJECT_FILTER_ZERO"]),
                "period_filter_zero_count": len([i for i in index_data["items"] if i["outcome"]["primary_reason_code"] == "PERIOD_FILTER_ZERO"]),
                "confidence_too_low_count": len([i for i in index_data["items"] if i["outcome"]["primary_reason_code"] == "CONFIDENCE_TOO_LOW"]),
            }
            
            index_path.write_text(
                json.dumps(index_data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            # No fallar si no se puede guardar debug report
            print(f"[MATCHING_DEBUG] Error guardando debug report: {e}")
            pass
    
    def build_matching_debug_report(
        self,
        pending: PendingItemV1,
        context: Dict[str, Any],
        repo_docs: List[DocumentInstanceV1],
        match_result: Dict[str, Any],
        stage_counts: Dict[str, int],
        type_lookup_info: Optional[Dict[str, Any]] = None,
        alias_info: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        SPRINT C2.34: Genera matching_debug_report determinista cuando decision es NO_MATCH/REVIEW_REQUIRED.
        
        Esta función es pura y determinista: mismo input -> mismo output.
        No modifica la lógica de matching, solo añade explicación.
        
        Args:
            pending: Item pendiente
            context: Contexto con company_key, person_key, platform_key, etc.
            repo_docs: Lista de documentos del repositorio considerados
            match_result: Resultado del matching (con decision, best_doc, etc.)
            stage_counts: Contadores por etapa del pipeline
            type_lookup_info: Info sobre búsqueda de tipos (opcional)
            alias_info: Info sobre aliases (opcional)
        
        Returns:
            Dict con matching_debug_report o None si no aplica
        """
        decision = match_result.get("decision")
        if decision not in ("NO_MATCH", "REVIEW_REQUIRED"):
            # Solo generar report para NO_MATCH o REVIEW_REQUIRED
            return None
        
        # Obtener pending_id (si existe en pending o generar desde datos)
        pending_id = getattr(pending, "item_id", None) or f"{pending.tipo_doc}|{pending.elemento}"
        
        # Construir filters_applied
        filters_applied = {
            "own_company_key": context.get("own_company_key"),
            "company_key": context.get("company_key"),
            "person_key": context.get("person_key"),
            "period_key": context.get("period_key"),
            "platform_key": context.get("platform_key", "egestiona"),
        }
        
        # Construir reasons (ordenados por prioridad)
        reasons = []
        
        # 1. NO_LOCAL_DOCS: Si no hay docs en repo o lista filtrada inicial vacía
        local_docs_considered = stage_counts.get("local_docs_considered", len(repo_docs))
        if local_docs_considered == 0:
            reasons.append(make_reason(
                NO_LOCAL_DOCS,
                "No hay documentos en el repositorio para este requisito",
                "Subir el documento correspondiente al repositorio"
            ))
        
        # 2. TYPE_NOT_FOUND / TYPE_INACTIVE: Si type_id no existe o está inactivo
        if type_lookup_info:
            type_id = type_lookup_info.get("type_id")
            type_found = type_lookup_info.get("found", False)
            type_active = type_lookup_info.get("active", False)
            
            if not type_found:
                reasons.append(make_reason(
                    TYPE_NOT_FOUND,
                    f"El tipo de documento no existe en el catálogo",
                    "Revisar configuración de tipos de documento",
                    {"type_id_attempted": type_id}
                ))
            elif not type_active:
                reasons.append(make_reason(
                    TYPE_INACTIVE,
                    f"El tipo de documento está inactivo",
                    "Activar el tipo de documento en el catálogo",
                    {"type_id": type_id}
                ))
        
        # 3. ALIAS_NOT_MATCHING: Si alias/platform_name no puede mapearse
        if alias_info:
            alias_received = alias_info.get("alias_received")
            alias_matched = alias_info.get("matched", False)
            if alias_received and not alias_matched:
                reasons.append(make_reason(
                    ALIAS_NOT_MATCHING,
                    f"No se reconoce el alias '{alias_received}' en esta plataforma",
                    "Revisar alias del tipo o configuración de plataforma",
                    {"alias_received": alias_received}
                ))
        
        # 4. SCOPE_MISMATCH: Si pending es worker pero type scope es company-only, o viceversa
        pending_scope = "worker" if pending.trabajador else "company"
        if type_lookup_info:
            type_scope = type_lookup_info.get("scope")
            if type_scope and pending_scope != type_scope:
                reasons.append(make_reason(
                    SCOPE_MISMATCH,
                    f"El tipo de documento es de scope '{type_scope}' pero el requisito es '{pending_scope}'",
                    "Revisar el scope del tipo de documento o el requisito",
                    {"pending_scope": pending_scope, "type_scope": type_scope}
                ))
        
        # 5. COMPANY_MISMATCH / PERSON_MISMATCH: Si hay docs del type pero para otra company/person
        docs_after_type = stage_counts.get("local_docs_after_type", 0)
        docs_after_company = stage_counts.get("local_docs_after_company", 0)
        docs_after_person = stage_counts.get("local_docs_after_person", 0)
        
        if docs_after_type > 0 and docs_after_company == 0:
            company_key = context.get("company_key")
            reasons.append(make_reason(
                COMPANY_MISMATCH,
                f"Hay documentos del tipo pero para otra empresa (buscado: {company_key})",
                "Revisar asignación de empresa en los documentos",
                {"company_key_searched": company_key}
            ))
        
        if pending_scope == "worker" and docs_after_company > 0 and docs_after_person == 0:
            person_key = context.get("person_key")
            reasons.append(make_reason(
                PERSON_MISMATCH,
                f"Hay documentos del tipo pero para otro trabajador (buscado: {person_key})",
                "Revisar asignación de trabajador en los documentos",
                {"person_key_searched": person_key}
            ))
        
        # 6. PERIOD_MISMATCH: Si period_key existe y no hay docs que cubran ese period_key
        period_key = context.get("period_key")
        docs_after_period = stage_counts.get("local_docs_after_period", 0)
        if period_key and docs_after_company > 0 and docs_after_period == 0:
            reasons.append(make_reason(
                PERIOD_MISMATCH,
                f"Hay documentos, pero no cubren el periodo {period_key}",
                "Sube el documento del periodo correcto o revisa el periodo",
                {"period_key_searched": period_key}
            ))
        
        # 7. VALIDITY_MISMATCH: Si tras validity filter no queda nada
        docs_after_validity = stage_counts.get("local_docs_after_validity", 0)
        if docs_after_period > 0 and docs_after_validity == 0:
            reasons.append(make_reason(
                VALIDITY_MISMATCH,
                "Hay documentos pero ninguno es válido para la fecha actual",
                "Revisar fechas de validez de los documentos o subir uno válido"
            ))
        
        # Asegurar que hay al menos un reason
        if not reasons:
            reasons.append(make_reason(
                NO_LOCAL_DOCS,
                "No se pudo determinar la causa específica",
                "Revisar configuración y documentos disponibles"
            ))
        
        # Ordenar reasons por prioridad (ya están en orden de prioridad por cómo se añaden)
        # Pero asegurar orden determinista: ordenar por code
        reasons_sorted = sorted(reasons, key=lambda r: r["code"])
        
        # Construir counters (best-effort)
        counters = {
            "local_docs_considered": stage_counts.get("local_docs_considered", 0),
            "local_docs_after_type": stage_counts.get("local_docs_after_type", 0),
            "local_docs_after_scope": stage_counts.get("local_docs_after_scope", 0),
            "local_docs_after_company": stage_counts.get("local_docs_after_company", 0),
            "local_docs_after_person": stage_counts.get("local_docs_after_person", 0),
            "local_docs_after_period": stage_counts.get("local_docs_after_period", 0),
            "local_docs_after_validity": stage_counts.get("local_docs_after_validity", 0),
        }
        
        # Construir report determinista
        report = {
            "pending_id": pending_id,
            "decision": decision,
            "filters_applied": filters_applied,
            "reasons": reasons_sorted,
            "counters": counters,
        }
        
        # Asegurar orden determinista en JSON (sort_keys al serializar)
        return report

