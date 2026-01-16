"""
Planificador de envíos CAE v1.1.

Genera planes deterministas y auditable a partir del repositorio y un scope explícito.
NO ejecuta subidas reales, solo planifica.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict
from pathlib import Path

from backend.cae.submission_models_v1 import (
    CAEScopeContextV1,
    CAEPlanDecisionV1,
    CAESubmissionPlanV1,
    CAESubmissionItemV1,
)
from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
from backend.repository.period_planner_v1 import PeriodPlannerV1
from backend.repository.document_status_calculator_v1 import calculate_document_status
from backend.shared.document_repository_v1 import DocumentTypeV1, DocumentInstanceV1, PeriodKindV1


class CAESubmissionPlannerV1:
    """Planificador de envíos CAE."""
    
    def __init__(self, store: Optional[DocumentRepositoryStoreV1] = None):
        self.store = store or DocumentRepositoryStoreV1()
        self.planner = PeriodPlannerV1(self.store)
    
    def generate_plan_id(self) -> str:
        """Genera un plan_id único: CAEPLAN-YYYYMMDD-HHMMSS-<shortid>"""
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d-%H%M%S")
        short_id = str(uuid.uuid4())[:8]
        return f"CAEPLAN-{timestamp}-{short_id}"
    
    def plan_submission(self, scope: CAEScopeContextV1) -> CAESubmissionPlanV1:
        """
        Genera un plan de envío basado en el scope.
        
        REGLAS:
        - NO infiere/amplía scope: solo usa el scope explícito
        - Fechas: deterministas; si hay ambigüedad -> NEEDS_CONFIRMATION
        - Si scope inválido o sin docs -> BLOCKED
        """
        plan_id = self.generate_plan_id()
        created_at = datetime.now()
        
        # Validar scope básico
        if not scope.platform_key:
            return CAESubmissionPlanV1(
                plan_id=plan_id,
                created_at=created_at,
                scope=scope,
                decision="BLOCKED",
                reasons=["platform_key es requerido"],
                items=[],
                summary={"pending_items": 0, "docs_candidates": 0},
                executor_hint=None,
            )
        
        # Determinar tipos a procesar
        types_to_process = self._resolve_types(scope)
        if not types_to_process:
            return CAESubmissionPlanV1(
                plan_id=plan_id,
                created_at=created_at,
                scope=scope,
                decision="BLOCKED",
                reasons=["No hay tipos de documento que coincidan con el scope"],
                items=[],
                summary={"pending_items": 0, "docs_candidates": 0},
                executor_hint=self._get_executor_hint(scope.platform_key),
            )
        
        # Generar items
        items: List[CAESubmissionItemV1] = []
        reasons: List[str] = []
        needs_confirmation = False
        
        for doc_type in types_to_process:
            type_items, type_reasons, type_needs_confirmation = self._process_type(
                doc_type=doc_type,
                scope=scope,
            )
            items.extend(type_items)
            reasons.extend(type_reasons)
            if type_needs_confirmation:
                needs_confirmation = True
        
        # Determinar decisión
        if not items:
            decision: CAEPlanDecisionV1 = "BLOCKED"
            if not reasons:
                reasons.append("No hay documentos o períodos faltantes en el scope especificado")
        elif needs_confirmation:
            decision = "NEEDS_CONFIRMATION"
        else:
            decision = "READY"
        
        # Calcular summary (con protección contra errores)
        try:
            pending_items = len([i for i in items if i.kind == "MISSING_PERIOD"])
            docs_candidates = len([i for i in items if i.kind == "DOC_INSTANCE"])
            
            summary = {
                "pending_items": pending_items,
                "docs_candidates": docs_candidates,
                "total_items": len(items),
                "types_processed": len(types_to_process),
            }
        except Exception:
            # Si hay error al calcular summary, usar valores por defecto
            summary = {
                "pending_items": 0,
                "docs_candidates": 0,
                "total_items": len(items),
                "types_processed": len(types_to_process),
            }
        
        return CAESubmissionPlanV1(
            plan_id=plan_id,
            created_at=created_at,
            scope=scope,
            decision=decision,
            reasons=reasons,
            items=items,
            summary=summary,
            executor_hint=self._get_executor_hint(scope.platform_key),
        )
    
    def _resolve_types(self, scope: CAEScopeContextV1) -> List[DocumentTypeV1]:
        """
        Resuelve qué tipos procesar según el scope.
        
        IMPORTANTE: NO infiere. Si type_ids está vacío, retorna lista vacía.
        El frontend debe enviar la lista explícita de tipos visibles.
        """
        try:
            all_types = self.store.list_types(include_inactive=False)
        except Exception:
            # Si hay error al listar tipos (repositorio vacío, etc.), retornar lista vacía
            return []
        
        if not scope.type_ids:
            # Lista vacía: el frontend no especificó tipos
            # Por regla, NO inferimos "todos", retornamos vacío
            return []
        
        # Filtrar por type_ids explícitos
        result = []
        for type_id in scope.type_ids:
            doc_type = self.store.get_type(type_id)
            if doc_type and doc_type.active:
                # Aplicar filtros adicionales del scope
                if scope.company_key and doc_type.scope.value == "worker":
                    # Si hay company_key, solo tipos worker
                    result.append(doc_type)
                elif scope.company_key and doc_type.scope.value == "company":
                    # Si hay company_key, también tipos company
                    result.append(doc_type)
                elif not scope.company_key:
                    # Sin company_key, incluir todos los tipos que coincidan
                    result.append(doc_type)
        
        return result
    
    def _process_type(
        self,
        doc_type: DocumentTypeV1,
        scope: CAEScopeContextV1,
    ) -> tuple[List[CAESubmissionItemV1], List[str], bool]:
        """
        Procesa un tipo de documento y genera items.
        
        Returns:
            (items, reasons, needs_confirmation)
        """
        items: List[CAESubmissionItemV1] = []
        reasons: List[str] = []
        needs_confirmation = False
        
        # Determinar sujetos a procesar
        subjects = self._resolve_subjects(doc_type, scope)
        if not subjects:
            reasons.append(f"No hay sujetos que coincidan con el scope para {doc_type.type_id}")
            return items, reasons, needs_confirmation
        
        # Procesar cada sujeto
        for subject_scope, company_key, person_key in subjects:
            # Si hay period_keys específicos, usar esos
            if scope.period_keys:
                for period_key in scope.period_keys:
                    item, item_reasons, item_needs_confirmation = self._process_period(
                        doc_type=doc_type,
                        scope_context=scope,
                        subject_scope=subject_scope,
                        company_key=company_key,
                        person_key=person_key,
                        period_key=period_key,
                    )
                    if item:
                        items.append(item)
                    reasons.extend(item_reasons)
                    if item_needs_confirmation:
                        needs_confirmation = True
            else:
                # Sin period_keys específicos: buscar períodos faltantes o documentos existentes
                period_items, period_reasons, period_needs_confirmation = self._process_type_subject(
                    doc_type=doc_type,
                    scope_context=scope,
                    subject_scope=subject_scope,
                    company_key=company_key,
                    person_key=person_key,
                )
                items.extend(period_items)
                reasons.extend(period_reasons)
                if period_needs_confirmation:
                    needs_confirmation = True
        
        return items, reasons, needs_confirmation
    
    def _resolve_subjects(
        self,
        doc_type: DocumentTypeV1,
        scope: CAEScopeContextV1,
    ) -> List[tuple[str, Optional[str], Optional[str]]]:
        """
        Resuelve qué sujetos procesar según el scope.
        
        Returns:
            Lista de (scope, company_key, person_key)
        """
        subjects: List[tuple[str, Optional[str], Optional[str]]] = []
        
        # Si el tipo requiere scope específico, validar
        if doc_type.scope.value == "company":
            if scope.company_key:
                subjects.append(("company", scope.company_key, None))
            else:
                # Sin company_key pero tipo company: buscar todas las empresas con docs de este tipo
                try:
                    all_docs = self.store.list_documents(type_id=doc_type.type_id, scope="company")
                    company_keys = set(d.company_key for d in all_docs if d.company_key)
                    for ck in company_keys:
                        subjects.append(("company", ck, None))
                except Exception:
                    # Si hay error, continuar sin añadir sujetos
                    pass
        
        elif doc_type.scope.value == "worker":
            if scope.company_key and scope.person_key:
                # Si se especifican ambos, usarlos directamente (no buscar en docs)
                subjects.append(("worker", scope.company_key, scope.person_key))
            elif scope.company_key:
                # Solo company_key: buscar todos los trabajadores de esa empresa con docs de este tipo
                try:
                    all_docs = self.store.list_documents(
                        type_id=doc_type.type_id,
                        scope="worker",
                        company_key=scope.company_key,
                    )
                    person_keys = set((d.company_key, d.person_key) for d in all_docs if d.company_key and d.person_key)
                    if person_keys:
                        for ck, pk in person_keys:
                            subjects.append(("worker", ck, pk))
                    # Si no hay docs pero hay company_key, aún así podemos procesar (para períodos faltantes)
                    # No añadir sujeto aquí, se manejará en _process_type_subject
                except Exception:
                    # Si hay error, continuar sin añadir sujetos
                    pass
            else:
                # Sin filtros: buscar todos los trabajadores con docs de este tipo
                try:
                    all_docs = self.store.list_documents(type_id=doc_type.type_id, scope="worker")
                    person_keys = set((d.company_key, d.person_key) for d in all_docs if d.company_key and d.person_key)
                    for ck, pk in person_keys:
                        subjects.append(("worker", ck, pk))
                except Exception:
                    # Si hay error, continuar sin añadir sujetos
                    pass
        
        return subjects
    
    def _process_type_subject(
        self,
        doc_type: DocumentTypeV1,
        scope_context: CAEScopeContextV1,
        subject_scope: str,
        company_key: Optional[str],
        person_key: Optional[str],
    ) -> tuple[List[CAESubmissionItemV1], List[str], bool]:
        """
        Procesa un tipo para un sujeto específico, buscando períodos faltantes o documentos.
        """
        items: List[CAESubmissionItemV1] = []
        reasons: List[str] = []
        needs_confirmation = False
        
        # Verificar si es tipo periódico
        try:
            period_kind = self.planner.get_period_kind_from_type(doc_type)
        except Exception:
            # Si hay error al obtener period_kind, asumir NONE
            period_kind = PeriodKindV1.NONE
        
        if period_kind != PeriodKindV1.NONE:
            # Tipo periódico: buscar períodos faltantes
            try:
                periods = self.planner.generate_expected_periods(
                    doc_type=doc_type,
                    months_back=24,  # Por defecto, ajustable si es necesario
                    company_key=company_key,
                    person_key=person_key,
                )
            except Exception:
                # Si hay error al generar períodos, continuar con lista vacía
                periods = []
            
            for period in periods:
                if period.status.value in ("MISSING", "LATE"):
                    item, item_reasons, item_needs_confirmation = self._process_period(
                        doc_type=doc_type,
                        scope_context=scope_context,
                        subject_scope=subject_scope,
                        company_key=company_key,
                        person_key=person_key,
                        period_key=period.period_key,
                    )
                    if item:
                        items.append(item)
                    reasons.extend(item_reasons)
                    if item_needs_confirmation:
                        needs_confirmation = True
        else:
            # Tipo no periódico: buscar documentos existentes que puedan enviarse
            try:
                docs = self.store.list_documents(
                    type_id=doc_type.type_id,
                    scope=subject_scope,
                    company_key=company_key,
                    person_key=person_key,
                )
            except Exception:
                # Si hay error al listar documentos, continuar con lista vacía
                docs = []
            
            for doc in docs:
                # Solo documentos que estén en estado válido para enviar
                try:
                    doc_type_obj = self.store.get_type(doc.type_id)
                    if doc_type_obj:
                        try:
                            status, _, _, _, _ = calculate_document_status(doc, doc_type=doc_type_obj)
                            if status.value in ("VALID", "EXPIRING_SOON"):
                                item, item_reasons, item_needs_confirmation = self._process_document(
                                    doc=doc,
                                    doc_type=doc_type,
                                    scope_context=scope_context,
                                )
                                if item:
                                    items.append(item)
                                reasons.extend(item_reasons)
                                if item_needs_confirmation:
                                    needs_confirmation = True
                        except Exception:
                            # Si hay error al calcular estado, continuar con siguiente documento
                            pass
                except Exception:
                    # Si hay error al obtener tipo, continuar con siguiente documento
                    pass
        
        return items, reasons, needs_confirmation
    
    def _process_period(
        self,
        doc_type: DocumentTypeV1,
        scope_context: CAEScopeContextV1,
        subject_scope: str,
        company_key: Optional[str],
        person_key: Optional[str],
        period_key: str,
    ) -> tuple[Optional[CAESubmissionItemV1], List[str], bool]:
        """
        Procesa un período específico y genera un item MISSING_PERIOD.
        """
        reasons: List[str] = []
        needs_confirmation = False
        
        # Verificar si existe documento para este período
        try:
            existing_docs = self.store.list_documents(
                type_id=doc_type.type_id,
                scope=subject_scope,
                company_key=company_key,
                person_key=person_key,
                period_key=period_key,
            )
        except Exception:
            # Si hay error al listar documentos, asumir que no existen
            existing_docs = []
        
        if existing_docs:
            # Ya existe documento: no es missing, pero podría ser candidato
            # Por ahora, solo generamos items para períodos faltantes
            return None, reasons, needs_confirmation
        
        # Resolver fechas del período
        resolved_dates, date_reasons, date_needs_confirmation = self._resolve_period_dates(
            doc_type=doc_type,
            period_key=period_key,
        )
        reasons.extend(date_reasons)
        if date_needs_confirmation:
            needs_confirmation = True
        
        # Si no se pudieron resolver las fechas, aún así crear el item pero con status NEEDS_CONFIRMATION
        if resolved_dates is None:
            needs_confirmation = True
            if not reasons:
                reasons.append("No se pudieron resolver las fechas del período")
        
        status = "NEEDS_CONFIRMATION" if needs_confirmation else "PLANNED"
        
        item = CAESubmissionItemV1(
            kind="MISSING_PERIOD",
            type_id=doc_type.type_id,
            scope=subject_scope,
            company_key=company_key,
            person_key=person_key,
            period_key=period_key,
            suggested_doc_id=None,
            resolved_dates=resolved_dates,
            status=status,
            reason="; ".join(reasons) if reasons else "Período faltante",
        )
        
        return item, reasons, needs_confirmation
    
    def _process_document(
        self,
        doc: DocumentInstanceV1,
        doc_type: DocumentTypeV1,
        scope_context: CAEScopeContextV1,
    ) -> tuple[Optional[CAESubmissionItemV1], List[str], bool]:
        """
        Procesa un documento existente y genera un item DOC_INSTANCE.
        """
        reasons: List[str] = []
        needs_confirmation = False
        
        # Resolver fechas del documento
        resolved_dates, date_reasons, date_needs_confirmation = self._resolve_document_dates(
            doc=doc,
            doc_type=doc_type,
        )
        reasons.extend(date_reasons)
        if date_needs_confirmation:
            needs_confirmation = True
        
        status = "NEEDS_CONFIRMATION" if needs_confirmation else "PLANNED"
        
        item = CAESubmissionItemV1(
            kind="DOC_INSTANCE",
            type_id=doc.type_id,
            scope=doc.scope.value,
            company_key=doc.company_key,
            person_key=doc.person_key,
            period_key=doc.period_key,
            suggested_doc_id=doc.doc_id,
            resolved_dates=resolved_dates,
            status=status,
            reason="; ".join(reasons) if reasons else "Documento candidato para envío",
        )
        
        return item, reasons, needs_confirmation
    
    def _resolve_period_dates(
        self,
        doc_type: DocumentTypeV1,
        period_key: str,
    ) -> tuple[Optional[dict], List[str], bool]:
        """
        Resuelve fechas para un período.
        
        Returns:
            (resolved_dates, reasons, needs_confirmation)
        """
        reasons: List[str] = []
        needs_confirmation = False
        
        # Parsear period_key (YYYY-MM o YYYY)
        try:
            if len(period_key) == 7 and period_key[4] == "-":  # YYYY-MM
                year, month = map(int, period_key.split("-"))
                period_start = date(year, month, 1)
                if month == 12:
                    period_end = date(year, 12, 31)
                else:
                    period_end = date(year, month + 1, 1) - timedelta(days=1)
            elif len(period_key) == 4:  # YYYY
                year = int(period_key)
                period_start = date(year, 1, 1)
                period_end = date(year, 12, 31)
            else:
                reasons.append(f"Formato de period_key no reconocido: {period_key}")
                needs_confirmation = True
                return None, reasons, needs_confirmation
        except (ValueError, IndexError) as e:
            reasons.append(f"Error al parsear period_key {period_key}: {e}")
            needs_confirmation = True
            return None, reasons, needs_confirmation
        
        # Determinar fechas según configuración del tipo
        policy = doc_type.validity_policy
        
        if policy.mode.value == "monthly" and policy.monthly:
            # Mensual: valid_from y valid_to según configuración
            if policy.monthly.valid_from == "period_start":
                valid_from = period_start
            elif policy.monthly.valid_from == "period_end":
                valid_from = period_end
            else:
                valid_from = period_start  # Default
            
            if policy.monthly.valid_to == "period_end":
                valid_to = period_end
            elif policy.monthly.valid_to == "period_start":
                valid_to = period_start
            else:
                valid_to = period_end  # Default
            
            # issued_at: usar inicio del período como aproximación
            issued_at = period_start
        elif policy.mode.value == "annual":
            # Anual: usar todo el año
            valid_from = period_start
            valid_to = period_end
            issued_at = period_start
        else:
            # Otro modo: usar período como aproximación
            valid_from = period_start
            valid_to = period_end
            issued_at = period_start
            reasons.append(f"Modo de validez {policy.mode.value} no tiene resolución de fechas específica")
            needs_confirmation = True
        
        resolved_dates = {
            "issued_at": issued_at.isoformat(),
            "valid_from": valid_from.isoformat(),
            "valid_to": valid_to.isoformat(),
        }
        
        return resolved_dates, reasons, needs_confirmation
    
    def _resolve_document_dates(
        self,
        doc: DocumentInstanceV1,
        doc_type: DocumentTypeV1,
    ) -> tuple[Optional[dict], List[str], bool]:
        """
        Resuelve fechas para un documento existente.
        
        Returns:
            (resolved_dates, reasons, needs_confirmation)
        """
        reasons: List[str] = []
        needs_confirmation = False
        
        # Usar fechas del documento si están disponibles
        issued_at = doc.issued_at or (doc.extracted.issue_date if doc.extracted else None)
        valid_from = None
        valid_to = None
        
        if doc.computed_validity:
            valid_from = doc.computed_validity.valid_from
            valid_to = doc.computed_validity.valid_to
        
        # Si faltan fechas, intentar calcularlas
        # v1.8.2: Si el documento tiene computed_validity completo, no necesitamos confirmación
        if not issued_at:
            reasons.append("issued_at no disponible en el documento")
            # Solo marcar needs_confirmation si realmente falta issued_at Y no tenemos valid_from/valid_to
            if not valid_from or not valid_to:
                needs_confirmation = True
        
        if not valid_from or not valid_to:
            # Intentar calcular desde el tipo
            if doc.period_key:
                period_dates, period_reasons, period_needs_confirmation = self._resolve_period_dates(
                    doc_type=doc_type,
                    period_key=doc.period_key,
                )
                if period_dates:
                    if not valid_from:
                        try:
                            valid_from = date.fromisoformat(period_dates["valid_from"])
                        except:
                            pass
                    if not valid_to:
                        try:
                            valid_to = date.fromisoformat(period_dates["valid_to"])
                        except:
                            pass
                reasons.extend(period_reasons)
                # v1.8.2: Solo marcar needs_confirmation si realmente no pudimos resolver las fechas
                if period_needs_confirmation and (not valid_from or not valid_to):
                    needs_confirmation = True
            else:
                reasons.append("valid_from/valid_to no disponibles y no hay period_key")
                needs_confirmation = True
        
        # v1.8.2: Si tenemos todas las fechas necesarias (valid_from y valid_to), no necesitamos confirmación
        if valid_from and valid_to:
            needs_confirmation = False
        
        resolved_dates = {}
        if issued_at:
            resolved_dates["issued_at"] = issued_at.isoformat() if isinstance(issued_at, date) else str(issued_at)
        if valid_from:
            resolved_dates["valid_from"] = valid_from.isoformat() if isinstance(valid_from, date) else str(valid_from)
        if valid_to:
            resolved_dates["valid_to"] = valid_to.isoformat() if isinstance(valid_to, date) else str(valid_to)
        
        if not resolved_dates:
            return None, reasons, needs_confirmation
        
        # v1.8.2: Si tenemos todas las fechas necesarias (valid_from y valid_to), no necesitamos confirmación
        # incluso si falta issued_at (puede ser opcional en algunos casos)
        if valid_from and valid_to:
            needs_confirmation = False
            # Limpiar razones relacionadas con falta de fechas si ya las tenemos
            reasons = [r for r in reasons if "no disponible" not in r.lower() and "no hay period_key" not in r.lower()]
        
        return resolved_dates, reasons, needs_confirmation
    
    def _get_executor_hint(self, platform_key: str) -> Optional[str]:
        """Retorna el hint del executor según la plataforma."""
        if platform_key == "egestiona":
            return "egestiona_upload_v1"
        return None

