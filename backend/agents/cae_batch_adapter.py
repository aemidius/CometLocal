"""
Adaptador CAE batch sobre el motor batch genérico.

v3.1.0: Transforma peticiones CAE específicas en BatchAgentRequest genérico
y post-procesa resultados batch en informes CAE estructurados.
"""

import logging
from typing import List, Dict, Any

from backend.shared.models import (
    CAEBatchRequest,
    CAEWorker,
    BatchAgentRequest,
    BatchAgentGoal,
    BatchAgentResponse,
    BatchAgentGoalResult,
    CAEBatchResponse,
    CAEWorkerDocStatus,
)

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
    
    Args:
        cae_request: Petición batch CAE
        
    Returns:
        BatchAgentRequest equivalente
    """
    goals: List[BatchAgentGoal] = []
    
    # Asegurar que context_strategies incluye "cae" si no está especificado
    context_strategies = cae_request.context_strategies or ["cae"]
    if "cae" not in context_strategies:
        context_strategies = ["cae"] + context_strategies
    
    for worker in cae_request.workers:
        # Construir objetivo textual en español para el agente
        goal_text = _build_cae_goal_text(cae_request, worker)
        
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
    
    logger.info(
        f"[cae-adapter] Built CAE response: {total_workers} workers, "
        f"{success_count} success, {failure_count} failures"
    )
    
    return CAEBatchResponse(
        platform=cae_request.platform,
        company_name=cae_request.company_name,
        workers=worker_statuses,
        summary=summary,
    )

