"""
Adaptador CAE batch sobre el motor batch genérico.

v3.1.0: Transforma peticiones CAE específicas en BatchAgentRequest genérico
y post-procesa resultados batch en informes CAE estructurados.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from backend.shared.models import (
    CAEBatchRequest,
    CAEWorker,
    BatchAgentRequest,
    BatchAgentGoal,
    BatchAgentResponse,
    BatchAgentGoalResult,
    CAEBatchResponse,
    CAEWorkerDocStatus,
    WorkerMemory,
    CompanyMemory,
    PlatformMemory,
)
from backend.memory import MemoryStore
from backend.config import MEMORY_BASE_DIR

logger = logging.getLogger(__name__)

# Mapeo de tipos de documento a nombres legibles
DOC_TYPE_NAMES = {
    "reconocimiento_medico": "reconocimiento médico",
    "formacion_prl": "formación PRL",
    "formacion": "formación",
    "prl": "PRL",
    "contrato": "contrato",
    "dni": "DNI",
    "otro": "otro documento",
}


def _build_cae_goal_text(cae_request: CAEBatchRequest, worker: CAEWorker) -> str:
    """
    Construye el texto del objetivo para un trabajador CAE.
    
    v3.1.0: Genera un objetivo textual en español que el agente puede ejecutar.
    
    Args:
        cae_request: Petición batch CAE completa
        worker: Trabajador específico
        
    Returns:
        Texto del objetivo en español
    """
    # Construir lista legible de documentos requeridos
    required_docs = worker.required_docs or []
    if required_docs:
        doc_names = [
            DOC_TYPE_NAMES.get(doc_type, doc_type.replace("_", " "))
            for doc_type in required_docs
        ]
        docs_text = ", ".join(doc_names)
    else:
        docs_text = "documentación de prevención de riesgos laborales"
    
    # Construir objetivo completo
    goal_parts = [
        f"Accede a la plataforma CAE de {cae_request.company_name}",
        f"localiza al trabajador {worker.full_name} (ID {worker.id})",
        f"y revisa la documentación de prevención de riesgos laborales.",
    ]
    
    if required_docs:
        goal_parts.append(
            f"Comprueba si están correctamente subidos y vigentes los siguientes documentos: {docs_text}."
        )
    
    goal_parts.extend([
        "Si detectas que falta alguno, súbelo desde el repositorio local si está disponible",
        "y verifica visualmente que la plataforma confirma la subida.",
        "Al final, indícame claramente qué documentos están correctos, cuáles faltan",
        "y si ha habido errores de subida.",
    ])
    
    goal_text = " ".join(goal_parts)
    
    logger.debug(
        f"[cae-adapter] Built goal text for worker {worker.id}: {goal_text[:100]}..."
    )
    
    return goal_text


def build_batch_request_from_cae(cae_request: CAEBatchRequest) -> BatchAgentRequest:
    """
    Transforma un CAEBatchRequest en un BatchAgentRequest genérico.
    
    v3.1.0: Convierte la petición CAE específica en una petición batch genérica
    que puede ser procesada por run_batch_agent.
    v3.9.0: Carga memoria persistente para enriquecer objetivos (opcional).
    
    Args:
        cae_request: Petición batch CAE
        
    Returns:
        BatchAgentRequest equivalente
    """
    goals: List[BatchAgentGoal] = []
    
    # v3.9.0: Cargar memoria persistente (opcional, no crítico si falla)
    memory_store: Optional[MemoryStore] = None
    try:
        memory_store = MemoryStore(MEMORY_BASE_DIR)
        logger.debug(f"[cae-adapter] Memory store initialized at {MEMORY_BASE_DIR}")
    except Exception as e:
        logger.warning(f"[cae-adapter] Failed to initialize memory store: {e}")
    
    # Asegurar que context_strategies incluye "cae" si no está especificado
    context_strategies = cae_request.context_strategies or ["cae"]
    if "cae" not in context_strategies:
        context_strategies = ["cae"] + context_strategies
    
    for worker in cae_request.workers:
        # Construir objetivo textual en español para el agente
        goal_text = _build_cae_goal_text(cae_request, worker)
        
        # v3.9.0: Enriquecer objetivo con memoria si está disponible (TODO: implementar enriquecimiento)
        # Por ahora solo cargamos la memoria, el enriquecimiento se puede añadir más adelante
        if memory_store:
            try:
                worker_memory = memory_store.load_worker(worker.id)
                if worker_memory:
                    logger.debug(f"[cae-adapter] Loaded memory for worker {worker.id}")
                    # TODO: Enriquecer goal_text con información de memoria
            except Exception as e:
                logger.debug(f"[cae-adapter] Failed to load memory for worker {worker.id}: {e}")
        
        goals.append(
            BatchAgentGoal(
                id=worker.id,
                goal=goal_text,
                execution_profile_name=cae_request.execution_profile_name,
                context_strategies=context_strategies,
            )
        )
    
    logger.info(
        f"[cae-adapter] Built batch request: {len(goals)} goals for "
        f"{cae_request.company_name} on platform {cae_request.platform}"
    )
    
    return BatchAgentRequest(
        goals=goals,
        default_execution_profile_name=cae_request.execution_profile_name,
        default_context_strategies=context_strategies,
        max_consecutive_failures=cae_request.max_consecutive_failures,
        default_execution_mode=cae_request.execution_mode,  # v4.3.0
    )


def build_cae_response_from_batch(
    cae_request: CAEBatchRequest,
    batch_response: BatchAgentResponse,
) -> CAEBatchResponse:
    """
    Post-procesa BatchAgentResponse en CAEBatchResponse estructurado.
    
    v3.1.0: Extrae información específica CAE de los resultados batch genéricos,
    incluyendo documentos subidos, errores y estado por trabajador.
    
    Args:
        cae_request: Petición CAE original
        batch_response: Respuesta batch genérica
        
    Returns:
        CAEBatchResponse con información estructurada por trabajador
    """
    # Crear dict de workers por id para búsqueda rápida
    worker_by_id: Dict[str, CAEWorker] = {
        worker.id: worker for worker in cae_request.workers
    }
    
    worker_statuses: List[CAEWorkerDocStatus] = []
    
    for result in batch_response.goals:
        worker = worker_by_id.get(result.id)
        
        if not worker:
            logger.warning(
                f"[cae-adapter] Result for unknown worker id: {result.id}"
            )
            continue
        
        # Extraer información de documentos subidos y errores
        uploaded_docs: List[str] = []
        upload_errors: List[str] = []
        missing_docs: List[str] = []
        
        # v3.1.0: Extraer uploaded_docs de file_upload_instructions
        if result.file_upload_instructions:
            for instruction in result.file_upload_instructions:
                # instruction puede ser dict o FileUploadInstructionDTO
                if isinstance(instruction, dict):
                    # Buscar doc_type en diferentes campos posibles
                    doc_type = instruction.get("doc_type")
                    file_name = instruction.get("file_name") or instruction.get("path", "")
                    
                    if doc_type:
                        uploaded_docs.append(doc_type)
                    elif file_name:
                        # Intentar inferir tipo desde nombre de archivo
                        file_lower = file_name.lower()
                        for doc_type_key, doc_name in DOC_TYPE_NAMES.items():
                            if doc_type_key.replace("_", "") in file_lower:
                                uploaded_docs.append(doc_type_key)
                                break
                else:
                    # Si es un objeto (FileUploadInstructionDTO), acceder a atributos
                    doc_type = getattr(instruction, "doc_type", None)
                    if doc_type:
                        uploaded_docs.append(doc_type)
                    else:
                        # Intentar desde path o description
                        path = getattr(instruction, "path", "")
                        if path:
                            file_lower = path.lower()
                            for doc_type_key, doc_name in DOC_TYPE_NAMES.items():
                                if doc_type_key.replace("_", "") in file_lower:
                                    uploaded_docs.append(doc_type_key)
                                    break
        
        # v3.1.0: Extraer upload_errors de métricas y secciones
        if result.metrics_summary:
            upload_info = result.metrics_summary.get("summary", {}).get("upload_info", {})
            upload_verification_info = result.metrics_summary.get("summary", {}).get(
                "upload_verification_info", {}
            )
            
            # Errores de upload
            if upload_info.get("upload_attempts", 0) > upload_info.get("upload_successes", 0):
                upload_errors.append("Algunos intentos de subida fallaron")
            
            # Errores de verificación
            if upload_verification_info.get("upload_error_detected_count", 0) > 0:
                upload_errors.append("Se detectaron errores en la verificación visual de subidas")
        
        # v3.1.0: Extraer missing_docs de secciones (heurística simple)
        if result.sections:
            for section in result.sections:
                answer = section.get("answer", "").lower()
                # Buscar indicadores de documentos faltantes
                if any(keyword in answer for keyword in ["falta", "no se encontró", "no está", "ausente"]):
                    # Intentar extraer tipo de documento mencionado
                    for doc_type_key, doc_name in DOC_TYPE_NAMES.items():
                        if doc_name.lower() in answer:
                            if doc_type_key not in missing_docs:
                                missing_docs.append(doc_type_key)
        
        # v3.3.0: Extraer información CAE desde texto combinado (visible + OCR)
        combined_text = ""
        if result.sections:
            for section in result.sections:
                answer = section.get("answer", "")
                if answer:
                    combined_text += answer + "\n"
        
        # También buscar en structured_sources si hay texto adicional
        if result.structured_sources:
            for source in result.structured_sources:
                title = source.get("title", "")
                if title:
                    combined_text += title + "\n"
        
        # v3.3.0: Analizar estado CAE desde texto combinado
        cae_status_info = None
        if combined_text:
            from backend.agents.cae_ocr_analyzer import extract_cae_status_from_text
            cae_status_info = extract_cae_status_from_text(combined_text)
        
        # v3.1.0: Construir notas adicionales
        notes_parts = []
        if result.error_message:
            notes_parts.append(f"Error: {result.error_message}")
        if upload_errors:
            notes_parts.append(f"Errores de subida: {', '.join(upload_errors)}")
        
        # v4.4.0: Añadir información de análisis del documento si está disponible
        document_analysis = None
        if result.sections:
            for section in result.sections:
                if section.get("document_analysis"):
                    document_analysis = section["document_analysis"]
                    break
        
        # También buscar en file_upload_instructions
        if not document_analysis and result.file_upload_instructions:
            for instruction in result.file_upload_instructions:
                if isinstance(instruction, dict) and instruction.get("document_analysis"):
                    document_analysis = instruction["document_analysis"]
                    break
        
        if document_analysis:
            analysis_parts = []
            if document_analysis.get("issue_date"):
                analysis_parts.append(f"issue_date={document_analysis['issue_date']}")
            if document_analysis.get("expiry_date"):
                analysis_parts.append(f"expiry_date={document_analysis['expiry_date']}")
            if document_analysis.get("worker_name"):
                analysis_parts.append(f"worker_name={document_analysis['worker_name']}")
            if document_analysis.get("confidence") is not None:
                analysis_parts.append(f"confidence={document_analysis['confidence']:.2f}")
            if document_analysis.get("warnings"):
                warnings_str = ", ".join(document_analysis["warnings"][:3])  # Limitar a 3 warnings
                analysis_parts.append(f"warnings=[{warnings_str}]")
            
            if analysis_parts:
                notes_parts.append(f"Documento analizado: {', '.join(analysis_parts)}")
        
        # v4.8.0: Añadir información de análisis profundo si está disponible
        deep_analysis = None
        if result.sections:
            for section in result.sections:
                if section.get("deep_document_analysis"):
                    deep_analysis = section["deep_document_analysis"]
                    break
        
        # También buscar en file_upload_instructions
        if not deep_analysis and result.file_upload_instructions:
            for instruction in result.file_upload_instructions:
                if isinstance(instruction, dict) and instruction.get("deep_document_analysis"):
                    deep_analysis = instruction["deep_document_analysis"]
                    break
        
        if deep_analysis:
            deep_parts = []
            
            # Tipo de documento y nivel
            if deep_analysis.get("doc_type"):
                doc_type_name = DOC_TYPE_NAMES.get(deep_analysis["doc_type"], deep_analysis["doc_type"])
                deep_parts.append(f"Documento {doc_type_name}")
            
            if deep_analysis.get("training_level"):
                deep_parts.append(f"Nivel {deep_analysis['training_level']}")
            
            if deep_analysis.get("training_hours"):
                deep_parts.append(f"{deep_analysis['training_hours']}")
            
            if deep_analysis.get("document_code"):
                deep_parts.append(f"Código {deep_analysis['document_code']}")
            
            if deep_parts:
                notes_parts.append(" — ".join(deep_parts))
            
            # Fechas
            date_parts = []
            if deep_analysis.get("issue_date"):
                date_parts.append(f"Emitido: {deep_analysis['issue_date']}")
            if deep_analysis.get("expiry_date"):
                date_parts.append(f"Caduca: {deep_analysis['expiry_date']}")
            
            if date_parts:
                notes_parts.append(" — ".join(date_parts))
            
            # Centro emisor
            if deep_analysis.get("issuer_name"):
                notes_parts.append(f"Centro: {deep_analysis['issuer_name']}")
            
            # Confianza
            if deep_analysis.get("confidence"):
                notes_parts.append(f"Confianza del análisis: {deep_analysis['confidence']:.2f}")
        
        # v4.5.0/v4.7.0: Añadir información de rellenado automático de formulario
        form_fill_detected = False
        form_mapped_fields = None
        if result.sections:
            for section in result.sections:
                if section.get("form_fill"):
                    form_fill = section["form_fill"]
                    status = form_fill.get("status", "unknown")
                    fields = form_fill.get("fields", [])
                    if fields:
                        field_names = [f.get("semantic_field", "") for f in fields]
                        notes_parts.append(
                            f"Se ha intentado rellenar automáticamente los campos del formulario "
                            f"({', '.join(field_names)}) con los datos del documento. "
                            f"Estado: {status}"
                        )
                        
                        # v4.7.0: Añadir información sobre método de detección
                        if section.get("form_mapped_fields"):
                            form_mapped_fields = section["form_mapped_fields"]
                            sources = [mf.get("source", "unknown") for mf in form_mapped_fields if mf]
                            if "hybrid" in sources:
                                notes_parts.append("form_detection: hybrid (DOM + OCR)")
                            elif "ocr" in sources:
                                notes_parts.append("form_detection: ocr")
                            elif "dom" in sources:
                                notes_parts.append("form_detection: dom")
                            
                            # Confianza promedio
                            confidences = [mf.get("confidence", 0.0) for mf in form_mapped_fields if mf and mf.get("confidence")]
                            if confidences:
                                avg_confidence = sum(confidences) / len(confidences)
                                notes_parts.append(f"Confianza promedio del mapeo: {avg_confidence:.2f}")
                        
                        form_fill_detected = True
                        break
        
        # También buscar en file_upload_instructions
        if not form_fill_detected and result.file_upload_instructions:
            for instruction in result.file_upload_instructions:
                if isinstance(instruction, dict) and instruction.get("form_fill_instruction"):
                    form_fill_inst = instruction["form_fill_instruction"]
                    plan = form_fill_inst.get("plan", {})
                    fields = plan.get("fields", [])
                    if fields:
                        field_names = [f.get("semantic_field", "") for f in fields]
                        notes_parts.append(
                            f"Se ha intentado rellenar automáticamente los campos del formulario "
                            f"({', '.join(field_names)}) con los datos del documento."
                        )
                        break
        
        # v3.3.0: Añadir información de estado CAE a las notas
        if cae_status_info and cae_status_info.get("status") != "desconocido":
            status = cae_status_info["status"]
            status_text = {
                "vigente": "Estado: Vigente",
                "caducado": "Estado: Caducado",
                "pendiente": "Estado: Pendiente",
                "no_apto": "Estado: No apto",
            }.get(status, f"Estado: {status}")
            notes_parts.append(status_text)
            
            if cae_status_info.get("expiry_dates"):
                dates_str = ", ".join(cae_status_info["expiry_dates"])
                notes_parts.append(f"Caducidades detectadas: {dates_str}")
        
        # v3.5.0: Usar VisualFlowState si está disponible para enriquecer notas y success
        last_visual_flow_state = None
        if hasattr(result, 'steps') and result.steps:
            # Buscar el último visual_flow_state en los steps
            for step in reversed(result.steps):
                if step.info and step.info.get("visual_flow_state"):
                    from backend.shared.models import VisualFlowState
                    try:
                        last_visual_flow_state = VisualFlowState(**step.info["visual_flow_state"])
                        break
                    except Exception as e:
                        logger.debug(f"[cae-batch] Failed to parse visual_flow_state: {e}")
        
        if last_visual_flow_state:
            if last_visual_flow_state.stage == "error":
                notes_parts.append("El flujo visual indica que hay mensajes de error en la plataforma.")
            elif last_visual_flow_state.stage == "confirmed":
                # Reforzar success si el flujo visual indica confirmación
                if not result.success:
                    logger.debug("[cae-batch] Visual flow state indicates confirmed, but result.success is False")
        
        # v3.6.0: Usar VisualContractResult si está disponible para enriquecer notas
        last_visual_contract = None
        if hasattr(result, 'steps') and result.steps:
            # Buscar el último visual_expectation en los steps
            for step in reversed(result.steps):
                if step.info and step.info.get("visual_expectation"):
                    from backend.shared.models import VisualContractResult
                    try:
                        last_visual_contract = VisualContractResult(**step.info["visual_expectation"])
                        break
                    except Exception as e:
                        logger.debug(f"[cae-batch] Failed to parse visual_expectation: {e}")
        
        if last_visual_contract:
            if last_visual_contract.outcome == "violation":
                notes_parts.append("El contrato visual indica que el flujo de guardado/confirmación no ha llegado al estado esperado.")
            elif last_visual_contract.outcome == "mismatch":
                notes_parts.append("El estado visual observado no coincide completamente con el esperado.")
            elif last_visual_contract.outcome == "match":
                # Reforzar confianza si hay match
                logger.debug("[cae-batch] Visual contract match detected, reinforcing confidence")
        
        # v3.7.0: Usar AgentIntent si está disponible para enriquecer notas
        critical_intents = []
        all_intents = []
        if hasattr(result, 'steps') and result.steps:
            # Buscar intenciones relevantes en los steps
            for step in reversed(result.steps):
                if step.info and step.info.get("agent_intent"):
                    from backend.shared.models import AgentIntent
                    try:
                        agent_intent = AgentIntent(**step.info["agent_intent"])
                        # Solo considerar intenciones relevantes para CAE
                        if agent_intent.intent_type in ["upload_file", "save_changes", "confirm_submission", "select_file"]:
                            if agent_intent.intent_type not in [i.intent_type for i in all_intents]:
                                all_intents.append(agent_intent)
                                if agent_intent.criticality == "critical":
                                    critical_intents.append(agent_intent)
                    except Exception as e:
                        logger.debug(f"[cae-batch] Failed to parse agent_intent: {e}")
        
        if critical_intents:
            intent_descriptions = {
                "upload_file": "subir archivo",
                "save_changes": "guardar cambios",
                "confirm_submission": "confirmar envío",
                "select_file": "seleccionar archivo",
            }
            intent_names = [intent_descriptions.get(intent.intent_type, intent.intent_type) for intent in critical_intents]
            notes_parts.append(f"Intenciones críticas ejecutadas: {', '.join(intent_names)}.")
        
        if all_intents and not critical_intents:
            # Si hay intenciones pero ninguna es crítica, mencionarlas brevemente
            intent_types = list(set([intent.intent_type for intent in all_intents]))
            if intent_types:
                notes_parts.append(f"Intenciones detectadas: {', '.join(intent_types)}.")
        
        # v4.1.0: Usar OutcomeJudgeReport si está disponible para enriquecer notas y success
        # v4.2.0: También extraer información para actualizar memoria y detectar regresiones
        outcome_judge = result.outcome_judge
        global_score = None
        top_issues = []
        regression_flag = None
        
        if outcome_judge:
            if outcome_judge.global_review:
                global_review = outcome_judge.global_review
                # Añadir información de puntuación global
                if global_review.global_score is not None:
                    global_score = global_review.global_score
                    score_percent = int(global_score * 100)
                    notes_parts.append(f"OutcomeJudge: Puntuación global {score_percent}%")
                
                # Añadir problemas principales si hay
                if global_review.main_issues:
                    top_issues = global_review.main_issues[:5]  # Top 5 issues
                    issues_str = "; ".join(top_issues[:3])  # Limitar a 3 para notas
                    notes_parts.append(f"Issues detectados: {issues_str}")
                
                # Actualizar success si overall_success está definido y es False
                if global_review.overall_success is False:
                    # No cambiar result.success directamente, pero añadir nota
                    notes_parts.append("OutcomeJudge indica que la ejecución fue problemática")
        
        notes = "; ".join(notes_parts) if notes_parts else None
        
        # v3.2.0: Extraer visual_actions de las secciones
        visual_actions = []
        if result.sections:
            from backend.shared.models import VisualActionResult
            for section in result.sections:
                # Buscar visual_confirmation en la sección
                if section.get("upload_verification"):
                    upload_verification = section["upload_verification"]
                    if isinstance(upload_verification, dict):
                        visual_actions.append(VisualActionResult(
                            action_type="upload_file",
                            expected_effect="Verificar subida de archivo",
                            confirmed=upload_verification.get("status") == "confirmed",
                            confidence=upload_verification.get("confidence", 0.0),
                            evidence=upload_verification.get("evidence"),
                        ))
                # También buscar en upload_summary si existe
                if section.get("upload_summary") and section["upload_summary"].get("verification_status"):
                    verification_status = section["upload_summary"]["verification_status"]
                    visual_actions.append(VisualActionResult(
                        action_type="upload_file",
                        expected_effect="Verificar subida de archivo",
                        confirmed=verification_status == "confirmed",
                        confidence=section["upload_summary"].get("verification_confidence", 0.0),
                        evidence=section["upload_summary"].get("verification_evidence"),
                    ))
        
        # Si no hay visual_actions en secciones, intentar extraer de metrics_summary
        if not visual_actions and result.metrics_summary:
            visual_confirmation_info = result.metrics_summary.get("summary", {}).get("visual_confirmation_info", {})
            if visual_confirmation_info.get("visual_confirmations_attempted", 0) > 0:
                # Crear una acción visual agregada
                from backend.shared.models import VisualActionResult
                visual_actions.append(VisualActionResult(
                    action_type="mixed",
                    expected_effect="Confirmación visual de acciones críticas",
                    confirmed=visual_confirmation_info.get("visual_confirmation_success_ratio", 0.0) > 0.5,
                    confidence=visual_confirmation_info.get("visual_confirmation_success_ratio", 0.0),
                    evidence=f"Intentos: {visual_confirmation_info.get('visual_confirmations_attempted', 0)}, Fallos: {visual_confirmation_info.get('visual_confirmations_failed', 0)}",
                ))
        
        worker_status = CAEWorkerDocStatus(
            worker_id=worker.id,
            full_name=worker.full_name,
            success=result.success,
            missing_docs=missing_docs,
            uploaded_docs=uploaded_docs,
            upload_errors=upload_errors,
            notes=notes,
            raw_answer=result.final_answer,
            metrics_summary=result.metrics_summary,
            visual_actions=visual_actions if visual_actions else None,  # v3.2.0
            cae_status=cae_status_info.get("status") if cae_status_info and cae_status_info.get("status") != "desconocido" else None,  # v3.3.0
            cae_status_evidence=cae_status_info.get("evidence_snippets") if cae_status_info else None,  # v3.3.0
            cae_expiry_dates=cae_status_info.get("expiry_dates") if cae_status_info else None,  # v3.3.0
        )
        
        worker_statuses.append(worker_status)
    
    # v4.2.0: Actualizar memoria con resultados de OutcomeJudge y detectar regresiones
    # v4.3.0: No actualizar memoria en modo dry_run
    memory_store: Optional[MemoryStore] = None
    regressions_detected = 0
    regression_threshold = 0.20  # Umbral de regresión en escala 0-1 (delta <= -0.20, equivalente a -20 puntos porcentuales)
    
    # v4.3.0: Determinar execution_mode efectivo
    effective_execution_mode = cae_request.execution_mode or "live"
    if effective_execution_mode not in ("live", "dry_run"):
        effective_execution_mode = "live"
    
    try:
        # v4.3.0: Solo inicializar memoria si no estamos en dry_run
        if effective_execution_mode != "dry_run":
            memory_store = MemoryStore(MEMORY_BASE_DIR)
        now = datetime.now()
        
        for i, result in enumerate(batch_response.goals):
            worker = worker_by_id.get(result.id)
            if not worker:
                continue
            
            worker_status = worker_statuses[i] if i < len(worker_statuses) else None
            if not worker_status:
                continue
            
            outcome_judge = result.outcome_judge
            if not outcome_judge or not outcome_judge.global_review:
                continue
            
            global_review = outcome_judge.global_review
            global_score = global_review.global_score
            if global_score is None:
                continue
            
            # Extraer issues principales
            top_issues = []
            if global_review.main_issues:
                top_issues = global_review.main_issues[:5]
            # También añadir issues de sub-goals si hay
            if outcome_judge.sub_goals:
                for sg in outcome_judge.sub_goals:
                    if sg.issues:
                        top_issues.extend(sg.issues[:2])  # Top 2 por sub-goal
            # Limitar a top 10 issues totales
            top_issues = top_issues[:10]
            
            # v4.3.0: Solo actualizar memoria si no estamos en dry_run
            updated_worker_memory = None
            if effective_execution_mode != "dry_run" and memory_store:
                # Cargar memoria previa del worker para detectar regresión
                prev_worker_memory = memory_store.load_worker(worker.id)
                prev_score = prev_worker_memory.last_outcome_score if prev_worker_memory else None

                # Detectar regresión
                if prev_score is not None:
                    delta = global_score - prev_score
                    if delta <= -regression_threshold:
                        regression_flag = {
                            "type": "strong_regression",
                            "previous_score": prev_score,
                            "current_score": global_score,
                            "delta": delta
                        }
                        worker_status.regression_flag = regression_flag
                        regressions_detected += 1
                        
                        # Añadir nota de regresión
                        if worker_status.notes:
                            worker_status.notes += f" ⚠️ Posible regresión: la puntuación global ha bajado de {int(prev_score * 100)} → {int(global_score * 100)}."
                        else:
                            worker_status.notes = f"⚠️ Posible regresión: la puntuación global ha bajado de {int(prev_score * 100)} → {int(global_score * 100)}."

                # Actualizar memoria del worker
                updated_worker_memory = memory_store.update_worker_outcome(
                    worker_id=worker.id,
                    new_score=global_score,
                    issues=top_issues,
                    timestamp=now
                )
                
                # Actualizar memoria de empresa
                memory_store.update_company_outcome(
                    company_name=cae_request.company_name,
                    platform=cae_request.platform,
                    worker_contribution_score=global_score,
                    issues=top_issues,
                    timestamp=now
                )
                
                # Actualizar memoria de plataforma
                memory_store.update_platform_outcome(
                    platform_name=cae_request.platform,
                    company_contribution_score=global_score,
                    issues=top_issues,
                    timestamp=now
                )
            else:
                # v4.3.0: En dry_run, cargar memoria solo para lectura (no actualizar)
                if memory_store:
                    updated_worker_memory = memory_store.load_worker(worker.id)
            
            # v4.3.0: En dry_run, añadir nota de simulación
            if effective_execution_mode == "dry_run":
                if worker_status.notes:
                    worker_status.notes = f"(Simulación, no se han realizado acciones reales) {worker_status.notes}"
                else:
                    worker_status.notes = "(Simulación, no se han realizado acciones reales)"
            
            # Enriquecer worker_status con memory_summary_outcome
            if updated_worker_memory:
                # Cargar también memoria de empresa para common_issues (solo si no es dry_run)
                company_memory = None
                if effective_execution_mode != "dry_run" and memory_store:
                    company_memory = memory_store.load_company(cae_request.company_name, cae_request.platform)
                elif effective_execution_mode == "dry_run" and memory_store:
                    # En dry_run, solo leer (no actualizar)
                    company_memory = memory_store.load_company(cae_request.company_name, cae_request.platform)
                
                memory_summary_outcome = {
                    "last_outcome_score": updated_worker_memory.last_outcome_score,
                    "best_outcome_score": updated_worker_memory.best_outcome_score,
                    "worst_outcome_score": updated_worker_memory.worst_outcome_score,
                    "outcome_run_count": updated_worker_memory.outcome_run_count,
                    "last_outcome_timestamp": updated_worker_memory.last_outcome_timestamp.isoformat() if updated_worker_memory.last_outcome_timestamp else None,
                }
                
                if company_memory and company_memory.common_issues:
                    memory_summary_outcome["common_issues_company"] = company_memory.common_issues
                
                worker_status.memory_summary_outcome = memory_summary_outcome
                
                # Añadir nota histórica si hay suficiente información
                if updated_worker_memory.outcome_run_count > 1:
                    avg_score = updated_worker_memory.last_outcome_score
                    if avg_score is not None:
                        score_text = "excelente" if avg_score >= 0.8 else "buena" if avg_score >= 0.6 else "regular" if avg_score >= 0.4 else "baja"
                        historical_note = f"Históricamente este trabajador tiene calidad de documentación {score_text} (media ~{int(avg_score * 100)}/100)."
                        if worker_status.notes:
                            worker_status.notes = f"{historical_note} {worker_status.notes}"
                        else:
                            worker_status.notes = historical_note
                
                if company_memory and company_memory.common_issues:
                    issues_note = f"Se han detectado problemas recurrentes en esta empresa: {', '.join(company_memory.common_issues[:3])}."
                    if worker_status.notes:
                        worker_status.notes = f"{worker_status.notes} {issues_note}"
                    else:
                        worker_status.notes = issues_note
    
    except Exception as e:
        logger.warning(f"[cae-adapter] Error al actualizar memoria de outcome: {e}", exc_info=True)
    
    # Construir summary global
    total_workers = len(cae_request.workers)
    success_count = sum(1 for w in worker_statuses if w.success)
    failure_count = total_workers - success_count
    workers_with_errors = sum(1 for w in worker_statuses if w.upload_errors)
    workers_with_missing_docs = sum(1 for w in worker_statuses if w.missing_docs)
    
    summary = {
        "total_workers": total_workers,
        "success_count": success_count,
        "failure_count": failure_count,
        "workers_with_errors": workers_with_errors,
        "workers_with_missing_docs": workers_with_missing_docs,
        "total_uploaded_docs": sum(len(w.uploaded_docs) for w in worker_statuses),
        "total_upload_errors": sum(len(w.upload_errors) for w in worker_statuses),
        # Reutilizar información del batch genérico
        "batch_summary": batch_response.summary,
    }
    
    # v4.2.0: Añadir información de outcome y regresiones al summary
    if memory_store:
        # Calcular avg_outcome_score de workers con outcome_judge
        outcome_scores = []
        workers_with_low_score = 0
        for result in batch_response.goals:
            if result.outcome_judge and result.outcome_judge.global_review:
                score = result.outcome_judge.global_review.global_score
                if score is not None:
                    outcome_scores.append(score)
                    if score < 0.6:  # Score bajo (< 60%)
                        workers_with_low_score += 1
        
        if outcome_scores:
            avg_outcome_score_workers = sum(outcome_scores) / len(outcome_scores)
            summary["avg_outcome_score_workers"] = round(avg_outcome_score_workers, 2)
            summary["workers_with_low_score"] = workers_with_low_score
        
        summary["regressions_detected"] = regressions_detected
        summary["regression_threshold"] = regression_threshold
    
    logger.info(
        f"[cae-adapter] Built CAE response: {total_workers} workers, "
        f"{success_count} success, {failure_count} failures"
    )
    
    # v3.9.0: Actualizar memoria persistente
    memory_store: Optional[MemoryStore] = None
    memory_summary: Dict[str, Any] = {}
    
    try:
        memory_store = MemoryStore(MEMORY_BASE_DIR)
        now = datetime.now()
        
        # Actualizar memoria por trabajador
        for worker_status in worker_statuses:
            try:
                # Cargar memoria existente o crear nueva
                worker_memory = memory_store.load_worker(worker_status.worker_id)
                if not worker_memory:
                    worker_memory = WorkerMemory(
                        worker_id=worker_status.worker_id,
                        full_name=worker_status.full_name,
                        company_name=cae_request.company_name,
                    )
                
                # Actualizar información
                worker_memory.full_name = worker_status.full_name
                worker_memory.company_name = cae_request.company_name
                worker_memory.last_seen = now
                
                # Incrementar contadores de documentos exitosos
                for doc_type in worker_status.uploaded_docs:
                    worker_memory.successful_docs[doc_type] = worker_memory.successful_docs.get(doc_type, 0) + 1
                
                # Incrementar contadores de documentos fallidos
                for doc_type in worker_status.missing_docs:
                    worker_memory.failed_docs[doc_type] = worker_memory.failed_docs.get(doc_type, 0) + 1
                
                for error in worker_status.upload_errors:
                    # Intentar extraer tipo de documento del error
                    for doc_type in DOC_TYPE_NAMES.keys():
                        if doc_type in error.lower():
                            worker_memory.failed_docs[doc_type] = worker_memory.failed_docs.get(doc_type, 0) + 1
                            break
                    else:
                        # Si no se puede identificar, usar "unknown"
                        worker_memory.failed_docs["unknown"] = worker_memory.failed_docs.get("unknown", 0) + 1
                
                # Actualizar notas si hay errores repetidos
                if worker_status.upload_errors:
                    failed_doc_types = [doc for doc, count in worker_memory.failed_docs.items() if count > 1]
                    if failed_doc_types:
                        worker_memory.notes = f"Ha fallado repetidamente en: {', '.join(failed_doc_types)}"
                
                # Guardar memoria del trabajador
                memory_store.save_worker(worker_memory)
                
                # Añadir resumen de memoria al worker_status
                worker_status.memory_summary = {
                    "worker_successful_docs": dict(worker_memory.successful_docs),
                    "worker_failed_docs": dict(worker_memory.failed_docs),
                }
                
            except Exception as e:
                logger.warning(f"[cae-adapter] Failed to update memory for worker {worker_status.worker_id}: {e}")
        
        # Actualizar memoria de empresa
        try:
            company_memory = memory_store.load_company(cae_request.company_name, cae_request.platform)
            if not company_memory:
                company_memory = CompanyMemory(
                    company_name=cae_request.company_name,
                    platform=cae_request.platform,
                )
            
            company_memory.last_seen = now
            
            # Contar documentos requeridos y faltantes por tipo
            for worker_status in worker_statuses:
                # Contar documentos requeridos (de la petición original)
                worker = next((w for w in cae_request.workers if w.id == worker_status.worker_id), None)
                if worker and worker.required_docs:
                    for doc_type in worker.required_docs:
                        company_memory.required_docs_counts[doc_type] = company_memory.required_docs_counts.get(doc_type, 0) + 1
                
                # Contar documentos faltantes
                for doc_type in worker_status.missing_docs:
                    company_memory.missing_docs_counts[doc_type] = company_memory.missing_docs_counts.get(doc_type, 0) + 1
                
                # Contar errores de upload
                for error in worker_status.upload_errors:
                    for doc_type in DOC_TYPE_NAMES.keys():
                        if doc_type in error.lower():
                            company_memory.upload_error_counts[doc_type] = company_memory.upload_error_counts.get(doc_type, 0) + 1
                            break
            
            memory_store.save_company(company_memory)
            
            # Añadir resumen de empresa a memory_summary
            memory_summary["company"] = {
                "required_docs_counts": dict(company_memory.required_docs_counts),
                "missing_docs_counts": dict(company_memory.missing_docs_counts),
                "upload_error_counts": dict(company_memory.upload_error_counts),
            }
            
        except Exception as e:
            logger.warning(f"[cae-adapter] Failed to update company memory: {e}")
        
        # Actualizar memoria de plataforma
        try:
            platform_memory = memory_store.load_platform(cae_request.platform)
            if not platform_memory:
                platform_memory = PlatformMemory(platform=cae_request.platform)
            
            platform_memory.last_seen = now
            
            # Contar uso de características visuales y OCR desde métricas
            total_visual_clicks = 0
            total_visual_recoveries = 0
            total_upload_errors = 0
            total_ocr_usage = 0
            
            for worker_status in worker_statuses:
                if worker_status.metrics_summary:
                    summary_metrics = worker_status.metrics_summary.get("summary", {})
                    
                    # Visual clicks
                    visual_click_info = summary_metrics.get("visual_click_info", {})
                    total_visual_clicks += visual_click_info.get("visual_click_attempts", 0)
                    
                    # Visual recovery (aproximación: visual_flow_updates)
                    visual_flow_info = summary_metrics.get("visual_flow_info", {})
                    total_visual_recoveries += visual_flow_info.get("visual_flow_updates", 0)
                    
                    # Upload errors
                    upload_info = summary_metrics.get("upload_info", {})
                    total_upload_errors += upload_info.get("upload_attempts", 0) - upload_info.get("upload_successes", 0)
                    
                    # OCR usage
                    ocr_info = summary_metrics.get("ocr_info", {})
                    total_ocr_usage += ocr_info.get("ocr_calls", 0)
            
            platform_memory.visual_click_usage += total_visual_clicks
            platform_memory.visual_recovery_usage += total_visual_recoveries
            platform_memory.upload_error_counts += total_upload_errors
            platform_memory.ocr_usage += total_ocr_usage
            
            memory_store.save_platform(platform_memory)
            
            # Añadir resumen de plataforma a memory_summary
            memory_summary["platform"] = {
                "visual_click_usage": platform_memory.visual_click_usage,
                "visual_recovery_usage": platform_memory.visual_recovery_usage,
                "upload_error_counts": platform_memory.upload_error_counts,
                "ocr_usage": platform_memory.ocr_usage,
            }
            
        except Exception as e:
            logger.warning(f"[cae-adapter] Failed to update platform memory: {e}")
        
    except Exception as e:
        logger.warning(f"[cae-adapter] Failed to initialize memory store: {e}")
    
    return CAEBatchResponse(
        platform=cae_request.platform,
        company_name=cae_request.company_name,
        workers=worker_statuses,
        summary=summary,
        memory_summary=memory_summary if memory_summary else None,  # v3.9.0
    )

