"""
Rutas para planificación de envíos CAE v1.1.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.cae.submission_models_v1 import (
    CAEScopeContextV1,
    CAESubmissionPlanV1,
    CAESubmissionItemV1,
)
from backend.cae.submission_planner_v1 import CAESubmissionPlannerV1
from backend.cae.execution_models_v1 import (
    ChallengeRequestV1,
    ChallengeResponseV1,
    ExecuteRequestV1,
    RunResultV1,
)
from backend.cae.execution_runner_v1 import CAEExecutionRunnerV1
from backend.config import DATA_DIR


router = APIRouter(
    prefix="/api/cae",
    tags=["cae"],
)


# ========== v1.5: Document Candidates ==========

class DocCandidateResponse(BaseModel):
    """Respuesta con candidatos de documentos."""
    candidates: List[dict]
    fallback_applied: bool = False
    best_doc_id: Optional[str] = None
    best_reason: Optional[str] = None


@router.get("/doc_candidates", response_model=DocCandidateResponse)
async def get_doc_candidates(
    type_id: str,
    scope: str,  # "company" | "worker"
    company_key: Optional[str] = None,
    person_key: Optional[str] = None,
    period_key: Optional[str] = None,
    allow_period_fallback: bool = False,
    include_best: bool = False,
) -> DocCandidateResponse:
    """
    Lista candidatos de documentos para un pending item.
    
    Filtra por type_id, scope, company_key, person_key, period_key.
    Ordena por: status reviewed/submitted primero, luego por updated_at desc.
    Limita a 50.
    
    Si period_key está presente y no hay documentos con ese period_key:
    - Si allow_period_fallback=false: devuelve [] (fallback_applied=false)
    - Si allow_period_fallback=true: devuelve docs del mismo tipo/sujeto sin filtrar por period_key (fallback_applied=true)
    """
    from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
    from backend.repository.document_status_calculator_v1 import calculate_document_status
    
    try:
        import logging
        logger = logging.getLogger(__name__)
        
        store = DocumentRepositoryStoreV1()
        
        # Validar scope
        if scope not in ["company", "worker"]:
            raise HTTPException(status_code=400, detail=f"scope debe ser 'company' o 'worker', es '{scope}'")
        
        # Normalizar strings vacíos a None
        if company_key == '':
            company_key = None
        if person_key == '':
            person_key = None
        
        logger.info(f"[doc_candidates] type_id={type_id}, scope={scope}, company_key={company_key}, person_key={person_key}, period_key={period_key}")
        
        # Validar sujeto según scope
        if scope == "company":
            if not company_key:
                raise HTTPException(status_code=400, detail="company_key requerido para scope=company")
            if person_key:
                raise HTTPException(status_code=400, detail="person_key debe ser null para scope=company")
        elif scope == "worker":
            if not company_key or not person_key:
                logger.warning(f"[doc_candidates] Missing required keys for worker scope: company_key={company_key}, person_key={person_key}")
                raise HTTPException(status_code=400, detail="company_key y person_key requeridos para scope=worker")
        
        # Listar documentos con filtros
        fallback_applied = False
        docs = store.list_documents(
            type_id=type_id,
            scope=scope,
            company_key=company_key,
            person_key=person_key,
            period_key=period_key,
        )
        
        # Si period_key está presente y no hay documentos con ese period_key
        if period_key and len(docs) == 0:
            if allow_period_fallback:
                # Fallback: buscar sin filtrar por period_key
                docs = store.list_documents(
                    type_id=type_id,
                    scope=scope,
                    company_key=company_key,
                    person_key=person_key,
                    period_key=None,  # Sin filtrar por period_key
                )
                fallback_applied = True
            else:
                # Sin fallback: devolver lista vacía
                docs = []
                fallback_applied = False
        
        # Obtener tipo para calcular estados
        doc_type = store.get_type(type_id)
        
        # Preparar candidatos con información relevante
        candidates = []
        for doc in docs:
            # Calcular estado de validez
            validity_status, _, _, _, _ = calculate_document_status(doc, doc_type=doc_type)
            
            # Verificar que el PDF existe
            try:
                pdf_path = store._get_doc_pdf_path(doc.doc_id)
                pdf_exists = pdf_path.exists()
            except Exception:
                pdf_exists = False
            
            # Obtener SHA256 si existe
            sha256 = None
            if hasattr(doc, 'file_sha256') and doc.file_sha256:
                sha256 = doc.file_sha256
            elif hasattr(doc, 'sha256'):
                sha256 = doc.sha256
            
            candidate = {
                "doc_id": doc.doc_id,
                "type_id": doc.type_id,  # Necesario para ranking
                "scope": doc.scope.value if hasattr(doc.scope, 'value') else str(doc.scope),
                "company_key": doc.company_key if hasattr(doc, 'company_key') else None,
                "person_key": doc.person_key if hasattr(doc, 'person_key') else None,
                "period_key": doc.period_key if hasattr(doc, 'period_key') else None,
                "file_name_original": doc.file_name_original,
                "issued_at": doc.issued_at.isoformat() if doc.issued_at else None,
                "valid_to": None,
                "status": doc.status.value if hasattr(doc.status, 'value') else str(doc.status),
                "validity_status": validity_status.value if hasattr(validity_status, 'value') else str(validity_status),
                "sha256": sha256,
                "pdf_exists": pdf_exists,
                "updated_at": doc.updated_at.isoformat() if hasattr(doc, 'updated_at') and doc.updated_at else None,
            }
            
            # Añadir valid_to si existe
            if hasattr(doc, 'computed_validity') and doc.computed_validity:
                if doc.computed_validity.valid_to:
                    candidate["valid_to"] = doc.computed_validity.valid_to.isoformat()
            elif hasattr(doc, 'validity_override') and doc.validity_override:
                if doc.validity_override.override_valid_to:
                    candidate["valid_to"] = doc.validity_override.override_valid_to.isoformat()
            
            candidates.append(candidate)
        
        # Ordenar: status reviewed/submitted primero, luego por updated_at desc
        def sort_key(cand):
            status = cand.get("status", "")
            validity_status = cand.get("validity_status", "")
            updated_at = cand.get("updated_at")
            
            # Prioridad 1: status reviewed/submitted
            status_priority = 0
            if "reviewed" in status.lower() or "submitted" in status.lower():
                status_priority = 1
            
            # Prioridad 2: validity_status VALID
            validity_priority = 0
            if validity_status == "VALID":
                validity_priority = 1
            
            # Prioridad 3: updated_at (más reciente primero)
            updated_priority = 0
            if updated_at:
                try:
                    from datetime import datetime
                    updated_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                    updated_priority = updated_dt.timestamp()
                except Exception:
                    pass
            
            return (-status_priority, -validity_priority, -updated_priority)
        
        candidates.sort(key=sort_key)
        
        # Limitar a 50
        candidates = candidates[:50]
        
        # Calcular best_doc_id si se solicita
        best_doc_id = None
        best_reason = None
        if include_best and candidates:
            from backend.cae.doc_candidate_ranker_v1 import get_best_candidate
            
            best_doc_id, best_reason = get_best_candidate(
                candidates=candidates,
                target_type_id=type_id,
                target_scope=scope,
                target_company_key=company_key,
                target_person_key=person_key,
                target_period_key=period_key,
            )
        
        return DocCandidateResponse(
            candidates=candidates,
            fallback_applied=fallback_applied,
            best_doc_id=best_doc_id,
            best_reason=best_reason,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener candidatos: {str(e)}")


class PlanRequest(BaseModel):
    """Request para generar un plan."""
    scope: CAEScopeContextV1


# ========== v1.5: Plan from Selection ==========

class SelectedItemV1(BaseModel):
    """Item seleccionado por el usuario."""
    type_id: str
    scope: Literal["company", "worker"]
    company_key: Optional[str] = None
    person_key: Optional[str] = None
    period_key: Optional[str] = None  # "YYYY-MM"
    suggested_doc_id: Optional[str] = None  # obligatorio para READY


class PlanFromSelectionRequest(BaseModel):
    """Request para generar plan desde selección explícita."""
    scope: CAEScopeContextV1
    selected_items: List[SelectedItemV1]


@router.post("/plan_from_selection", response_model=CAESubmissionPlanV1)
async def create_plan_from_selection(request: PlanFromSelectionRequest) -> CAESubmissionPlanV1:
    """
    Genera un plan de envío CAE desde una selección explícita de items con documentos asignados.
    
    v1.5: NO infiere items desde store/pending. Usa SOLO selected_items.
    
    - Si selected_items está vacío -> HTTP 400
    - Para cada item:
      - Si suggested_doc_id falta -> item.status NEEDS_CONFIRMATION
      - Verificar que el doc existe y su PDF existe; si no -> item.status BLOCKED
      - Si tipo requiere valid_from (validity_start_mode=manual):
        - Si el doc no aporta resolved_dates.valid_from -> item NEEDS_CONFIRMATION
    - Decisión global:
      - READY solo si todos los items están PLANNED y con suggested_doc_id
      - NEEDS_CONFIRMATION si hay alguno NEEDS_CONFIRMATION y ninguno BLOCKED
      - BLOCKED si cualquiera BLOCKED
    """
    from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
    from backend.repository.document_status_calculator_v1 import calculate_document_status
    
    # Validar que selected_items no está vacío
    if not request.selected_items:
        raise HTTPException(status_code=400, detail="selected_items no puede estar vacío")
    
    plan_id = CAESubmissionPlannerV1().generate_plan_id()
    created_at = datetime.now()
    
    store = DocumentRepositoryStoreV1()
    planner = CAESubmissionPlannerV1(store)
    
    items: List[CAESubmissionItemV1] = []
    reasons: List[str] = []
    has_needs_confirmation = False
    has_blocked = False
    
    for selected_item in request.selected_items:
        # Validar scope
        if selected_item.scope == "company":
            if not selected_item.company_key:
                items.append(CAESubmissionItemV1(
                    kind="MISSING_PERIOD",
                    type_id=selected_item.type_id,
                    scope=selected_item.scope,
                    company_key=selected_item.company_key,
                    person_key=None,
                    period_key=selected_item.period_key,
                    suggested_doc_id=selected_item.suggested_doc_id,
                    status="BLOCKED",
                    reason="company_key requerido para scope=company",
                ))
                has_blocked = True
                reasons.append(f"Item {selected_item.type_id}: company_key requerido")
                continue
        elif selected_item.scope == "worker":
            if not selected_item.company_key or not selected_item.person_key:
                items.append(CAESubmissionItemV1(
                    kind="MISSING_PERIOD",
                    type_id=selected_item.type_id,
                    scope=selected_item.scope,
                    company_key=selected_item.company_key,
                    person_key=selected_item.person_key,
                    period_key=selected_item.period_key,
                    suggested_doc_id=selected_item.suggested_doc_id,
                    status="BLOCKED",
                    reason="company_key y person_key requeridos para scope=worker",
                ))
                has_blocked = True
                reasons.append(f"Item {selected_item.type_id}: company_key y person_key requeridos")
                continue
        
        # Verificar suggested_doc_id
        if not selected_item.suggested_doc_id:
            items.append(CAESubmissionItemV1(
                kind="MISSING_PERIOD",
                type_id=selected_item.type_id,
                scope=selected_item.scope,
                company_key=selected_item.company_key,
                person_key=selected_item.person_key,
                period_key=selected_item.period_key,
                suggested_doc_id=None,
                status="NEEDS_CONFIRMATION",
                reason="suggested_doc_id no asignado",
            ))
            has_needs_confirmation = True
            reasons.append(f"Item {selected_item.type_id}: suggested_doc_id no asignado")
            continue
        
        # Verificar que el documento existe
        doc = store.get_document(selected_item.suggested_doc_id)
        if not doc:
            import logging
            logging.warning(f"[create_plan_from_selection] Documento {selected_item.suggested_doc_id} no encontrado")
            items.append(CAESubmissionItemV1(
                kind="MISSING_PERIOD",
                type_id=selected_item.type_id,
                scope=selected_item.scope,
                company_key=selected_item.company_key,
                person_key=selected_item.person_key,
                period_key=selected_item.period_key,
                suggested_doc_id=selected_item.suggested_doc_id,
                status="BLOCKED",
                reason=f"Documento {selected_item.suggested_doc_id} no encontrado en el repositorio",
            ))
            has_blocked = True
            reasons.append(f"Item {selected_item.type_id}: documento {selected_item.suggested_doc_id} no encontrado")
            continue
        
        # Verificar que el PDF existe
        try:
            pdf_path = store._get_doc_pdf_path(selected_item.suggested_doc_id)
            if not pdf_path.exists():
                items.append(CAESubmissionItemV1(
                    kind="MISSING_PERIOD",
                    type_id=selected_item.type_id,
                    scope=selected_item.scope,
                    company_key=selected_item.company_key,
                    person_key=selected_item.person_key,
                    period_key=selected_item.period_key,
                    suggested_doc_id=selected_item.suggested_doc_id,
                    status="BLOCKED",
                    reason=f"PDF no encontrado para documento {selected_item.suggested_doc_id}",
                ))
                has_blocked = True
                reasons.append(f"Item {selected_item.type_id}: PDF no encontrado")
                continue
        except Exception as e:
            items.append(CAESubmissionItemV1(
                kind="MISSING_PERIOD",
                type_id=selected_item.type_id,
                scope=selected_item.scope,
                company_key=selected_item.company_key,
                person_key=selected_item.person_key,
                period_key=selected_item.period_key,
                suggested_doc_id=selected_item.suggested_doc_id,
                status="BLOCKED",
                reason=f"Error al verificar PDF: {str(e)}",
            ))
            has_blocked = True
            reasons.append(f"Item {selected_item.type_id}: error al verificar PDF")
            continue
        
        # Obtener tipo de documento
        doc_type = store.get_type(selected_item.type_id)
        if not doc_type:
            items.append(CAESubmissionItemV1(
                kind="MISSING_PERIOD",
                type_id=selected_item.type_id,
                scope=selected_item.scope,
                company_key=selected_item.company_key,
                person_key=selected_item.person_key,
                period_key=selected_item.period_key,
                suggested_doc_id=selected_item.suggested_doc_id,
                status="BLOCKED",
                reason=f"Tipo de documento {selected_item.type_id} no encontrado",
            ))
            has_blocked = True
            reasons.append(f"Item {selected_item.type_id}: tipo no encontrado")
            continue
        
        # Resolver fechas del documento
        # v1.8.2: Si el documento tiene computed_validity completo, usar esas fechas directamente
        # sin necesidad de resolver desde el period_key
        resolved_dates, date_reasons, date_needs_confirmation = planner._resolve_document_dates(
            doc=doc,
            doc_type=doc_type,
        )
        
        # v1.9.1: Si el documento tiene un period_key diferente al del pendiente,
        # SIEMPRE resolver las fechas usando el period_key del pendiente (incluso si el documento tiene computed_validity completo)
        # porque las fechas del documento son para su period_key, no para el del pendiente
        if selected_item.period_key and doc.period_key and doc.period_key != selected_item.period_key:
            # Intentar resolver fechas usando el period_key del pendiente
            period_dates, period_reasons, period_needs_confirmation = planner._resolve_period_dates(
                doc_type=doc_type,
                period_key=selected_item.period_key,
            )
            if period_dates:
                # Si se resolvieron las fechas del periodo, usar esas fechas (sobrescribir las anteriores)
                resolved_dates = period_dates
                date_reasons = period_reasons
                date_needs_confirmation = period_needs_confirmation
        # v1.8.2: Si el documento tiene computed_validity completo con valid_from y valid_to,
        # y el documento tiene issued_at, y el period_key coincide, no necesitamos confirmación
        elif doc.computed_validity and doc.computed_validity.valid_from and doc.computed_validity.valid_to:
            if doc.issued_at or (doc.extracted and doc.extracted.issue_date):
                # El documento tiene todas las fechas necesarias, no necesitamos confirmación
                date_needs_confirmation = False
                # Asegurar que resolved_dates tiene todas las fechas
                if not resolved_dates or "valid_from" not in resolved_dates or "valid_to" not in resolved_dates:
                    # Reconstruir resolved_dates desde computed_validity
                    resolved_dates = {}
                    if doc.issued_at:
                        resolved_dates["issued_at"] = doc.issued_at.isoformat() if hasattr(doc.issued_at, 'isoformat') else str(doc.issued_at)
                    elif doc.extracted and doc.extracted.issue_date:
                        resolved_dates["issued_at"] = doc.extracted.issue_date.isoformat() if hasattr(doc.extracted.issue_date, 'isoformat') else str(doc.extracted.issue_date)
                    resolved_dates["valid_from"] = doc.computed_validity.valid_from.isoformat() if hasattr(doc.computed_validity.valid_from, 'isoformat') else str(doc.computed_validity.valid_from)
                    resolved_dates["valid_to"] = doc.computed_validity.valid_to.isoformat() if hasattr(doc.computed_validity.valid_to, 'isoformat') else str(doc.computed_validity.valid_to)
        
        # Si el documento tiene el mismo period_key que el pendiente y aún hay NEEDS_CONFIRMATION,
        # intentar resolver desde el period_key
        if date_needs_confirmation and selected_item.period_key and doc.period_key == selected_item.period_key:
            period_dates, period_reasons, period_needs_confirmation = planner._resolve_period_dates(
                doc_type=doc_type,
                period_key=selected_item.period_key,
            )
            if period_dates and not period_needs_confirmation:
                # Usar las fechas resueltas del periodo
                resolved_dates = period_dates
                date_reasons = period_reasons
                date_needs_confirmation = False
        
        # Verificar si el tipo requiere valid_from manual
        item_status = "PLANNED"
        item_reasons = []
        
        if date_needs_confirmation:
            item_status = "NEEDS_CONFIRMATION"
            item_reasons.extend(date_reasons)
            has_needs_confirmation = True
        
        # Verificar si validity_start_mode es manual y falta valid_from
        # v1.8.2: Si el documento tiene computed_validity con valid_from, no necesitamos confirmación
        if hasattr(doc_type, 'validity_policy') and doc_type.validity_policy:
            if hasattr(doc_type.validity_policy, 'start_mode'):
                if doc_type.validity_policy.start_mode and doc_type.validity_policy.start_mode.value == "manual":
                    # Solo marcar NEEDS_CONFIRMATION si realmente falta valid_from
                    # Si el documento tiene computed_validity con valid_from, está bien
                    if not resolved_dates or "valid_from" not in resolved_dates:
                        # Verificar si el documento tiene computed_validity con valid_from
                        if not (doc.computed_validity and doc.computed_validity.valid_from):
                            item_status = "NEEDS_CONFIRMATION"
                            item_reasons.append("Tipo requiere valid_from manual pero no está disponible en el documento")
                            has_needs_confirmation = True
                        else:
                            # El documento tiene computed_validity con valid_from, asegurar que está en resolved_dates
                            if not resolved_dates:
                                resolved_dates = {}
                            if "valid_from" not in resolved_dates:
                                resolved_dates["valid_from"] = doc.computed_validity.valid_from.isoformat() if hasattr(doc.computed_validity.valid_from, 'isoformat') else str(doc.computed_validity.valid_from)
                            # No necesitamos confirmación si tenemos valid_from
                            if item_status == "NEEDS_CONFIRMATION" and "valid_from" in resolved_dates:
                                item_status = "PLANNED"
                                has_needs_confirmation = False
        
        items.append(CAESubmissionItemV1(
            kind="MISSING_PERIOD",
            type_id=selected_item.type_id,
            scope=selected_item.scope,
            company_key=selected_item.company_key,
            person_key=selected_item.person_key,
            period_key=selected_item.period_key,
            suggested_doc_id=selected_item.suggested_doc_id,
            resolved_dates=resolved_dates,
            status=item_status,
            reason="; ".join(item_reasons) if item_reasons else "Item listo para envío",
        ))
        
        if item_reasons:
            reasons.extend([f"Item {selected_item.type_id}: {r}" for r in item_reasons])
    
    # Determinar decisión global
    if has_blocked:
        decision = "BLOCKED"
    elif has_needs_confirmation:
        decision = "NEEDS_CONFIRMATION"
    else:
        decision = "READY"
    
    # Generar summary
    summary = {
        "total_items": len(request.selected_items),
        "items_planned": len([i for i in items if i.status == "PLANNED"]),
        "items_needs_confirmation": len([i for i in items if i.status == "NEEDS_CONFIRMATION"]),
        "items_blocked": len([i for i in items if i.status == "BLOCKED"]),
    }
    
    plan = CAESubmissionPlanV1(
        plan_id=plan_id,
        created_at=created_at,
        scope=request.scope,
        decision=decision,
        reasons=reasons,
        items=items,
        summary=summary,
        executor_hint="egestiona_upload_v1" if request.scope.platform_key == "egestiona" else None,
    )
    
    # Guardar evidencia
    try:
        evidence_dir = Path(DATA_DIR) / "docs" / "evidence" / "cae_plans"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_file = evidence_dir / f"{plan_id}.json"
        evidence_file.write_text(
            json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        # No crítico si falla guardar evidencia
        pass
    
    return plan


@router.post("/plan", response_model=CAESubmissionPlanV1)
async def create_plan(request: PlanRequest) -> CAESubmissionPlanV1:
    """
    Genera un plan de envío CAE basado en el scope.
    
    NO ejecuta subidas reales, solo planifica.
    
    - Si scope inválido -> HTTP 400
    - Si no hay items en scope -> HTTP 200 con decision=BLOCKED
    """
    from datetime import datetime
    import uuid
    
    # Validar scope básico
    if not request.scope.platform_key or not request.scope.platform_key.strip():
        raise HTTPException(
            status_code=400,
            detail="platform_key es requerido y no puede estar vacío"
        )
    
    # Validar mode
    valid_modes = ["READ_ONLY", "PREPARE_WRITE", "WRITE"]
    if request.scope.mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"mode debe ser uno de: {', '.join(valid_modes)}"
        )
    
    try:
        # Inicializar planificador con manejo de errores
        try:
            planner = CAESubmissionPlannerV1()
        except Exception as e:
            # Si falla la inicialización, retornar plan BLOCKED
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error al inicializar planificador: {e}", exc_info=True)
            
            now = datetime.now()
            timestamp = now.strftime("%Y%m%d-%H%M%S")
            short_id = str(uuid.uuid4())[:8]
            plan_id = f"CAEPLAN-{timestamp}-{short_id}"
            
            return CAESubmissionPlanV1(
                plan_id=plan_id,
                created_at=now,
                scope=request.scope,
                decision="BLOCKED",
                reasons=[f"Error al inicializar planificador: {str(e)}"],
                items=[],
                summary={"pending_items": 0, "docs_candidates": 0, "total_items": 0, "types_processed": 0},
                executor_hint=None,
            )
        
        # Generar plan con manejo de errores
        try:
            plan = planner.plan_submission(request.scope)
        except Exception as e:
            # Si falla la generación del plan, retornar plan BLOCKED
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            error_trace = traceback.format_exc()
            logger.error(f"Error al generar plan: {e}\n{error_trace}")
            
            now = datetime.now()
            timestamp = now.strftime("%Y%m%d-%H%M%S")
            short_id = str(uuid.uuid4())[:8]
            plan_id = f"CAEPLAN-{timestamp}-{short_id}"
            
            return CAESubmissionPlanV1(
                plan_id=plan_id,
                created_at=now,
                scope=request.scope,
                decision="BLOCKED",
                reasons=[f"Error al generar plan: {str(e)}"],
                items=[],
                summary={"pending_items": 0, "docs_candidates": 0, "total_items": 0, "types_processed": 0},
                executor_hint=None,
            )
        
        # Guardar evidencia (puede fallar, pero no debe romper la respuesta)
        try:
            _save_plan_evidence(plan)
        except Exception as e:
            # Log el error pero no fallar la respuesta
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Error al guardar evidencia del plan {plan.plan_id}: {e}")
        
        return plan
    
    except HTTPException:
        # Re-lanzar HTTPExceptions (400, 404, etc.)
        raise
    
    except Exception as e:
        # Cualquier otro error: retornar plan BLOCKED en lugar de 500
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        error_trace = traceback.format_exc()
        logger.error(f"Error inesperado al generar plan: {e}\n{error_trace}")
        
        # Generar plan_id de emergencia
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d-%H%M%S")
        short_id = str(uuid.uuid4())[:8]
        plan_id = f"CAEPLAN-{timestamp}-{short_id}"
        
        return CAESubmissionPlanV1(
            plan_id=plan_id,
            created_at=now,
            scope=request.scope,
            decision="BLOCKED",
            reasons=[f"Error al procesar el scope: {str(e)}"],
            items=[],
            summary={"pending_items": 0, "docs_candidates": 0, "total_items": 0, "types_processed": 0},
            executor_hint=None,
        )


@router.get("/plan/{plan_id}", response_model=CAESubmissionPlanV1)
async def get_plan(plan_id: str) -> CAESubmissionPlanV1:
    """
    Obtiene un plan guardado por su ID (solo lectura de evidencia).
    """
    evidence_path = _get_evidence_path(plan_id)
    
    if not evidence_path.exists():
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    
    try:
        with open(evidence_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Reconstruir el plan desde JSON
        plan = CAESubmissionPlanV1.model_validate(data)
        return plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al leer plan: {str(e)}")


def _get_evidence_dir() -> Path:
    """Obtiene el directorio de evidencia."""
    evidence_dir = Path(DATA_DIR) / "docs" / "evidence" / "cae_plans"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    return evidence_dir


def _get_evidence_path(plan_id: str) -> Path:
    """Obtiene el path del archivo de evidencia para un plan."""
    evidence_dir = _get_evidence_dir()
    return evidence_dir / f"{plan_id}.json"


def _get_plan_evidence(plan_id: str) -> Optional[CAESubmissionPlanV1]:
    """Lee un plan desde el archivo de evidencia."""
    evidence_path = _get_evidence_path(plan_id)
    
    if not evidence_path.exists():
        return None
    
    try:
        with open(evidence_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Reconstruir el plan desde JSON
        plan = CAESubmissionPlanV1.model_validate(data)
        return plan
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error al leer plan {plan_id}: {e}")
        return None


def _save_plan_evidence(plan: CAESubmissionPlanV1) -> None:
    """Guarda el plan como evidencia en JSON."""
    evidence_path = _get_evidence_path(plan.plan_id)
    
    # Convertir a dict serializable
    plan_dict = plan.model_dump(mode="json")
    
    # Guardar JSON
    with open(evidence_path, 'w', encoding='utf-8') as f:
        json.dump(plan_dict, f, indent=2, ensure_ascii=False)


# Sistema de challenges (guardado en archivo temporal)
def _get_challenges_dir() -> Path:
    """Obtiene el directorio de challenges."""
    challenges_dir = Path(DATA_DIR) / "refs" / "cae_challenges"
    challenges_dir.mkdir(parents=True, exist_ok=True)
    return challenges_dir


def _save_challenge(plan_id: str, challenge_token: str, expires_at: datetime) -> None:
    """Guarda un challenge en archivo temporal."""
    challenges_dir = _get_challenges_dir()
    challenge_file = challenges_dir / f"{challenge_token}.json"
    
    challenge_data = {
        "plan_id": plan_id,
        "challenge_token": challenge_token,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.now().isoformat(),
    }
    
    with open(challenge_file, 'w', encoding='utf-8') as f:
        json.dump(challenge_data, f, indent=2, ensure_ascii=False)


def _get_challenge(challenge_token: str) -> Optional[dict]:
    """Obtiene un challenge por su token."""
    challenges_dir = _get_challenges_dir()
    challenge_file = challenges_dir / f"{challenge_token}.json"
    
    if not challenge_file.exists():
        return None
    
    try:
        with open(challenge_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _validate_challenge(challenge_token: str, challenge_response: str, plan_id: str) -> tuple[bool, Optional[str]]:
    """
    Valida un challenge.
    
    Returns:
        (is_valid, error_message)
    """
    challenge_data = _get_challenge(challenge_token)
    if not challenge_data:
        return False, "Challenge token inválido o expirado"
    
    # Verificar expiración (TTL de 5 minutos)
    expires_at = datetime.fromisoformat(challenge_data["expires_at"])
    if datetime.now() > expires_at:
        return False, "Challenge token expirado"
    
    # Verificar que el plan_id coincide
    if challenge_data["plan_id"] != plan_id:
        return False, f"Challenge token no corresponde al plan {plan_id}"
    
    # Verificar respuesta exacta
    expected_response = f"EJECUTAR {plan_id}"
    if challenge_response != expected_response:
        return False, f"Challenge response incorrecto. Esperado: '{expected_response}'"
    
    return True, None


@router.post("/execute/{plan_id}/challenge", response_model=ChallengeResponseV1)
async def create_challenge(plan_id: str, request: ChallengeRequestV1) -> ChallengeResponseV1:
    """
    Crea un challenge para confirmar la ejecución de un plan.
    """
    # Cargar el plan
    planner = CAESubmissionPlannerV1()
    plan = _get_plan_evidence(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    
    # Validar que el plan es ejecutable
    if plan.decision != "READY":
        raise HTTPException(
            status_code=409,
            detail=f"Plan decision debe ser READY, es {plan.decision}"
        )
    
    if plan.scope.platform_key != "egestiona":
        raise HTTPException(
            status_code=400,
            detail=f"Platform debe ser 'egestiona', es '{plan.scope.platform_key}'"
        )
    
    if plan.scope.mode not in ["PREPARE_WRITE", "WRITE"]:
        raise HTTPException(
            status_code=409,
            detail=f"Mode debe ser PREPARE_WRITE o WRITE, es '{plan.scope.mode}'"
        )
    
    # Generar challenge token
    import secrets
    challenge_token = secrets.token_urlsafe(32)
    
    # Guardar challenge (TTL de 5 minutos)
    expires_at = datetime.now() + timedelta(minutes=5)
    _save_challenge(plan_id, challenge_token, expires_at)
    
    # Generar prompt
    prompt = f"Escribe EXACTAMENTE: EJECUTAR {plan_id}"
    
    return ChallengeResponseV1(
        plan_id=plan_id,
        challenge_token=challenge_token,
        prompt=prompt,
    )


@router.post("/execute/{plan_id}", response_model=RunResultV1)
async def execute_plan(plan_id: str, request: ExecuteRequestV1) -> RunResultV1:
    """
    Ejecuta un plan después de validar el challenge.
    """
    # Cargar el plan
    planner = CAESubmissionPlannerV1()
    plan = planner.get_plan_evidence(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found")
    
    # Validar challenge
    is_valid, error_msg = _validate_challenge(
        challenge_token=request.challenge_token,
        challenge_response=request.challenge_response,
        plan_id=plan_id,
    )
    if not is_valid:
        raise HTTPException(status_code=403, detail=error_msg)
    
    # Validar plan (mismas validaciones que en challenge)
    if plan.decision != "READY":
        raise HTTPException(
            status_code=409,
            detail=f"Plan decision debe ser READY, es {plan.decision}"
        )
    
    if plan.scope.platform_key != "egestiona":
        raise HTTPException(
            status_code=400,
            detail=f"Platform debe ser 'egestiona', es '{plan.scope.platform_key}'"
        )
    
    if plan.scope.mode not in ["PREPARE_WRITE", "WRITE"]:
        raise HTTPException(
            status_code=409,
            detail=f"Mode debe ser PREPARE_WRITE o WRITE, es '{plan.scope.mode}'"
        )
    
    # Ejecutar el plan
    runner = CAEExecutionRunnerV1()
    result = runner.execute_plan_egestiona(plan=plan, dry_run=request.dry_run)
    
    return result

