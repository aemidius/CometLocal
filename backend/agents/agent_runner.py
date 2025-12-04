from typing import List, Optional, Tuple, Dict, Any
import re
import time
import logging
import os
import asyncio
import unicodedata
from dataclasses import dataclass, field
from collections import defaultdict
from urllib.parse import quote_plus, urlparse, parse_qs

from openai import AsyncOpenAI

from backend.browser.browser import BrowserController
from backend.shared.models import BrowserAction, BrowserObservation, StepResult, SourceInfo
from backend.planner.simple_planner import SimplePlanner
from backend.planner.llm_planner import LLMPlanner
from backend.config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL, DEFAULT_IMAGE_SEARCH_URL_TEMPLATE
from backend.agents.session_context import SessionContext
from backend.agents.execution_profile import ExecutionProfile
from backend.agents.context_strategies import (
    DEFAULT_CONTEXT_STRATEGIES,
    ContextStrategy,
    build_context_strategies,
)
from backend.agents.retry_policy import RetryPolicy
from backend.agents.execution_plan import ExecutionPlan, PlannedSubGoal

logger = logging.getLogger(__name__)


class EarlyStopReason:
    """
    Constantes centralizadas para los motivos de early-stop.
    v1.4.8: Centralización para evitar typos y facilitar mantenimiento.
    """
    GOAL_SATISFIED_ON_INITIAL_PAGE = "goal_satisfied_on_initial_page"
    GOAL_SATISFIED_AFTER_ENSURE_CONTEXT_BEFORE_LLM = "goal_satisfied_after_ensure_context_before_llm"
    GOAL_SATISFIED_AFTER_ACTION = "goal_satisfied_after_action"
    GOAL_SATISFIED_AFTER_REORIENTATION = "goal_satisfied_after_reorientation"


@dataclass
class SubGoalMetrics:
    """
    Métricas de un sub-objetivo individual.
    v1.5.0: Estructura para almacenar métricas por sub-objetivo.
    """
    goal: str
    focus_entity: Optional[str]
    goal_type: str  # "wikipedia", "images", "other"
    steps_taken: int
    early_stop_reason: Optional[str]  # EarlyStopReason.* o None
    elapsed_seconds: float
    success: bool


class AgentMetrics:
    """
    Recolecta y agrega métricas de ejecución del agente.
    v1.5.0: Infraestructura de observabilidad para medir eficiencia y patrones.
    v2.3.0: Añade contadores de uploads de archivos.
    """
    def __init__(self):
        self.sub_goals: List[SubGoalMetrics] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        # v2.3.0: Contadores de uploads
        self.upload_attempts: int = 0
        self.upload_successes: int = 0
        # v2.5.0: Contadores de verificación de uploads
        self.upload_confirmed_count: int = 0
        self.upload_unconfirmed_count: int = 0
        self.upload_error_detected_count: int = 0
        # v2.6.0: Contadores de retry
        self.retry_attempts: int = 0
        self.retry_successes: int = 0
        self.retry_exhausted_count: int = 0
        # v2.8.0: Contadores de planificación
        self.plan_generated: bool = False
        self.plan_confirmed: bool = False
        self.plan_cancelled: bool = False
        # v2.9.0: Contadores de sub-goals saltados
        self.skipped_sub_goals_count: int = 0
        self.skipped_sub_goal_indices: List[int] = []
        # v3.2.0: Contadores de confirmación visual
        self.visual_confirmations_attempted: int = 0
        self.visual_confirmations_failed: int = 0
    
    def start(self):
        """Marca el inicio de la ejecución completa."""
        self.start_time = time.monotonic()
    
    def finish(self):
        """Marca el fin de la ejecución completa."""
        self.end_time = time.monotonic()
    
    def add_subgoal_metrics(
        self,
        goal: str,
        focus_entity: Optional[str],
        goal_type: str,
        steps_taken: int,
        early_stop_reason: Optional[str],
        elapsed_seconds: float,
        success: bool,
    ):
        """
        Añade métricas de un sub-objetivo.
        
        Args:
            goal: Texto del sub-objetivo
            focus_entity: Entidad focal (si existe)
            goal_type: Tipo de objetivo ("wikipedia", "images", "other")
            steps_taken: Número de pasos ejecutados
            early_stop_reason: Razón de early-stop (EarlyStopReason.*) o None
            elapsed_seconds: Tiempo transcurrido en segundos
            success: True si terminó exitosamente (early-stop por objetivo cumplido)
        """
        metrics = SubGoalMetrics(
            goal=goal,
            focus_entity=focus_entity,
            goal_type=goal_type,
            steps_taken=steps_taken,
            early_stop_reason=early_stop_reason,
            elapsed_seconds=elapsed_seconds,
            success=success,
        )
        self.sub_goals.append(metrics)
    
    def register_upload_verification(self, status: Optional[str]) -> None:
        """
        Registra el resultado de una verificación de upload.
        
        v2.5.1: Helper para actualizar contadores de verificación automáticamente.
        
        Args:
            status: Estado de verificación ("confirmed", "not_confirmed", "error_detected", etc.)
        """
        if not status:
            return
        
        if status == "confirmed":
            self.upload_confirmed_count += 1
        elif status == "not_confirmed":
            self.upload_unconfirmed_count += 1
        elif status == "error_detected":
            self.upload_error_detected_count += 1
        # "not_applicable" y otros estados se ignoran
    
    def register_upload_attempt(self, upload_status: Optional[Dict[str, Any]]) -> None:
        """
        Registra un intento de upload y su resultado.
        
        v2.5.1: Helper para actualizar contadores de uploads automáticamente.
        
        Args:
            upload_status: Dict con status del upload (puede ser dict o string para compatibilidad)
        """
        if not upload_status:
            return
        
        self.upload_attempts += 1
        
        # v2.4.0: Soporte para formato nuevo (dict) y antiguo (string)
        status = upload_status.get("status") if isinstance(upload_status, dict) else upload_status
        if status == "success":
            self.upload_successes += 1
    
    def register_retry_attempt(self) -> None:
        """
        Registra un intento de retry.
        
        v2.6.0: Helper para actualizar contadores de retry.
        """
        self.retry_attempts += 1
    
    def register_retry_success(self) -> None:
        """
        Registra un retry exitoso.
        
        v2.6.0: Helper para actualizar contadores de retry.
        """
        self.retry_successes += 1
    
    def register_retry_exhausted(self) -> None:
        """
        Registra que se agotaron los retries sin éxito.
        
        v2.6.0: Helper para actualizar contadores de retry.
        """
        self.retry_exhausted_count += 1
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """
        Genera un resumen serializable de todas las métricas.
        
        Returns:
            Dict con:
            - sub_goals: Lista de métricas por sub-objetivo
            - summary: Resumen agregado (totales, ratios, conteos)
        """
        total_sub_goals = len(self.sub_goals)
        total_steps = sum(m.steps_taken for m in self.sub_goals)
        total_time = sum(m.elapsed_seconds for m in self.sub_goals)
        
        # Conteo por early_stop_reason
        early_stop_counts: Dict[str, int] = defaultdict(int)
        for m in self.sub_goals:
            reason = m.early_stop_reason or "none"
            early_stop_counts[reason] += 1
        
        # Conteo por goal_type
        goal_type_counts: Dict[str, int] = defaultdict(int)
        goal_type_success: Dict[str, int] = defaultdict(int)
        for m in self.sub_goals:
            goal_type_counts[m.goal_type] += 1
            if m.success:
                goal_type_success[m.goal_type] += 1
        
        # Ratios de éxito por goal_type
        goal_type_success_ratio: Dict[str, float] = {}
        for goal_type, total in goal_type_counts.items():
            success_count = goal_type_success[goal_type]
            ratio = success_count / total if total > 0 else 0.0
            goal_type_success_ratio[goal_type] = round(ratio, 3)
        
        # Tiempo total (si se marcó inicio/fin)
        execution_time = None
        if self.start_time is not None and self.end_time is not None:
            execution_time = round(self.end_time - self.start_time, 3)
        
        # v2.3.0: Calcular promedios
        avg_steps_per_subgoal = total_steps / total_sub_goals if total_sub_goals > 0 else 0.0
        avg_elapsed_seconds = total_time / total_sub_goals if total_sub_goals > 0 else 0.0
        success_count = sum(1 for m in self.sub_goals if m.success)
        
        # v2.3.0: Información de uploads
        upload_info = {
            "upload_attempts": self.upload_attempts,
            "upload_successes": self.upload_successes,
            "upload_success_ratio": round(self.upload_successes / self.upload_attempts, 3) if self.upload_attempts > 0 else 0.0,
        }
        
        # v2.5.0: Información de verificación de uploads
        upload_verification_info = {
            "upload_confirmed_count": self.upload_confirmed_count,
            "upload_unconfirmed_count": self.upload_unconfirmed_count,
            "upload_error_detected_count": self.upload_error_detected_count,
            "upload_verification_confirmed_ratio": round(
                self.upload_confirmed_count / max(1, self.upload_attempts), 3
            ) if self.upload_attempts > 0 else 0.0,
        }
        
        # v2.6.0: Información de retry
        retry_info = {
            "retry_attempts": self.retry_attempts,
            "retry_successes": self.retry_successes,
            "retry_exhausted_count": self.retry_exhausted_count,
            "retry_success_ratio": round(
                self.retry_successes / max(1, self.retry_attempts), 3
            ) if self.retry_attempts > 0 else 0.0,
        }
        
        # v2.8.0: Información de planificación
        planning_info = {
            "plan_generated": self.plan_generated,
            "plan_confirmed": self.plan_confirmed,
            "plan_cancelled": self.plan_cancelled,
        }
        
        # v2.9.0: Información de sub-goals saltados
        skipped_info = {
            "skipped_sub_goals_count": self.skipped_sub_goals_count,
            "skipped_sub_goal_indices": self.skipped_sub_goal_indices,
        }
        
        # v3.2.0: Información de confirmación visual
        visual_confirmation_info = {
            "visual_confirmations_attempted": self.visual_confirmations_attempted,
            "visual_confirmations_failed": self.visual_confirmations_failed,
            "visual_confirmation_success_ratio": round(
                (self.visual_confirmations_attempted - self.visual_confirmations_failed) / 
                max(1, self.visual_confirmations_attempted), 3
            ) if self.visual_confirmations_attempted > 0 else 0.0,
        }
        
        # Serializar sub_goals
        sub_goals_data = []
        for m in self.sub_goals:
            sub_goals_data.append({
                "goal": m.goal,
                "focus_entity": m.focus_entity,
                "goal_type": m.goal_type,
                "steps_taken": m.steps_taken,
                "early_stop_reason": m.early_stop_reason,
                "elapsed_seconds": round(m.elapsed_seconds, 3),
                "success": m.success,
            })
        
        return {
            "sub_goals": sub_goals_data,
            "summary": {
                "total_sub_goals": total_sub_goals,
                "total_steps": total_steps,
                "total_time_seconds": round(total_time, 3),
                "execution_time_seconds": execution_time,
                "success_count": success_count,
                "avg_steps_per_subgoal": round(avg_steps_per_subgoal, 1),
                "avg_elapsed_seconds": round(avg_elapsed_seconds, 3),
                "early_stop_counts": dict(early_stop_counts),
                "goal_type_counts": dict(goal_type_counts),
                "goal_type_success_ratio": goal_type_success_ratio,
                "upload_info": upload_info,  # v2.3.0
                "upload_verification_info": upload_verification_info,  # v2.5.0
                "retry_info": retry_info,  # v2.6.0
                "planning_info": planning_info,  # v2.8.0
                "skipped_info": skipped_info,  # v2.9.0
                "visual_confirmation_info": visual_confirmation_info,  # v3.2.0
                "mode": "interactive",  # v3.0.0: Marcar modo interactivo
            }
        }


def _goal_mentions_wikipedia(goal: str) -> bool:
    text = goal.lower()
    return "wikipedia" in text


def _goal_requires_wikipedia(goal: str) -> bool:
    """Returns True if the goal requires Wikipedia context (obligatory)."""
    text = goal.lower()
    return "wikipedia" in text


def _goal_mentions_images(goal: str) -> bool:
    text = goal.lower()
    keywords = ["imagen", "imágenes", "foto", "fotos", "picture", "pictures", "image", "images"]
    return any(keyword in text for keyword in keywords)


def _infer_goal_type(goal: str) -> str:
    """
    Infiere el tipo de objetivo basándose en el contenido del goal.
    v1.5.0: Helper para clasificar objetivos en "wikipedia", "images", o "other".
    """
    goal_lower = goal.lower()
    if _goal_mentions_wikipedia(goal):
        return "wikipedia"
    elif _goal_mentions_images(goal):
        return "images"
    else:
        return "other"


def _add_metrics_to_steps(
    steps: List[StepResult],
    goal: str,
    focus_entity: Optional[str],
    steps_taken: int,
    early_stop_reason: Optional[str],
    elapsed_seconds: float,
    success: bool,
) -> None:
    """
    Adjunta métricas de sub-goal al último StepResult.
    v1.5.0: Helper para registrar métricas que luego serán leídas por run_llm_task_with_answer
    para alimentar AgentMetrics.
    
    Args:
        steps: Lista de StepResult (se modifica el último)
        goal: Texto del objetivo
        focus_entity: Entidad focal (opcional)
        steps_taken: Número de pasos ejecutados
        early_stop_reason: Razón de early-stop (opcional)
        elapsed_seconds: Tiempo transcurrido en segundos
        success: True si terminó exitosamente
    """
    if not steps:
        return
    
    # Inferir goal_type usando helper existente
    goal_type = _infer_goal_type(goal)
    
    # Construir dict de métricas
    metrics_dict = {
        "goal": goal,
        "focus_entity": focus_entity,
        "goal_type": goal_type,
        "steps_taken": steps_taken,
        "early_stop_reason": early_stop_reason,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "success": success,
    }
    
    # Añadir al último step
    last_step = steps[-1]
    if last_step.info is None:
        last_step.info = {}
    else:
        last_step.info = dict(last_step.info)
    
    last_step.info["metrics_subgoal"] = metrics_dict
    
    logger.debug(
        "[metrics] sub-goal metrics attached: goal=%r focus_entity=%r steps=%d early_stop=%r elapsed=%.2f success=%r goal_type=%s",
        goal,
        focus_entity,
        steps_taken,
        early_stop_reason,
        elapsed_seconds,
        success,
        goal_type,
    )


def _extract_sources_from_steps(steps: List[StepResult]) -> List[Dict[str, Any]]:
    """
    Extrae fuentes únicas de una lista de StepResult.
    v1.6.0: Helper para agrupar fuentes por sub-goal.
    """
    seen_urls = set()
    sources = []
    
    for step in steps:
        if not step.observation or not step.observation.url:
            continue
        
        url = step.observation.url
        if url in seen_urls:
            continue
        
        seen_urls.add(url)
        title = step.observation.title or ""
        
        # Inferir goal_type de la URL
        goal_type = "other"
        if "wikipedia.org" in url.lower():
            goal_type = "wikipedia"
        elif "duckduckgo.com" in url.lower() and ("ia=images" in url.lower() or "iax=images" in url.lower()):
            goal_type = "images"
        
        sources.append({
            "url": url,
            "title": title,
            "goal_type": goal_type,
        })
    
    return sources


async def _maybe_execute_file_upload(
    browser: BrowserController,
    instruction: "FileUploadInstruction",
) -> Optional[StepResult]:
    """
    Intenta ejecutar un upload de archivo si hay un input[type='file'] disponible.
    
    v2.3.0: Conecta FileUploadInstruction con la acción real de upload en el navegador.
    
    Args:
        browser: Instancia de BrowserController
        instruction: FileUploadInstruction con la información del archivo a subir
        
    Returns:
        StepResult con el resultado del upload, o None si no se puede ejecutar
    """
    from backend.agents.file_upload import FileUploadInstruction
    from backend.shared.models import BrowserAction, BrowserObservation
    from pathlib import Path
    
    try:
        # Verificar que el archivo existe
        file_path = Path(instruction.path)
        selector = "input[type='file']"
        
        if not file_path.exists():
            logger.warning(f"[file-upload] File does not exist: {file_path}")
            # Crear StepResult con error
            obs = await browser.get_observation()
            # v2.4.0: Estandarizar estructura de upload_status
            upload_status = {
                "status": "file_not_found",
                "file_path": str(file_path),
                "selector": selector,
                "error_message": f"Archivo no encontrado: {file_path}",
            }
            # v2.5.0: Verificación no aplicable para casos de error previo al upload
            file_name = os.path.basename(str(file_path))
            verification_result = {
                "status": "not_applicable",
                "file_name": file_name,
                "confidence": 0.0,
                "evidence": "",
            }
            return StepResult(
                observation=obs,
                last_action=BrowserAction(
                    type="upload_file",
                    args={"file_path": str(file_path), "selector": selector}
                ),
                error=f"Archivo no encontrado: {file_path}",
                info={
                    "file_upload_instruction": instruction.to_dict(),
                    "upload_status": upload_status,
                    "upload_verification": verification_result,
                }
            )
        
        logger.debug(
            f"[file-upload] Attempting upload: file={file_path} selector={selector}"
        )
        
        # Ejecutar upload
        obs = await browser.upload_file(selector, str(file_path))
        
        # v2.4.0: Estandarizar estructura de upload_status
        upload_status = {
            "status": "success",
            "file_path": str(file_path),
            "selector": selector,
            "error_message": None,
        }
        
        # v2.5.0: Verificar visualmente si el upload fue aceptado
        verification_result = _verify_upload_visually(
            observation=obs,
            file_path=str(file_path),
            goal="",  # El goal se puede obtener del contexto si es necesario
        )
        
        # v3.2.0: Confirmación visual adicional con _verify_action_visually
        file_name = os.path.basename(str(file_path))
        file_name_base = os.path.splitext(file_name)[0]
        visual_confirmation = _verify_action_visually(
            observation=obs,
            expected_effect=f"Confirmar que el archivo {file_name} ha sido subido correctamente",
            keywords=[
                file_name, file_name_base,
                "documento subido", "archivo subido", "documento cargado", "archivo cargado",
                "subido correctamente", "carga completada", "upload complete", "uploaded successfully",
                "documento adjuntado", "archivo adjuntado", "guardado correctamente",
            ],
        )
        visual_confirmation.action_type = "upload_file"
        
        # Construir StepResult con éxito
        info_dict = {
            "file_upload_instruction": instruction.to_dict(),
            "upload_status": upload_status,
            "upload_verification": verification_result,
            "visual_confirmation": visual_confirmation.model_dump(),  # v3.2.0
        }
        
        return StepResult(
            observation=obs,
            last_action=BrowserAction(
                type="upload_file",
                args={"file_path": str(file_path), "selector": selector}
            ),
            error=None,
            info=info_dict,
        )
        
    except Exception as e:
        # Si hay error (no se encuentra input, error de Playwright, etc.)
        logger.debug(f"[file-upload] Upload failed: {e}")
        try:
            obs = await browser.get_observation()
        except Exception:
            # Si no podemos obtener observación, crear una básica
            obs = BrowserObservation(
                url="",
                title="",
                visible_text_excerpt="",
                clickable_texts=[],
                input_hints=[],
            )
        
        # Determinar el tipo de error
        error_msg = str(e)
        selector = "input[type='file']"
        
        if "no se encontró" in error_msg.lower() or "not found" in error_msg.lower():
            status = "no_input_found"
        else:
            status = "error"
        
        # v2.4.0: Estandarizar estructura de upload_status
        upload_status = {
            "status": status,
            "file_path": str(instruction.path),
            "selector": selector,
            "error_message": error_msg,
        }
        
        # v2.5.0: Verificación no aplicable para casos de error
        file_name = os.path.basename(str(instruction.path))
        verification_result = {
            "status": "not_applicable",
            "file_name": file_name,
            "confidence": 0.0,
            "evidence": "",
        }
        
        return StepResult(
            observation=obs,
            last_action=BrowserAction(
                type="upload_file",
                args={"file_path": str(instruction.path), "selector": selector}
            ),
            error=error_msg,
            info={
                "file_upload_instruction": instruction.to_dict(),
                "upload_status": upload_status,
                "upload_verification": verification_result,
            }
        )


def _evaluate_subgoal_for_retry(
    steps: List[StepResult],
    metrics_data: Optional[Dict[str, Any]],
    retry_policy: "RetryPolicy",
) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Evalúa si un sub-goal necesita retry basándose en evidencias.
    
    v2.6.0: Analiza upload_status, upload_verification y success del sub-goal.
    
    Args:
        steps: Lista de StepResult del sub-goal
        metrics_data: Datos de métricas del sub-goal (puede ser None)
        retry_policy: Política de retry a aplicar
        
    Returns:
        Tuple (should_retry, upload_status, verification_status, error_message)
    """
    # Buscar información de upload en los steps
    upload_status = None
    verification_status = None
    error_message = None
    
    for step in reversed(steps):
        if step.info:
            # Buscar upload_status
            if "upload_status" in step.info and not upload_status:
                upload_status_dict = step.info["upload_status"]
                if isinstance(upload_status_dict, dict):
                    upload_status = upload_status_dict.get("status")
                elif isinstance(upload_status_dict, str):
                    upload_status = upload_status_dict
            
            # Buscar upload_verification
            if "upload_verification" in step.info and not verification_status:
                verification_dict = step.info["upload_verification"]
                if isinstance(verification_dict, dict):
                    verification_status = verification_dict.get("status")
            
            # Buscar error
            if step.error and not error_message:
                error_message = step.error
    
    # Evaluar si se debe hacer retry
    should_retry = False
    retry_reason = None
    
    # Si el goal fue exitoso, no hacer retry
    if metrics_data and metrics_data.get("success"):
        return (False, upload_status, verification_status, error_message)
    
    # Si hay upload_status que requiere retry
    if upload_status and retry_policy.should_retry_upload(upload_status):
        should_retry = True
        retry_reason = upload_status
    # Si hay verification_status que requiere retry
    elif verification_status and retry_policy.should_retry_verification(verification_status):
        should_retry = True
        retry_reason = verification_status
    # Si el goal falló y retry_on_goal_failure está activo
    elif retry_policy.retry_on_goal_failure and (not metrics_data or not metrics_data.get("success")):
        should_retry = True
        retry_reason = "goal_failure"
    
    return (should_retry, upload_status, verification_status, error_message)


def _build_retry_prompt_context(
    retry_context: Dict[str, Any],
) -> str:
    """
    Construye el contexto adicional para el prompt cuando hay retry.
    
    v2.6.0: Enriquece el prompt con información del intento anterior.
    
    Args:
        retry_context: Dict con información del intento anterior
        
    Returns:
        String con texto adicional para el prompt
    """
    parts = []
    parts.append("\n\nEl intento anterior de este objetivo no se completó correctamente:")
    
    upload_status = retry_context.get("last_upload_status")
    verification_status = retry_context.get("last_verification_status")
    error_message = retry_context.get("last_error_message")
    
    if upload_status:
        status_text = {
            "not_confirmed": "no se confirmó la subida del archivo",
            "no_input_found": "no se encontró un campo de subida de archivos",
            "error_detected": "se detectó un error durante la subida",
            "file_not_found": "no se encontró el archivo en el repositorio",
            "error": "se produjo un error durante la subida",
        }.get(upload_status, upload_status)
        parts.append(f"- Estado de subida: {status_text}")
    
    if verification_status:
        verification_text = {
            "not_confirmed": "no se encontró confirmación visual del archivo",
            "error_detected": "se detectó un mensaje de error en la página",
        }.get(verification_status, verification_status)
        parts.append(f"- Verificación visual: {verification_text}")
    
    if error_message:
        # Recortar error si es muy largo
        error_short = error_message[:150] + "..." if len(error_message) > 150 else error_message
        parts.append(f"- Error: {error_short}")
    
    parts.append("\nIntenta una estrategia diferente para completar el objetivo.")
    parts.append("Por ejemplo:")
    parts.append("- Busca un botón de guardar o confirmar")
    parts.append("- Reintenta la subida del archivo")
    parts.append("- Ajusta la interacción con el formulario")
    parts.append("- Verifica que el archivo esté en el formato correcto")
    
    return "\n".join(parts)


def _verify_upload_visually(
    observation: BrowserObservation,
    file_path: str,
    goal: str,
) -> Dict[str, Any]:
    """
    Verifica visualmente si un archivo subido ha sido aceptado/registrado en la plataforma.
    
    v2.5.0: Analiza el texto de la página después del upload para detectar:
    - Confirmación de éxito (nombre del archivo, mensajes de éxito)
    - Errores (mensajes de error)
    - Ausencia de confirmación clara
    
    Args:
        observation: BrowserObservation después del upload
        file_path: Ruta del archivo subido
        goal: Objetivo original (para contexto)
        
    Returns:
        Dict con:
        {
            "status": "confirmed" | "not_confirmed" | "error_detected",
            "file_name": str,
            "confidence": float,
            "evidence": str,
        }
    """
    # Obtener nombre del archivo y normalizarlo
    file_name = os.path.basename(file_path)
    file_name_normalized = _normalize_text_for_comparison(file_name)
    
    # Extraer texto de la observación
    # Usamos visible_text_excerpt que ya contiene el texto visible de la página
    page_text = observation.visible_text_excerpt or ""
    page_text_normalized = _normalize_text_for_comparison(page_text)
    
    # Si no hay texto, no podemos verificar
    if not page_text_normalized:
        logger.debug(
            "[upload-verification] No text available for verification: file=%s",
            file_name
        )
        return {
            "status": "not_confirmed",
            "file_name": file_name,
            "confidence": 0.3,
            "evidence": "No se encontró confirmación visual explícita (sin texto disponible)",
        }
    
    # Palabras clave de éxito (español e inglés)
    success_keywords = [
        "documento subido", "archivo subido", "documento cargado", "archivo cargado",
        "subido correctamente", "carga completada", "subida exitosa", "carga exitosa",
        "upload complete", "uploaded successfully", "file uploaded", "upload successful",
        "documento adjuntado", "archivo adjuntado", "adjuntado correctamente",
        "documento guardado", "archivo guardado", "guardado correctamente",
    ]
    
    # Palabras clave de error (español e inglés)
    error_keywords = [
        "error al subir", "no se pudo cargar", "fallo la carga", "falló la carga",
        "formato no permitido", "tamano excede", "tamaño excede", "archivo demasiado grande",
        "upload failed", "error uploading", "failed to upload", "upload error",
        "error al cargar", "no se pudo subir", "error de carga", "carga fallida",
        "archivo no valido", "archivo no válido", "formato incorrecto",
    ]
    
    # Normalizar keywords para comparación
    success_keywords_normalized = [_normalize_text_for_comparison(kw) for kw in success_keywords]
    error_keywords_normalized = [_normalize_text_for_comparison(kw) for kw in error_keywords]
    
    # 1. Buscar patrones de error primero (prioridad)
    error_evidence = None
    for kw in error_keywords_normalized:
        if kw in page_text_normalized:
            # Encontrar el fragmento de texto que contiene la keyword
            idx = page_text_normalized.find(kw)
            start = max(0, idx - 50)
            end = min(len(page_text_normalized), idx + len(kw) + 50)
            error_evidence = page_text[start:end].strip()
            break
    
    if error_evidence:
        logger.debug(
            "[upload-verification] Error detected: file=%s evidence=%r",
            file_name, error_evidence[:100]
        )
        return {
            "status": "error_detected",
            "file_name": file_name,
            "confidence": 0.9,
            "evidence": error_evidence,
        }
    
    # 2. Buscar el nombre del archivo en el texto (confirmación fuerte)
    if file_name_normalized:
        # Buscar el nombre completo o partes del nombre (sin extensión)
        file_name_base = os.path.splitext(file_name_normalized)[0]
        if file_name_normalized in page_text_normalized or file_name_base in page_text_normalized:
            # Encontrar el fragmento donde aparece
            idx = page_text_normalized.find(file_name_normalized)
            if idx == -1:
                idx = page_text_normalized.find(file_name_base)
            start = max(0, idx - 50)
            end = min(len(page_text_normalized), idx + len(file_name_normalized) + 50)
            evidence = page_text[start:end].strip()
            
            logger.debug(
                "[upload-verification] File name found: file=%s evidence=%r",
                file_name, evidence[:100]
            )
            return {
                "status": "confirmed",
                "file_name": file_name,
                "confidence": 0.85,
                "evidence": evidence,
            }
    
    # 3. Buscar mensajes genéricos de éxito
    success_evidence = None
    for kw in success_keywords_normalized:
        if kw in page_text_normalized:
            idx = page_text_normalized.find(kw)
            start = max(0, idx - 50)
            end = min(len(page_text_normalized), idx + len(kw) + 50)
            success_evidence = page_text[start:end].strip()
            break
    
    if success_evidence:
        logger.debug(
            "[upload-verification] Success message found: file=%s evidence=%r",
            file_name, success_evidence[:100]
        )
        return {
            "status": "confirmed",
            "file_name": file_name,
            "confidence": 0.7,
            "evidence": success_evidence,
        }
    
    # 4. No se encontró confirmación clara
    logger.debug(
        "[upload-verification] No confirmation found: file=%s",
        file_name
    )
    return {
        "status": "not_confirmed",
        "file_name": file_name,
        "confidence": 0.3,
        "evidence": "No se encontró confirmación visual explícita",
    }


async def _attempt_visual_recovery(
    browser: BrowserController,
    action_type: str,
    last_observation: BrowserObservation,
) -> Optional["VisualActionResult"]:
    """
    Intenta recuperación visual tras una acción que no fue confirmada.
    
    v3.2.0: Antes de entrar en retry global, intenta estrategias de recuperación:
    - Buscar botones alternativos (Guardar cambios, Aceptar, Finalizar)
    - Hacer scroll una vez
    - Repetir click si aplica
    - Re-verificar visualmente
    
    Args:
        browser: BrowserController para ejecutar acciones
        action_type: Tipo de acción que falló ("click", "upload_file")
        last_observation: Última observación disponible
        
    Returns:
        VisualActionResult si se intentó recuperación, None si no aplica
    """
    from backend.shared.models import VisualActionResult
    
    if action_type != "click":
        # Por ahora solo recuperación para clicks
        return None
    
    logger.debug("[visual-recovery] Attempting visual recovery for action_type=%s", action_type)
    
    try:
        # Estrategia 1: Hacer scroll una vez
        if browser.page:
            await browser.page.evaluate("window.scrollBy(0, 300)")
            await asyncio.sleep(0.5)  # Pequeña pausa para que se renderice
        
        # Estrategia 2: Buscar botones alternativos en la página
        observation = await browser.get_observation()
        clickable_texts = observation.clickable_texts or []
        
        alternative_buttons = ["guardar cambios", "aceptar", "finalizar", "confirmar"]
        clicked_alternative = False
        
        for alt_text in alternative_buttons:
            # Buscar en clickable_texts (normalizado)
            for clickable in clickable_texts:
                if alt_text in clickable.lower():
                    try:
                        await browser.click_by_text(clickable)
                        clicked_alternative = True
                        logger.debug("[visual-recovery] Clicked alternative button: %s", clickable)
                        await asyncio.sleep(0.5)  # Pausa para que se procese
                        break
                    except Exception as e:
                        logger.debug("[visual-recovery] Failed to click alternative button %s: %s", clickable, e)
                        continue
            
            if clicked_alternative:
                break
        
        # Obtener nueva observación después de la recuperación
        final_observation = await browser.get_observation()
        
        # Verificar si la recuperación tuvo éxito
        recovery_keywords = [
            "guardado", "guardado correctamente", "enviado", "enviado correctamente",
            "confirmado", "aceptado", "finalizado", "saved", "sent", "submitted",
        ]
        
        visual_result = _verify_action_visually(
            observation=final_observation,
            expected_effect="Confirmar que la recuperación visual tuvo éxito",
            keywords=recovery_keywords,
        )
        visual_result.action_type = "recovery"
        
        logger.debug(
            "[visual-recovery] Recovery result: confirmed=%r confidence=%.2f",
            visual_result.confirmed, visual_result.confidence
        )
        
        return visual_result
        
    except Exception as e:
        logger.debug("[visual-recovery] Recovery attempt failed: %s", e)
        return None


def _verify_action_visually(
    observation: BrowserObservation,
    expected_effect: str,
    keywords: List[str],
) -> "VisualActionResult":
    """
    Verifica visualmente si una acción crítica ha tenido el efecto esperado.
    
    v3.2.0: Analiza el texto visible de la página después de una acción (click, upload, etc.)
    para confirmar que se ha producido el efecto esperado.
    
    Args:
        observation: BrowserObservation después de la acción
        expected_effect: Descripción humana del efecto esperado (para logging)
        keywords: Lista de palabras clave a buscar en el texto (normalizadas)
        
    Returns:
        VisualActionResult con el resultado de la verificación
    """
    from backend.shared.models import VisualActionResult
    
    # Extraer texto de la observación
    page_text = observation.visible_text_excerpt or ""
    page_text_normalized = _normalize_text_for_comparison(page_text)
    
    # Si no hay texto, no podemos verificar
    if not page_text_normalized:
        logger.debug(
            "[visual-confirmation] No text available: expected_effect=%r",
            expected_effect
        )
        return VisualActionResult(
            action_type="unknown",
            expected_effect=expected_effect,
            confirmed=False,
            confidence=0.3,
            evidence="No se encontró texto disponible para verificación",
        )
    
    # Normalizar keywords para comparación
    keywords_normalized = [_normalize_text_for_comparison(kw) for kw in keywords]
    
    # Buscar matches de keywords
    matches = []
    for kw in keywords_normalized:
        if kw in page_text_normalized:
            # Encontrar el fragmento de texto que contiene la keyword
            idx = page_text_normalized.find(kw)
            start = max(0, idx - 50)
            end = min(len(page_text_normalized), idx + len(kw) + 50)
            evidence_fragment = page_text[start:end].strip()
            matches.append((kw, evidence_fragment))
    
    # Determinar resultado según número de matches
    if len(matches) >= 1:
        # Al menos una keyword encontrada → confirmado
        # Confidence aumenta con más matches
        confidence = min(0.7 + (len(matches) - 1) * 0.1, 0.95)
        evidence = "; ".join([frag for _, frag in matches[:3]])  # Máximo 3 fragmentos
        
        logger.debug(
            "[visual-confirmation] Action confirmed: expected_effect=%r matches=%d confidence=%.2f",
            expected_effect, len(matches), confidence
        )
        
        return VisualActionResult(
            action_type="unknown",  # Se establecerá en el llamador
            expected_effect=expected_effect,
            confirmed=True,
            confidence=confidence,
            evidence=evidence,
        )
    else:
        # No se encontraron keywords → no confirmado
        logger.debug(
            "[visual-confirmation] Action not confirmed: expected_effect=%r",
            expected_effect
        )
        
        return VisualActionResult(
            action_type="unknown",
            expected_effect=expected_effect,
            confirmed=False,
            confidence=0.3,
            evidence="No se encontraron indicadores visuales del efecto esperado",
        )


def _summarize_uploads_for_subgoal(steps: List[StepResult]) -> Optional[Dict[str, Any]]:
    """
    Dado el listado de steps de un sub-goal, analiza los upload_status
    y devuelve un pequeño resumen estructurado, o None si no hay uploads.
    
    v2.4.0: Helper para resumir intentos de upload por sub-objetivo.
    
    Args:
        steps: Lista de StepResult del sub-goal
        
    Returns:
        Dict con resumen de uploads o None si no hay uploads:
        {
            "status": "success" | "file_not_found" | "no_input_found" | "error",
            "file_path": str | None,
            "selector": str | None,
            "attempts": int,
        }
    """
    upload_statuses = []
    
    for step in steps:
        if step.info and "upload_status" in step.info:
            upload_status = step.info["upload_status"]
            # v2.4.0: Soporte para formato nuevo (dict) y antiguo (string) para compatibilidad
            if isinstance(upload_status, dict):
                upload_statuses.append(upload_status)
            elif isinstance(upload_status, str):
                # Formato antiguo: convertir a formato nuevo
                upload_statuses.append({
                    "status": upload_status,
                    "file_path": step.last_action.args.get("file_path") if step.last_action else None,
                    "selector": step.last_action.args.get("selector") if step.last_action else None,
                    "error_message": step.error,
                })
    
    if not upload_statuses:
        return None
    
    # Usar el último intento como el más relevante
    last_upload = upload_statuses[-1]
    
    # Extraer información
    status = last_upload.get("status") if isinstance(last_upload, dict) else last_upload
    file_path = last_upload.get("file_path") if isinstance(last_upload, dict) else None
    selector = last_upload.get("selector") if isinstance(last_upload, dict) else None
    
    # v2.5.0: Buscar información de verificación en los steps
    verification_status = None
    verification_confidence = None
    verification_evidence = None
    
    # Buscar el último step con upload_verification
    for step in reversed(steps):
        if step.info and "upload_verification" in step.info:
            verification = step.info["upload_verification"]
            if isinstance(verification, dict):
                verification_status = verification.get("status")
                verification_confidence = verification.get("confidence")
                verification_evidence = verification.get("evidence")
                break
    
    result = {
        "status": status,
        "file_path": file_path,
        "selector": selector,
        "attempts": len(upload_statuses),
    }
    
    # v2.5.0: Añadir campos de verificación si existen
    if verification_status is not None:
        result["verification_status"] = verification_status
        result["verification_confidence"] = verification_confidence
        result["verification_evidence"] = verification_evidence
    else:
        result["verification_status"] = None
        result["verification_confidence"] = None
        result["verification_evidence"] = None
    
    return result


def _build_final_answer(
    original_goal: str,
    sub_goals: List[str],
    sub_goal_answers: List[str],
    all_steps: List[StepResult],
    agent_metrics: Optional[AgentMetrics] = None,
    skipped_sub_goal_indices: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Construye una estructura de respuesta final enriquecida.
    v1.6.0: Estructura mejorada con secciones por sub-goal, fuentes y métricas.
    
    Returns:
        Dict con:
        - answer_text: texto final estructurado en español
        - sections: lista de secciones por sub-goal
        - sources: lista global de fuentes deduplicadas
        - metrics_summary: resumen de métricas (si disponible)
    """
    # Agrupar steps por sub_goal_index
    steps_by_subgoal: Dict[int, List[StepResult]] = defaultdict(list)
    for step in all_steps:
        sub_goal_idx = step.info.get("sub_goal_index")
        if sub_goal_idx is not None:
            steps_by_subgoal[sub_goal_idx].append(step)
        else:
            # Si no tiene índice, asignar al primero (caso de un solo sub-goal)
            steps_by_subgoal[1].append(step)
    
    # Construir secciones por sub-goal
    sections = []
    all_sources_dict: Dict[str, Dict[str, Any]] = {}  # url -> source info
    
    for idx, (sub_goal, answer) in enumerate(zip(sub_goals, sub_goal_answers), start=1):
        # Obtener steps de este sub-goal
        sub_goal_steps = steps_by_subgoal.get(idx, [])
        
        # Extraer fuentes de este sub-goal
        sub_goal_sources = _extract_sources_from_steps(sub_goal_steps)
        
        # Obtener información del sub-goal desde los steps o inferirla
        focus_entity = None
        goal_type = _infer_goal_type(sub_goal)
        
        # Buscar focus_entity en los steps
        for step in sub_goal_steps:
            if step.info and step.info.get("focus_entity"):
                focus_entity = step.info["focus_entity"]
                break
        
        # Si no hay focus_entity, intentar extraerla del sub_goal
        if not focus_entity:
            focus_entity = _extract_focus_entity_from_goal(sub_goal)
        
        # v2.4.0: Resumir uploads para este sub-goal
        upload_summary = _summarize_uploads_for_subgoal(sub_goal_steps)
        
        # Construir sección
        section = {
            "index": idx,
            "sub_goal": sub_goal,
            "answer": answer.strip(),
            "goal_type": goal_type,
            "focus_entity": focus_entity,
            "sources": sub_goal_sources,
        }
        
        # v2.4.0: Añadir upload_summary si existe
        if upload_summary:
            section["upload_summary"] = {
                "status": upload_summary["status"],
                "file_name": os.path.basename(upload_summary["file_path"]) if upload_summary.get("file_path") else None,
                "file_path": upload_summary.get("file_path"),
                "attempts": upload_summary["attempts"],
            }
            
            # v2.5.0: Añadir información de verificación si existe
            verification_status = upload_summary.get("verification_status")
            if verification_status is not None:
                section["upload_verification"] = {
                    "status": verification_status,
                    "file_name": upload_summary.get("verification_status") and section["upload_summary"]["file_name"],
                    "confidence": upload_summary.get("verification_confidence"),
                    "evidence": upload_summary.get("verification_evidence"),
                }
            else:
                section["upload_verification"] = None
        else:
            section["upload_summary"] = None
            section["upload_verification"] = None
        
        sections.append(section)
        
        # Agregar fuentes al diccionario global (deduplicar por URL)
        for source in sub_goal_sources:
            url = source["url"]
            if url not in all_sources_dict:
                all_sources_dict[url] = {
                    "url": url,
                    "title": source["title"],
                    "goal_type": source["goal_type"],
                    "sub_goals": [],
                }
            # Añadir este sub-goal a la lista si no está ya
            if idx not in all_sources_dict[url]["sub_goals"]:
                all_sources_dict[url]["sub_goals"].append(idx)
    
    # Convertir diccionario de fuentes a lista
    all_sources = list(all_sources_dict.values())
    
    # Construir texto final estructurado
    answer_parts = []
    
    # Resumen global breve
    if len(sub_goals) > 1:
        answer_parts.append(f"He completado {len(sub_goals)} sub-objetivos relacionados con tu petición.")
    else:
        answer_parts.append("He completado tu petición.")
    
    # v2.9.0: Añadir información de sub-objetivos no ejecutados
    if skipped_sub_goal_indices and len(skipped_sub_goal_indices) > 0:
        skipped_text = ", ".join(map(str, sorted(skipped_sub_goal_indices)))
        answer_parts.append("")
        answer_parts.append(f"Sub-objetivos no ejecutados (por configuración del usuario): {skipped_text}.")
    
    answer_parts.append("")  # Línea en blanco
    
    # Secciones por sub-goal
    for section in sections:
        idx = section["index"]
        sub_goal = section["sub_goal"]
        answer = section["answer"]
        goal_type = section["goal_type"]
        focus_entity = section.get("focus_entity")
        
        # Título de la sección
        if goal_type == "wikipedia" and focus_entity:
            section_title = f"{idx}. Sobre {focus_entity} (Wikipedia)"
        elif goal_type == "images" and focus_entity:
            section_title = f"{idx}. Imágenes de {focus_entity}"
        elif goal_type == "images":
            section_title = f"{idx}. Imágenes"
        else:
            section_title = f"{idx}. {sub_goal}"
        
        answer_parts.append(section_title)
        answer_parts.append(answer)
        
        # Mencionar fuentes principales (sin URLs completas)
        sources = section["sources"]
        if sources:
            source_domains = set()
            source_titles = []
            for source in sources[:2]:  # Máximo 2 fuentes principales
                url = source["url"]
                title = source.get("title", "")
                
                # Extraer dominio
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    domain = parsed.netloc.replace("www.", "")
                    if domain:
                        source_domains.add(domain)
                except Exception:
                    pass
                
                if title and title not in source_titles:
                    source_titles.append(title)
            
            if source_domains or source_titles:
                source_text = "Fuentes: "
                if source_titles:
                    source_text += ", ".join(source_titles[:2])
                elif source_domains:
                    source_text += ", ".join(sorted(source_domains)[:2])
                answer_parts.append(source_text)
        
        # v2.4.0: Añadir descripción de upload si existe
        upload_summary = section.get("upload_summary")
        if upload_summary:
            status = upload_summary["status"]
            file_name = upload_summary.get("file_name")
            file_path = upload_summary.get("file_path")
            
            if status == "success":
                if file_name:
                    upload_text = f"Además, he seleccionado y adjuntado el archivo {file_name} desde el repositorio local en el formulario de la página actual."
                else:
                    upload_text = "Además, he adjuntado un archivo desde el repositorio local en el formulario de la página actual."
            elif status == "file_not_found":
                upload_text = "He intentado localizar y adjuntar el documento en el repositorio local, pero no se ha encontrado el archivo esperado."
            elif status == "no_input_found":
                upload_text = "He buscado un campo de subida de archivos en la página, pero no he encontrado ningún input compatible para adjuntar el documento."
            elif status == "error":
                upload_text = "He intentado adjuntar el documento desde el repositorio local, pero se ha producido un error durante la subida."
            else:
                upload_text = "He intentado adjuntar un documento desde el repositorio local."
            
            answer_parts.append(upload_text)
            
            # v2.5.0: Añadir texto de verificación visual si existe
            upload_verification = section.get("upload_verification")
            if upload_verification and upload_verification.get("status") != "not_applicable":
                verification_status = upload_verification.get("status")
                verification_file_name = upload_verification.get("file_name") or file_name
                verification_evidence = upload_verification.get("evidence", "")
                
                if verification_status == "confirmed":
                    if verification_file_name:
                        verification_text = f"Además, he verificado visualmente que el archivo «{verification_file_name}» aparece en la plataforma, por lo que la subida parece completada correctamente."
                    else:
                        verification_text = "Además, he verificado visualmente que la subida parece completada correctamente."
                elif verification_status == "not_confirmed":
                    if verification_file_name:
                        verification_text = f"He intentado subir el archivo «{verification_file_name}», pero no he encontrado una confirmación visual clara de que haya quedado registrado en la plataforma. Es posible que sea necesario pulsar algún botón de guardar o confirmar."
                    else:
                        verification_text = "He intentado subir el archivo, pero no he encontrado una confirmación visual clara de que haya quedado registrado en la plataforma. Es posible que sea necesario pulsar algún botón de guardar o confirmar."
                elif verification_status == "error_detected":
                    if verification_file_name:
                        if verification_evidence:
                            # Recortar evidencia si es muy larga
                            evidence_short = verification_evidence[:100] + "..." if len(verification_evidence) > 100 else verification_evidence
                            verification_text = f"Tras intentar subir el archivo «{verification_file_name}», he detectado un mensaje de error en la página: «{evidence_short}». Es probable que la subida no se haya completado correctamente."
                        else:
                            verification_text = f"Tras intentar subir el archivo «{verification_file_name}», he detectado un mensaje de error en la página. Es probable que la subida no se haya completado correctamente."
                    else:
                        if verification_evidence:
                            evidence_short = verification_evidence[:100] + "..." if len(verification_evidence) > 100 else verification_evidence
                            verification_text = f"Tras intentar subir el archivo, he detectado un mensaje de error en la página: «{evidence_short}». Es probable que la subida no se haya completado correctamente."
                        else:
                            verification_text = "Tras intentar subir el archivo, he detectado un mensaje de error en la página. Es probable que la subida no se haya completado correctamente."
                else:
                    verification_text = None
                
                if verification_text:
                    answer_parts.append(verification_text)
        
        answer_parts.append("")  # Línea en blanco entre secciones
    
    # v2.2.0: Recoger instrucciones de file upload de todos los steps
    file_upload_instructions = []
    seen_paths = set()
    for step in all_steps:
        if step.info and "file_upload_instruction" in step.info:
            instruction_dict = step.info["file_upload_instruction"]
            path_str = instruction_dict.get("path", "")
            if path_str and path_str not in seen_paths:
                seen_paths.add(path_str)
                file_upload_instructions.append(instruction_dict)
    
    # v2.2.0: Añadir sección sobre documentos locales si existen
    if file_upload_instructions:
        answer_parts.append("")  # Línea en blanco
        answer_parts.append("Además, he identificado los siguientes documentos locales que podrían ser subidos:")
        for instruction in file_upload_instructions:
            description = instruction.get("description", "documento")
            answer_parts.append(f"- {description}")
    
    answer_text = "\n".join(answer_parts).strip()
    
    # Obtener métricas si están disponibles
    metrics_summary = None
    if agent_metrics:
        metrics_summary = agent_metrics.to_summary_dict()
    
    return {
        "answer_text": answer_text,
        "sections": sections,
        "sources": all_sources,
        "metrics_summary": metrics_summary,
    }


def _goal_mentions_pronoun(goal: str) -> bool:
    """
    Devuelve True si el objetivo contiene pronombres de tercera persona
    que suelen referirse a una entidad mencionada antes.
    
    v1.4.3: Función auxiliar para detectar pronombres en el goal.
    """
    lower = goal.lower()
    pronouns = [
        " él", " ella", " ellos", " ellas",
        " su ", " sus ", " suyo", " suya", " suyos", " suyas",
    ]
    padded = f" {lower} "
    return any(p in padded for p in pronouns)


def goal_uses_pronouns(goal: str) -> bool:
    """
    Devuelve True si el goal contiene referencias implícitas que requieren contexto.
    v1.7.0: Helper mejorado para detectar pronombres y referencias implícitas.
    
    Detecta:
    - él, ella, ellos, ellas
    - suyo/suya/suyos/suyas
    - esa persona, esa empresa (referencias genéricas)
    
    Args:
        goal: Texto del objetivo a analizar
        
    Returns:
        True si contiene referencias implícitas, False en caso contrario
    """
    lower = goal.lower()
    
    # Pronombres personales
    personal_pronouns = [
        r"\bél\b", r"\bella\b", r"\bellos\b", r"\bellas\b",
    ]
    
    # Pronombres posesivos
    possessive_pronouns = [
        r"\bsuyo\b", r"\bsuya\b", r"\bsuyos\b", r"\bsuyas\b",
        r"\bsu\b", r"\bsus\b",
    ]
    
    # Referencias genéricas
    generic_references = [
        r"esa persona", r"ese persona",
        r"esa empresa", r"ese empresa",
        r"ese lugar", r"esa lugar",
    ]
    
    # Verificar pronombres personales
    for pattern in personal_pronouns:
        if re.search(pattern, lower):
            return True
    
    # Verificar pronombres posesivos (con contexto de palabra)
    padded = f" {lower} "
    for pronoun in [" su ", " sus ", " suyo", " suya", " suyos", " suyas"]:
        if pronoun in padded:
            return True
    
    # Verificar referencias genéricas
    for ref in generic_references:
        if ref in lower:
            return True
    
    return False


def _is_url_in_wikipedia(url: str | None) -> bool:
    if not url:
        return False
    return "wikipedia.org" in url.lower()


def _is_url_in_image_search(url: str | None) -> bool:
    if not url:
        return False
    url_lower = url.lower()
    return (
        "ia=images" in url_lower
        or "iax=images" in url_lower
        or ("duckduckgo.com" in url_lower and "/images" in url_lower)
    )


def _extract_wikipedia_entity_from_goal(goal: str) -> Optional[str]:
    """
    Extrae la entidad de Wikipedia del objetivo si sigue un patrón conocido.
    
    Soporta patrones como:
    - "investiga quién fue X"
    - "mira información sobre X"
    - "busca información sobre X"
    - "consulta información sobre X"
    
    Devuelve la entidad extraída (sin "en Wikipedia" si estaba presente) o None.
    """
    goal_lower = goal.lower()
    
    # Patrones para extraer la entidad
    # Usamos grupos de captura para encontrar la posición exacta en el texto original
    patterns = [
        (r"investiga\s+qui[eé]n\s+fue\s+(.+?)(?:\s+en\s+wikipedia)?$", "investiga quién fue "),
        (r"investiga\s+quien\s+fue\s+(.+?)(?:\s+en\s+wikipedia)?$", "investiga quien fue "),
        (r"(?:mira|busca|consulta)\s+informaci[oó]n\s+sobre\s+(.+?)(?:\s+en\s+wikipedia)?$", "información sobre "),
    ]
    
    for pattern, prefix in patterns:
        match = re.search(pattern, goal_lower, re.IGNORECASE)
        if match:
            entity_lower = match.group(1).strip()
            # Eliminar "en wikipedia" si quedó al final
            entity_lower = re.sub(r"\s+en\s+wikipedia\s*$", "", entity_lower, flags=re.IGNORECASE)
            # Limpiar espacios y puntuación final
            entity_lower = entity_lower.strip(" ,;.")
            if entity_lower:
                # Buscar la posición del prefijo en el texto original
                prefix_lower = prefix.lower()
                prefix_pos = goal_lower.find(prefix_lower)
                if prefix_pos != -1:
                    # Calcular la posición donde empieza la entidad
                    entity_start = prefix_pos + len(prefix_lower)
                    # Buscar dónde termina la entidad (hasta "en wikipedia" o fin de línea)
                    entity_end_marker = " en wikipedia"
                    if entity_end_marker in goal_lower[entity_start:]:
                        entity_end = goal_lower.find(entity_end_marker, entity_start)
                    else:
                        entity_end = len(goal)
                    # Extraer la entidad del texto original
                    original_entity = goal[entity_start:entity_end].strip(" ,;.")
                    if original_entity:
                        return original_entity
                # Fallback: devolver en minúsculas si no encontramos la posición
                return entity_lower
    
    return None


def _build_wikipedia_article_url(entity: str) -> str:
    """
    Construye la URL de artículo en la Wikipedia en español para una entidad dada.
    """
    slug = entity.strip().replace(" ", "_")
    # Usa quote_plus para codificar caracteres especiales, pero respeta los guiones bajos
    # Primero reemplazamos espacios por guiones bajos, luego codificamos el resto
    encoded_slug = quote_plus(slug, safe="_")
    return f"https://es.wikipedia.org/wiki/{encoded_slug}"


def _is_url_entity_article(url: Optional[str], entity: str) -> bool:
    """
    Comprueba si la URL actual ya es el artículo de esa entidad en Wikipedia.
    """
    if not url:
        return False
    slug = entity.strip().replace(" ", "_")
    # Normalizar la URL para comparación
    url_lower = url.lower()
    slug_lower = slug.lower()
    # Buscar el patrón /wiki/entidad en la URL
    return f"/wiki/{slug_lower}" in url_lower or f"/wiki/{quote_plus(slug_lower, safe='_')}" in url_lower


async def ensure_context(
    goal: str,
    observation: Optional[BrowserObservation],
    browser: BrowserController,
    focus_entity: Optional[str] = None,
    context_strategies: Optional[List[ContextStrategy]] = None,
) -> Optional[BrowserAction]:
    """
    Context reorientation layer: ensures the browser is in a reasonable site
    for the current goal before delegating to the LLM planner.
    Returns a BrowserAction if reorientation is needed, None otherwise.
    
    v1.2: Images have priority over Wikipedia to avoid context contamination.
    v1.3: Uses normalized queries with focus_entity fallback.
    v1.4: Always navigates to new context, never reuses old pages even if in same domain.
    v1.4.1: Performance hotfix - avoid unnecessary reloads if already in correct context.
    v2.0.0: Refactored to use pluggable context strategies.
    v2.1.0: Accepts context_strategies parameter for per-request strategy selection.
    """
    # v2.1.0: Usar estrategias proporcionadas o DEFAULT_CONTEXT_STRATEGIES
    strategies = context_strategies if context_strategies is not None else DEFAULT_CONTEXT_STRATEGIES
    
    # v2.0.0: Usar estrategias de contexto por dominio
    for strategy in strategies:
        if strategy.goal_applies(goal, focus_entity):
            action = await strategy.ensure_context(goal, observation, focus_entity)
            # Logging para diagnóstico (mantener compatibilidad con v1.4.7)
            if action and action.type == "open_url" and "duckduckgo.com" in action.args.get("url", ""):
                # Extraer query de la URL para logging
                try:
                    from urllib.parse import urlparse, parse_qs
                    parsed = urlparse(action.args["url"])
                    query_params = parse_qs(parsed.query)
                    q_value = query_params.get('q', [''])[0]
                    logger.info(
                        "[image-query] goal=%r focus_entity=%r query=%r",
                        goal,
                        focus_entity,
                        q_value.replace('+', ' '),
                    )
                except Exception:
                    pass
            # v2.1.0: Logging para CAE
            if action and action.type == "open_url" and "cae" in goal.lower():
                logger.debug(f"[cae-context] navigating to CAE platform for goal: {goal!r}")
            return action
    
    # No reorientation needed (ninguna estrategia aplica)
    return None


def _goal_is_satisfied(
    goal: str,
    observation: Optional[BrowserObservation],
    focus_entity: Optional[str],
    context_strategies: Optional[List[ContextStrategy]] = None,
) -> bool:
    """
    Devuelve True si, para objetivos sencillos de Wikipedia o de imágenes,
    la página actual cumple razonablemente el objetivo del sub-goal.
    No intenta cubrir todos los casos complejos.
    
    v1.4.5: Helper para early-stop por sub-objetivo.
    v2.0.0: Refactored to use pluggable context strategies.
    v2.1.0: Accepts context_strategies parameter for per-request strategy selection.
    """
    if not observation or not observation.url:
        return False

    # v2.1.0: Usar estrategias proporcionadas o DEFAULT_CONTEXT_STRATEGIES
    strategies = context_strategies if context_strategies is not None else DEFAULT_CONTEXT_STRATEGIES

    # v2.0.0: Usar estrategias de contexto por dominio
    for strategy in strategies:
        if strategy.goal_applies(goal, focus_entity):
            return strategy.is_goal_satisfied(goal, observation, focus_entity)

    # Si ninguna estrategia aplica, el objetivo no está satisfecho
    return False


async def _execute_action(action: BrowserAction, browser: BrowserController) -> Optional[str]:
    """
    Executes a BrowserAction on the BrowserController.
    Returns None if successful, or an error message string if it failed.
    """
    try:
        if action.type == "open_url":
            url = action.args.get("url", "")
            if url:
                await browser.goto(url)
        elif action.type == "click_text":
            text = action.args.get("text", "")
            if text:
                await browser.click_by_text(text)
        elif action.type == "fill_input":
            # Use Playwright directly to fill by selector
            selector = action.args.get("selector", "")
            text = action.args.get("text", "")
            if selector and text and browser.page:
                try:
                    locator = browser.page.locator(selector).first
                    await locator.click(timeout=2000)
                    await locator.fill(text)
                except Exception as e:
                    return f"Failed to fill input with selector '{selector}': {str(e)}"
            elif text:
                # Fallback to type_text if no selector
                await browser.type_text(text)
        elif action.type == "press_key":
            key = action.args.get("key", "Enter")
            if key == "Enter":
                await browser.press_enter()
            elif browser.page:
                await browser.page.keyboard.press(key)
        elif action.type == "accept_cookies":
            await browser.accept_cookies()
        elif action.type == "wait":
            # No artificial sleeps, but we can wait for network idle
            if browser.page:
                try:
                    await browser.page.wait_for_load_state("networkidle", timeout=2000)
                except Exception:
                    pass  # Ignore timeout
        elif action.type == "noop":
            # No operation, just continue
            pass
        elif action.type == "upload_file":
            # v2.3.0: Upload de archivo (normalmente manejado por _maybe_execute_file_upload)
            # Esta acción puede ser ejecutada directamente si el LLM la elige
            file_path = action.args.get("file_path", "")
            selector = action.args.get("selector", "input[type='file']")
            try:
                await browser.upload_file(selector, file_path)
            except Exception as e:
                return f"Error uploading file: {e}"
        else:
            return f"Unknown action type: {action.type}"
        return None
    except Exception as exc:
        return str(exc)


async def run_simple_agent(
    goal: str,
    browser: BrowserController,
    max_steps: int = 5,
) -> List[StepResult]:
    """
    Runs a very simple, synchronous-looking agent loop on top of the
    BrowserController using the SimplePlanner.
    """
    planner = SimplePlanner()
    steps: List[StepResult] = []
    action_history: List[BrowserAction] = []

    for step_index in range(max_steps):
        try:
            # Get observation
            observation = await browser.get_observation()

            # Ask planner for next action (pass action history)
            action = planner.next_action(
                goal=goal,
                observation=observation,
                step_index=step_index,
                action_history=action_history
            )

            # If stop action, add final step and break
            if action.type == "stop":
                steps.append(StepResult(
                    observation=observation,
                    last_action=action,
                    error=None
                ))
                break

            # Execute the action
            error = await _execute_action(action, browser)

            # If there was an error, add step with error and break
            if error:
                steps.append(StepResult(
                    observation=observation,
                    last_action=action,
                    error=error
                ))
                break

            # Add action to history (only if it was executed successfully)
            action_history.append(action)

            # Get a new observation after the action
            try:
                observation_after = await browser.get_observation()
            except Exception:
                # If we can't get a new observation, use the previous one
                observation_after = observation

            # Add step result
            steps.append(StepResult(
                observation=observation_after,
                last_action=action,
                error=None
            ))

        except Exception as exc:
            # If we can't even get an observation, create a step with error
            try:
                observation = await browser.get_observation()
            except Exception:
                # Create a minimal observation if we can't get one
                from backend.shared.models import BrowserObservation
                observation = BrowserObservation(
                    url="",
                    title="",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[]
                )
            
            steps.append(StepResult(
                observation=observation,
                last_action=None,
                error=f"Failed to execute step {step_index}: {str(exc)}"
            ))
            break

    return steps


async def run_llm_agent(
    goal: str,
    browser: BrowserController,
    max_steps: int = 8,
    focus_entity: Optional[str] = None,
    reset_context: bool = False,
    execution_profile: Optional[ExecutionProfile] = None,
) -> List[StepResult]:
    """
    Runs an agent loop on top of BrowserController using the LLMPlanner.
    v1.5.0: Calcula métricas de ejecución y las añade a StepResult.info["metrics_subgoal"].
    v1.9.0: Acepta ExecutionProfile para controlar el comportamiento.
    """
    planner = LLMPlanner()
    steps: List[StepResult] = []
    
    # v1.9.0: Usar perfil si está disponible, sino usar default
    if execution_profile is None:
        execution_profile = ExecutionProfile.default()
    
    # v1.9.0: Aplicar max_steps del perfil si está definido
    effective_max_steps = execution_profile.get_effective_max_steps(max_steps)
    if effective_max_steps != max_steps:
        logger.debug(f"[profile] using max_steps={effective_max_steps} from profile (default was {max_steps})")
    
    # v1.5.0: Iniciar medición de tiempo
    start_time = time.monotonic()
    
    # v1.4: Calcular focus_entity si no se proporciona
    if focus_entity is None:
        focus_entity = _extract_focus_entity_from_goal(goal)

    # v1.4.7: Reordenar flujo de early-stop para evitar doble carga
    # 1) Observación inicial sin tocar nada
    early_stop_reason: Optional[str] = None
    try:
        initial_observation = await browser.get_observation()
        
        # Si reset_context, ignorar la observación inicial para forzar navegación
        if reset_context:
            initial_observation = None
        
        # 2) Early-stop con el estado inicial (antes de ensure_context)
        if initial_observation and _goal_is_satisfied(goal, initial_observation, focus_entity, context_strategies=context_strategies):
            logger.info(
                "[early-stop] goal satisfied on initial page goal=%r focus_entity=%r url=%r title=%r",
                goal,
                focus_entity,
                initial_observation.url if initial_observation else None,
                initial_observation.title if initial_observation else None,
            )
            early_stop_reason = EarlyStopReason.GOAL_SATISFIED_ON_INITIAL_PAGE
            steps.append(StepResult(
                observation=initial_observation,
                last_action=None,
                error=None,
                info={
                    "reason": early_stop_reason,
                    "focus_entity": focus_entity,
                }
            ))
            # v1.5.0: Añadir métricas antes de retornar
            elapsed = time.monotonic() - start_time
            _add_metrics_to_steps(steps, goal, focus_entity, len(steps), early_stop_reason, elapsed, success=True)
            return steps
        
        # 3) Si no está satisfecho, entonces y solo entonces llamamos ensure_context
        reorientation_action = await ensure_context(goal, initial_observation, browser, focus_entity=focus_entity, context_strategies=context_strategies)
        
        if reorientation_action:
            # Ejecutar reorientación
            error = await _execute_action(reorientation_action, browser)
            if not error:
                # Obtener nueva observación después de reorientación
                try:
                    initial_observation = await browser.get_observation()
                    steps.append(StepResult(
                        observation=initial_observation,
                        last_action=reorientation_action,
                        error=None,
                        info={}
                    ))
                except Exception:
                    # Si no podemos obtener observación, usar la anterior
                    pass
        
        # 4) Early-stop tras ensure_context, antes del primer paso del LLM
        # v1.4.8: Asegurar que se ejecuta siempre con focus_entity correcto
        if initial_observation and _goal_is_satisfied(goal, initial_observation, focus_entity, context_strategies=context_strategies):
            logger.info(
                "[early-stop] goal satisfied after ensure_context before LLM "
                "goal=%r focus_entity=%r url=%r title=%r",
                goal,
                focus_entity,
                initial_observation.url if initial_observation else None,
                initial_observation.title if initial_observation else None,
            )
            # Actualizar el último step con la razón
            early_stop_reason = EarlyStopReason.GOAL_SATISFIED_AFTER_ENSURE_CONTEXT_BEFORE_LLM
            if steps:
                last_step = steps[-1]
                info = dict(last_step.info or {})
                info["reason"] = early_stop_reason
                if focus_entity:
                    info["focus_entity"] = focus_entity
                last_step.info = info
            # v1.5.0: Añadir métricas antes de retornar
            elapsed = time.monotonic() - start_time
            _add_metrics_to_steps(steps, goal, focus_entity, len(steps), early_stop_reason, elapsed, success=True)
            return steps
        
        # v1.4.8: Logging defensivo para imágenes no satisfechas
        if _goal_mentions_images(goal) and initial_observation and not _goal_is_satisfied(goal, initial_observation, focus_entity, context_strategies=context_strategies):
            logger.debug(
                "[image-goal] not satisfied yet goal=%r focus_entity=%r url=%r title=%r",
                goal,
                focus_entity,
                initial_observation.url if initial_observation else None,
                initial_observation.title if initial_observation else None,
            )
    except Exception:
        # Si hay error obteniendo la observación inicial, continuar con el bucle normal
        pass

    for step_idx in range(effective_max_steps):
        try:
            # Get observation
            observation = await browser.get_observation()
            
            # v1.4: Si reset_context es True y es el primer paso, ignorar la observación actual
            # para forzar navegación a nuevo contexto
            if reset_context and step_idx == 0:
                observation = None

            # v1.4.1: Context reorientation layer: solo al inicio del sub-objetivo
            # v1.4.6: Si ya hicimos reorientación antes del bucle (steps no está vacío),
            # no volver a hacerla en step_idx == 0 para evitar duplicación
            reorientation_action = None
            if step_idx == 0 or observation is None:
                # v1.4.6: Solo reorientar si no se hizo antes del bucle
                # (si steps está vacío al entrar al bucle, significa que no se hizo reorientación previa)
                if len(steps) == 0 or step_idx > 0:
                    reorientation_action = await ensure_context(goal, observation, browser, focus_entity=focus_entity, context_strategies=context_strategies)
            
            if reorientation_action:
                # Execute reorientation action immediately
                error = await _execute_action(reorientation_action, browser)
                if error:
                    # If reorientation failed, add error step and continue anyway
                    steps.append(StepResult(
                        observation=observation,
                        last_action=reorientation_action,
                        error=f"Failed to reorient context: {error}",
                        info={}
                    ))
                else:
                    # Get new observation after reorientation
                    try:
                        observation = await browser.get_observation()
                        steps.append(StepResult(
                            observation=observation,
                            last_action=reorientation_action,
                            error=None,
                            info={}
                        ))
                        
                        # v1.4.5: early-stop después de reorientación si el objetivo ya está satisfecho
                        if _goal_is_satisfied(goal, observation, focus_entity, context_strategies=context_strategies):
                            early_stop_reason = EarlyStopReason.GOAL_SATISFIED_AFTER_REORIENTATION
                            logger.info(
                                "[early-stop] goal satisfied after reorientation for goal=%r focus_entity=%r step_idx=%d url=%r title=%r",
                                goal,
                                focus_entity,
                                step_idx,
                                observation.url if observation else None,
                                observation.title if observation else None,
                            )
                            break
                    except Exception:
                        # If we can't get observation, continue with previous one
                        pass
                
                # IMPORTANT: After reorientation, continue loop without consulting LLMPlanner
                # This ensures we don't skip the reorientation step
                # v1.5: Pero si el objetivo ya está satisfecho, salimos del bucle
                if observation and _goal_is_satisfied(goal, observation, focus_entity, context_strategies=context_strategies):
                    early_stop_reason = EarlyStopReason.GOAL_SATISFIED_AFTER_REORIENTATION
                    break
                continue

            # Ask planner for next action
            action = await planner.next_action(
                goal=goal,
                observation=observation,
                history=steps
            )

            # BLOCK STOP if obligatory context is not met
            # If goal requires Wikipedia and we're not in Wikipedia, ignore STOP and force reorientation
            if action.type == "stop":
                if _goal_requires_wikipedia(goal) and not _is_url_in_wikipedia(observation.url):
                    # Ignore STOP action - force reorientation instead
                    # v1.3: Pasar focus_entity a ensure_context
                    reorientation_action = await ensure_context(goal, observation, browser, focus_entity=focus_entity, context_strategies=context_strategies)
                    if reorientation_action:
                        # Execute reorientation action
                        error = await _execute_action(reorientation_action, browser)
                        if error:
                            steps.append(StepResult(
                                observation=observation,
                                last_action=reorientation_action,
                                error=f"Failed to reorient context: {error}",
                                info={}
                            ))
                        else:
                            try:
                                observation = await browser.get_observation()
                                steps.append(StepResult(
                                    observation=observation,
                                    last_action=reorientation_action,
                                    error=None,
                                    info={}
                                ))
                            except Exception:
                                pass
                        # Continue loop without accepting STOP
                        continue

            # If stop action (and context is OK), add final step and break
            if action.type == "stop":
                steps.append(StepResult(
                    observation=observation,
                    last_action=action,
                    error=None,
                    info={}
                ))
                break

            # Execute the action
            try:
                error = await _execute_action(action, browser)
            except Exception as exc:
                # If there was an exception executing the action
                steps.append(StepResult(
                    observation=observation,
                    last_action=action,
                    error=str(exc),
                    info={}
                ))
                break

            # If there was an error, add step with error and break
            if error:
                steps.append(StepResult(
                    observation=observation,
                    last_action=action,
                    error=error,
                    info={}
                ))
                break

            # Get a new observation after the action
            try:
                observation_after = await browser.get_observation()
            except Exception:
                # If we can't get a new observation, use the previous one
                observation_after = observation

            # v3.2.0: Confirmación visual para acciones críticas
            visual_confirmation = None
            if action.type == "click_text":
                clicked_text = action.args.get("text", "").lower()
                # Botones críticos que requieren confirmación visual
                critical_buttons = ["guardar", "enviar", "confirmar", "aceptar", "finalizar", "guardar cambios"]
                if any(btn in clicked_text for btn in critical_buttons):
                    from backend.shared.models import VisualActionResult
                    visual_confirmation = _verify_action_visually(
                        observation=observation_after,
                        expected_effect=f"Confirmar que el botón '{action.args.get('text', '')}' ha tenido efecto",
                        keywords=[
                            "guardado", "guardado correctamente", "guardado con éxito",
                            "enviado", "enviado correctamente", "enviado con éxito",
                            "confirmado", "confirmado correctamente", "confirmado con éxito",
                            "aceptado", "aceptado correctamente", "aceptado con éxito",
                            "finalizado", "finalizado correctamente", "finalizado con éxito",
                            "cambios guardados", "datos guardados", "información guardada",
                            "saved", "saved successfully", "changes saved",
                            "sent", "sent successfully", "submitted",
                        ],
                    )
                    visual_confirmation.action_type = "click"
                    logger.debug(
                        "[visual-confirmation] Critical button clicked: text=%r confirmed=%r confidence=%.2f",
                        action.args.get("text", ""), visual_confirmation.confirmed, visual_confirmation.confidence
                    )

            # Add step result
            step_info = {}
            if visual_confirmation:
                step_info["visual_confirmation"] = visual_confirmation.model_dump()
            
            steps.append(StepResult(
                observation=observation_after,
                last_action=action,
                error=None,
                info=step_info
            ))
            
            # v1.4.5: early-stop cuando el sub-objetivo actual ya está satisfecho
            if _goal_is_satisfied(goal, observation_after, focus_entity, context_strategies=context_strategies):
                early_stop_reason = EarlyStopReason.GOAL_SATISFIED_AFTER_ACTION
                logger.info(
                    "[early-stop] goal satisfied for goal=%r focus_entity=%r step_idx=%d url=%r title=%r",
                    goal,
                    focus_entity,
                    step_idx,
                    observation_after.url if observation_after else None,
                    observation_after.title if observation_after else None,
                )
                break

        except Exception as exc:
            # If we can't even get an observation, create a step with error
            try:
                observation = await browser.get_observation()
            except Exception:
                # Create a minimal observation if we can't get one
                from backend.shared.models import BrowserObservation
                observation = BrowserObservation(
                    url="",
                    title="",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[]
                )
            
            steps.append(StepResult(
                observation=observation,
                last_action=None,
                error=f"Failed to execute step: {str(exc)}",
                info={}
            ))
            break

    # v1.5.0: Calcular métricas finales y añadirlas al último step
    elapsed = time.monotonic() - start_time
    steps_taken = len(steps)
    
    # Determinar si fue exitoso: True si terminó con early-stop por objetivo cumplido
    success = early_stop_reason is not None and early_stop_reason.startswith("goal_satisfied")
    
    # Si no hay early_stop_reason y llegamos aquí, puede ser:
    # - max_steps alcanzado
    # - error
    # - stop action sin early-stop
    if early_stop_reason is None:
        # Verificar si el último step tiene error
        if steps and steps[-1].error:
            early_stop_reason = None  # Error
        elif steps_taken >= effective_max_steps:
            early_stop_reason = None  # Max steps alcanzado (usando effective_max_steps del perfil)
        else:
            early_stop_reason = None  # Stop action normal
    
    # v1.9.0: Añadir información del perfil a las métricas
    if steps:
        last_step = steps[-1]
        if last_step.info is None:
            last_step.info = {}
        else:
            last_step.info = dict(last_step.info)
        last_step.info["execution_profile"] = execution_profile.to_dict()
    
    _add_metrics_to_steps(steps, goal, focus_entity, steps_taken, early_stop_reason, elapsed, success)
    
    return steps


SYSTEM_PROMPT_ANSWER = (
    "Eres el agente de respuesta de CometLocal.\n"
    "Has navegado por la web con otro componente y ahora recibes:\n"
    "- el objetivo original del usuario,\n"
    "- el contenido textual visible de la última página,\n"
    "- y opcionalmente la URL y el título.\n"
    "Debes responder al usuario en español, de forma clara y resumida,\n"
    "usando SOLO la información disponible en el texto y el objetivo.\n\n"
    "INSTRUCCIONES ESPECÍFICAS:\n"
    "✅ Prioriza Wikipedia para objetivos tipo 'quién fue X' o 'información sobre X'.\n"
    "✅ Prioriza búsqueda de imágenes cuando el objetivo lo indique explícitamente.\n"
    "❌ No rechaces responder solo porque haya ruido en el histórico.\n"
    "✅ Explica explícitamente qué fuente estás usando.\n"
    "✅ Usa lo mejor disponible incluso si no es perfecto.\n"
    "❌ Solo di 'no encontré información' si realmente no hay fuentes útiles.\n\n"
    "IMPORTANTE: No debes bloquear la respuesta por la presencia de páginas menos relevantes.\n"
    "Debes centrarte únicamente en las fuentes pertinentes al objetivo actual.\n\n"
    "Si la URL indica que estás en una página de resultados de imágenes "
    "(por ejemplo, contiene 'ia=images' o 'iax=images' o es una búsqueda de imágenes),\n"
    "explica que has encontrado resultados de imágenes relacionados con el objetivo, "
    "y describe brevemente qué tipo de imágenes se muestran basándote en el texto visible.\n"
    "Si la página no es relevante o no hay información útil, explícalo."
)


def _decompose_goal(goal: str) -> List[str]:
    """
    Descomposición de un objetivo en sub-objetivos ordenados.
    
    v1.4.4: Mejorado para reconocer múltiples conectores secuenciales y devolver
    sub-goals limpios sin arrastrar partes de otros sub-objetivos.
    
    Reglas:
    - Si no detecta conectores, devuelve [goal] tal cual.
    - Divide recursivamente por múltiples conectores secuenciales.
    - Si el objetivo original menciona "wikipedia" y alguna parte no la
      menciona, se añade " en Wikipedia" a esa parte.
    - Limpia espacios y signos de puntuación sobrantes en los extremos.
    """
    text = " ".join(goal.strip().split())
    lower = text.lower()
    
    # v1.4.4: Lista ampliada de conectores secuenciales
    CONNECTORS = [
        " y luego ",
        " y después ",
        " y despues ",
        ", luego ",
        "; luego ",
        ", después ",
        ", despues ",
        "; después ",
        "; despues ",
        " y finalmente ",
        ", y finalmente ",
        "; y finalmente ",
    ]
    
    # v1.4.4: Buscar todos los conectores y sus posiciones
    connector_positions = []
    for connector in CONNECTORS:
        start = 0
        while True:
            idx = lower.find(connector, start)
            if idx == -1:
                break
            connector_positions.append((idx, idx + len(connector), len(connector), connector))
            start = idx + 1
    
    # Si no hay conectores, devolver el objetivo tal cual
    if not connector_positions:
        sub_goals = [text] if text else []
    else:
        # Ordenar por posición de inicio
        connector_positions.sort(key=lambda x: x[0])
        
        # v1.4.4: Filtrar solapamientos (si un conector está dentro de otro, mantener solo el más largo)
        filtered_positions = []
        for i, (start, end, length, connector) in enumerate(connector_positions):
            # Verificar si este conector se solapa con alguno ya añadido
            overlaps = False
            for prev_start, prev_end, _, _ in filtered_positions:
                # Si se solapa (inicio dentro del rango anterior o fin dentro del rango anterior)
                if (prev_start <= start < prev_end) or (prev_start < end <= prev_end):
                    overlaps = True
                    break
            if not overlaps:
                filtered_positions.append((start, end, length, connector))
        
        # Ordenar de nuevo por posición de inicio
        filtered_positions.sort(key=lambda x: x[0])
        
        # Dividir el texto por los conectores encontrados
        sub_goals = []
        start = 0
        
        for pos_start, pos_end, length, connector in filtered_positions:
            # Extraer la parte antes del conector
            part = text[start:pos_start].strip()
            if part:
                sub_goals.append(part)
            start = pos_end
        
        # Añadir la parte final
        if start < len(text):
            part = text[start:].strip()
            if part:
                sub_goals.append(part)
    
    # v1.4.4: Limpiar cada sub-goal
    cleaned_sub_goals = []
    for sub in sub_goals:
        # Limpiar espacios y signos de puntuación residuales
        sub = sub.strip()
        sub = sub.strip(" ,.;")
        if sub:  # Ignorar sub-goals vacíos
            cleaned_sub_goals.append(sub)
    
    if not cleaned_sub_goals:
        return [text] if text else []
    
    # Propagar contexto de Wikipedia:
    # Si el objetivo global menciona "wikipedia" y una parte no lo menciona,
    # añade " en Wikipedia" a esa parte.
    # EXCEPCIÓN v1.2: NO propagar "en Wikipedia" a sub-goals que mencionen imágenes
    if "wikipedia" in lower:
        new_parts: List[str] = []
        for p in cleaned_sub_goals:
            if "wikipedia" not in p.lower():
                # v1.2: Si el sub-goal menciona imágenes, NO añadir "en Wikipedia"
                if not _goal_mentions_images(p):
                    p = p + " en Wikipedia"
            new_parts.append(p)
        cleaned_sub_goals = new_parts
    
    # v1.4.4: Logging para depuración
    logger.info(
        "[decompose_goal] goal=%r -> sub_goals=%r",
        goal,
        cleaned_sub_goals,
    )
    
    return cleaned_sub_goals


def decompose_goal(goal: str) -> List[str]:
    """
    Divide un objetivo en sub-objetivos secuenciales usando conectores simples.
    Devuelve una lista ordenada de strings, uno por cada sub-objetivo.
    """
    # Conectores que indican secuencia
    connectors = [
        " y luego ",
        " luego ",
        " después ",
        " y después ",
        " and then ",
    ]
    
    # Buscar el primer conector que aparezca
    goal_lower = goal.lower()
    found_connector = None
    found_index = -1
    
    for connector in connectors:
        index = goal_lower.find(connector)
        if index != -1 and (found_index == -1 or index < found_index):
            found_connector = connector
            found_index = index
    
    # Si no hay conector, devolver el goal original
    if found_connector is None:
        return [goal.strip()]
    
    # Dividir por el conector encontrado
    parts = goal.split(found_connector, 1)
    first_part = parts[0].strip()
    rest = parts[1].strip() if len(parts) > 1 else ""
    
    # Si hay más partes, descomponer recursivamente
    if rest:
        sub_goals = [first_part] + decompose_goal(rest)
    else:
        sub_goals = [first_part]
    
    # Filtrar partes vacías y devolver
    return [sg for sg in sub_goals if sg]


def normalize_subgoal(sub_goal: str) -> str:
    """
    Normaliza un sub-objetivo humano a una forma más útil para navegación.
    
    Elimina verbos y frases guía comunes al principio del texto,
    preservando el contenido esencial y la mención a Wikipedia si existe.
    """
    # Trabajar sobre una copia
    result = sub_goal.strip()
    if not result:
        return sub_goal
    
    # Verificar si contiene "wikipedia" (para preservarlo después)
    original_lower = sub_goal.lower()
    has_wikipedia = "wikipedia" in original_lower
    
    # Prefijos a eliminar (en orden de más específico a menos específico)
    prefixes = [
        "investiga quién fue ",
        "investigar quién fue ",
        "investiga ",
        "investigar ",
        "quién fue ",
        "mira información sobre ",
        "mira ",
        "buscar información sobre ",
        "busca información sobre ",
        "buscar ",
        "busca ",
        "consulta ",
        "averigua ",
        "infórmate sobre ",
    ]
    
    # Intentar eliminar prefijos
    lower_result = result.lower()
    for prefix in prefixes:
        if lower_result.startswith(prefix):
            result = result[len(prefix):].strip()
            break
    
    # Eliminar "sobre " al inicio si quedó después de eliminar prefijos
    if result.lower().startswith("sobre "):
        result = result[6:].strip()
    
    # Si el resultado quedó vacío, devolver el original
    if not result:
        return sub_goal.strip()
    
    # Caso especial: preservar "en Wikipedia" si estaba en el original
    if has_wikipedia and "wikipedia" not in result.lower():
        result = f"{result} en Wikipedia"
    
    return result


async def _process_single_subgoal(
    raw_sub_goal: str,
    browser: BrowserController,
    max_steps: int,
) -> tuple[List[StepResult], Optional[BrowserObservation], str]:
    """
    Procesa un sub-objetivo individual:
    - Normaliza el sub-objetivo para navegación
    - Navega a Wikipedia si es necesario
    - Ejecuta el agente LLM con el objetivo normalizado
    - Genera una respuesta parcial usando el objetivo original
    Devuelve (steps, last_observation, partial_answer)
    """
    # Normalizar el sub-objetivo para navegación
    navigation_goal = normalize_subgoal(raw_sub_goal)
    
    steps: List[StepResult] = []

    # Orientación dura a Wikipedia si el sub-objetivo normalizado lo pide
    text_lower = navigation_goal.lower()
    if "wikipedia" in text_lower:
        cleanup_phrases = [
            "en wikipedia en español",
            "en la wikipedia en español",
            "en wikipedia",
            "en la wikipedia",
        ]
        query_text = navigation_goal
        for phrase in cleanup_phrases:
            query_text = query_text.replace(phrase, "")
        query_text = query_text.strip() or navigation_goal.strip()

        search_param = quote_plus(query_text)
        wikipedia_url = f"https://es.wikipedia.org/wiki/Especial:Buscar?search={search_param}"

        forced_action = BrowserAction(type="open_url", args={"url": wikipedia_url})

        try:
            error = await _execute_action(forced_action, browser)
            if error:
                try:
                    current_obs = await browser.get_observation()
                except Exception:
                    from backend.shared.models import BrowserObservation
                    current_obs = BrowserObservation(
                        url="",
                        title="",
                        visible_text_excerpt="",
                        clickable_texts=[],
                        input_hints=[]
                    )
                steps.append(
                    StepResult(
                        observation=current_obs,
                        last_action=forced_action,
                        error=error,
                        info={"phase": "forced_wikipedia_error"},
                    )
                )
            else:
                obs = await browser.get_observation()
                steps.append(
                    StepResult(
                        observation=obs,
                        last_action=forced_action,
                        error=None,
                        info={"phase": "forced_wikipedia"},
                    )
                )
        except Exception as exc:  # pragma: no cover - defensivo
            try:
                current_obs = await browser.get_observation()
            except Exception:
                from backend.shared.models import BrowserObservation
                current_obs = BrowserObservation(
                    url="",
                    title="",
                    visible_text_excerpt="",
                    clickable_texts=[],
                    input_hints=[]
                )
            steps.append(
                StepResult(
                    observation=current_obs,
                    last_action=forced_action,
                    error=str(exc),
                    info={"phase": "forced_wikipedia_error"},
                )
            )

    # Ejecutar el agente LLM para este sub-objetivo (usando el objetivo normalizado)
    # v1.9.0: Nota: ensure_context no tiene acceso a execution_profile, usa default
    try:
        more_steps = await run_llm_agent(goal=navigation_goal, browser=browser, max_steps=max_steps, execution_profile=None)
        steps.extend(more_steps)
    except Exception as exc:  # pragma: no cover - defensivo
        # Si falla, continuamos con los pasos que tengamos
        pass

    # Obtener la última observación de este sub-objetivo
    last_observation: Optional[BrowserObservation] = None
    for step in reversed(steps):
        if step.observation is not None:
            last_observation = step.observation
            break

    # Generar respuesta parcial
    partial_answer = ""
    if last_observation:
        url = last_observation.url or ""
        title = last_observation.title or ""
        visible = last_observation.visible_text_excerpt or ""

        system_prompt = SYSTEM_PROMPT_ANSWER
        user_prompt = (
            f"Sub-objetivo original del usuario:\n{raw_sub_goal}\n\n"
            f"Objetivo normalizado para la navegación: '{navigation_goal}'\n\n"
            f"URL visitada:\n{url}\n\n"
            f"Título de la página:\n{title}\n\n"
            "Contenido de la página (extracto del texto visible):\n"
            f"{visible}\n\n"
            "Responde brevemente a este sub-objetivo en español."
        )

        client = AsyncOpenAI(base_url=LLM_API_BASE, api_key=LLM_API_KEY)
        try:
            response = await client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            partial_answer = response.choices[0].message.content or ""
        except Exception as exc:  # pragma: no cover - defensivo
            partial_answer = f"No he podido generar una respuesta para este sub-objetivo. Detalle: {exc}"
    else:
        partial_answer = f"No he podido obtener información para: {raw_sub_goal}"

    return steps, last_observation, partial_answer


def _is_wikipedia_search_url(url: Optional[str]) -> bool:
    """
    Devuelve True si la URL es una página de búsqueda de Wikipedia.
    """
    if not url:
        return False
    url_lower = url.lower()
    return (
        "wikipedia.org/wiki/especial:buscar" in url_lower
        or "/w/index.php?search=" in url_lower
    )


def _get_effective_focus_entity(goal: str, focus_entity: Optional[str]) -> Optional[str]:
    """
    Devuelve la entidad a usar para búsquedas / artículos de Wikipedia.
    
    Prioridad:
    1) focus_entity explícito (propagado por run_llm_task_with_answer)
    2) entidad extraída del goal con _extract_focus_entity_from_goal
    3) en caso contrario, None (NO usar el goal literal como título)
    
    v1.4: Limpia palabras conectoras al inicio (de, del, la, el) de la entidad.
    """
    def clean_entity(entity: str) -> str:
        """Limpia palabras conectoras al inicio de la entidad."""
        entity = entity.strip()
        # Palabras conectoras que pueden aparecer al inicio
        connectors = ["de ", "del ", "la ", "el ", "y ", "en "]
        for connector in connectors:
            if entity.lower().startswith(connector):
                entity = entity[len(connector):].strip()
        return entity
    
    if focus_entity:
        cleaned = clean_entity(focus_entity)
        return cleaned if cleaned else None
    
    inferred = _extract_focus_entity_from_goal(goal)
    if inferred:
        cleaned = clean_entity(inferred)
        return cleaned if cleaned else None
    
    return None


def _normalize_wikipedia_query(goal: str, focus_entity: Optional[str] = None) -> Optional[str]:
    """
    Devuelve la query de Wikipedia, siempre basada en una entidad corta,
    nunca en una frase literal.
    
    Prioridad:
    1) focus_entity (ya normalizada por quien llama)
    2) _extract_focus_entity_from_goal(goal)
    3) None si no se puede inferir nada razonable
    """
    effective = _get_effective_focus_entity(goal, focus_entity)
    return effective


def build_execution_plan(
    goal: str,
    sub_goals: List[str],
    execution_profile: ExecutionProfile,
    context_strategies: List[str],
    document_repository: Optional["DocumentRepository"],
) -> ExecutionPlan:
    """
    Construye un plan de ejecución estructurado antes de ejecutar.
    
    v2.8.0: Genera un plan determinista basado solo en:
    - goal y sub_goals
    - execution_profile
    - context_strategies
    - document_repository
    
    NO usa LLM ni navegador. Es puramente analítico.
    
    Args:
        goal: Objetivo principal
        sub_goals: Lista de sub-objetivos descompuestos
        execution_profile: Perfil de ejecución
        context_strategies: Lista de nombres de estrategias activas
        document_repository: Repositorio de documentos (opcional)
        
    Returns:
        ExecutionPlan con toda la información planificada
    """
    from backend.agents.file_upload import _maybe_build_file_upload_instruction
    from backend.agents.session_context import SessionContext
    import os
    
    planned_sub_goals: List[PlannedSubGoal] = []
    session_context = SessionContext()
    session_context.update_goal(goal)
    
    for idx, sub_goal in enumerate(sub_goals, start=1):
        # Inferir strategy
        strategy = "other"
        sub_goal_lower = sub_goal.lower()
        
        if "cae" in sub_goal_lower or "documentación cae" in sub_goal_lower or "documentacion cae" in sub_goal_lower:
            strategy = "cae"
        elif _goal_mentions_images(sub_goal):
            strategy = "images"
        elif _goal_mentions_wikipedia(sub_goal):
            strategy = "wikipedia"
        
        # Inferir expected_actions
        expected_actions = ["navigate"]
        
        # Detectar intención de upload
        upload_keywords = [
            "sube", "subir", "adjunta", "adjuntar",
            "sube el", "sube la", "sube un", "sube una",
            "adjunta el", "adjunta la", "adjunta un", "adjunta una",
            "subir documento", "subir documentación", "adjuntar documento", "adjuntar documentación",
        ]
        has_upload_intent = any(keyword in sub_goal_lower for keyword in upload_keywords)
        
        if has_upload_intent:
            expected_actions.append("upload_file")
            expected_actions.append("verify_upload")
        
        # Inferir documents_needed
        documents_needed: List[str] = []
        
        if has_upload_intent and document_repository:
            try:
                # Extraer focus_entity del sub-goal
                focus_entity = _extract_focus_entity_from_goal(sub_goal)
                
                # Intentar construir instrucción de upload (modo análisis)
                upload_instruction = _maybe_build_file_upload_instruction(
                    goal=sub_goal,
                    focus_entity=focus_entity,
                    session_context=session_context,
                    document_repository=document_repository,
                )
                
                if upload_instruction and upload_instruction.path:
                    # Solo el nombre del archivo, no el path completo
                    file_name = os.path.basename(upload_instruction.path)
                    documents_needed.append(file_name)
            except Exception as e:
                logger.debug(f"[execution-plan] Error detecting documents for sub-goal {idx}: {e}")
        
        # Determinar may_retry
        # v2.6.0: Retry está habilitado por defecto, pero puede estar deshabilitado en el perfil
        may_retry = True  # Por defecto, los retries están habilitados
        
        planned_sub_goal = PlannedSubGoal(
            index=idx,
            sub_goal=sub_goal,
            strategy=strategy,
            expected_actions=expected_actions,
            documents_needed=documents_needed,
            may_retry=may_retry,
        )
        planned_sub_goals.append(planned_sub_goal)
    
    # Construir ExecutionPlan
    plan = ExecutionPlan(
        goal=goal,
        execution_profile=execution_profile.to_dict(),
        context_strategies=context_strategies,
        sub_goals=planned_sub_goals,
    )
    
    return plan


def _normalize_text_for_comparison(s: str) -> str:
    """
    Normaliza texto para comparación robusta (case-insensitive, sin diacríticos).
    v1.4.8: Helper para comparaciones en _goal_is_satisfied.
    """
    if not s:
        return ""
    # Pasar a minúsculas
    normalized = s.lower()
    # Eliminar diacríticos usando unicodedata
    normalized = unicodedata.normalize('NFD', normalized)
    normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    # Recortar espacios extra
    normalized = ' '.join(normalized.split())
    return normalized


def _build_image_search_query(goal: str, focus_entity: Optional[str]) -> str:
    """
    Construye una query limpia para búsquedas de imágenes.
    
    Reglas:
    - Si hay focus_entity: devolver "imágenes de {focus_entity}" (idioma español).
    - Si no hay focus_entity:
        - eliminar verbos tipo "muéstrame", "muestrame", "enséñame", "enseñame", "búscame", "pon", etc.
        - eliminar pronombres tipo "suyas", "suyos", "de él", "de ella"
        - convertir "fotos" a "imágenes"
        - devolver algo razonable, sin verbos imperativos.
    
    v1.4.7: Helper para normalizar queries de imágenes y evitar literales del goal.
    v1.4.8: Mejorado para cubrir más variantes de lenguaje natural en español.
    """
    # v1.4.8: Si hay focus_entity -> SIEMPRE usarla (prioridad absoluta)
    if focus_entity and focus_entity.strip():
        return f"imágenes de {focus_entity.strip()}".strip()
    
    # v1.4.8: Si no hay focus_entity, limpiar el goal de forma exhaustiva
    text = goal.strip()
    lower = text.lower()
    
    # v1.4.8: Convertir "fotos" a "imágenes" antes de procesar
    text = re.sub(r"\bfotos?\b", "imágenes", text, flags=re.IGNORECASE)
    text = re.sub(r"\bfotografías?\b", "imágenes", text, flags=re.IGNORECASE)
    
    # v1.4.8: Eliminar verbos imperativos ampliados (con y sin tilde)
    verbs = [
        "muéstrame", "muestrame", "muestra", "muestras", "muestren", "muestrenme",
        "enséñame", "enseñame", "ensename", "enseña", "enseñas", "enseñen", "enseñenme",
        "mira", "mirar", "ver", "veo", "vemos",
        "busca", "buscar", "búscame", "buscame", "buscas", "buscan",
        "pon", "ponme", "poner",
        "dame", "dar", "quiero ver", "quiero",
    ]
    for verb in verbs:
        # Eliminar verbos al inicio o seguidos de espacio
        pattern = rf"\b{re.escape(verb)}\s*"
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    
    # v1.4.8: Eliminar pronombres y frases relacionadas de forma exhaustiva
    pronouns = [
        r"\bsuyas\b", r"\bsuyos\b", r"\bsuya\b", r"\bsuyo\b",
        r"\bde él\b", r"\bde ella\b", r"\bde ellos\b", r"\bde ellas\b",
        r"\bél\b", r"\bella\b", r"\bellos\b", r"\bellas\b",
        r"\bde mí\b", r"\bde ti\b", r"\bmí\b", r"\bti\b",
    ]
    for pronoun in pronouns:
        text = re.sub(pronoun, "", text, flags=re.IGNORECASE)
    
    # Limpiar espacios múltiples y puntuación
    text = re.sub(r"\s+", " ", text).strip(" ,.;:¡!¿?")
    
    # v1.4.8: Si tras limpiar no queda nada útil o solo quedan pronombres, devolver "imágenes"
    if not text or len(text.strip()) < 3:
        return "imágenes"
    
    # Verificar que no queden solo pronombres comunes
    remaining_lower = text.lower().strip()
    if remaining_lower in ["él", "ella", "ellos", "ellas", "mí", "ti", "suyas", "suyos"]:
        return "imágenes"
    
    # Si el texto es exactamente "imágenes" (o variantes), devolver directamente
    if remaining_lower in ["imágenes", "imagenes", "imagen"]:
        return "imágenes"
    
    # Asegurar que la query empieza por "imágenes" (solo si no empieza ya con "imagen")
    # Primero, eliminar cualquier "imágenes" duplicada al inicio
    text = re.sub(r"^imágenes\s+imágenes\s*", "imágenes ", text, flags=re.IGNORECASE)
    remaining_lower = text.lower().strip()
    
    # Verificar si ya empieza con "imágenes" (con o sin tilde)
    starts_with_imagenes = (
        remaining_lower.startswith("imágenes") or 
        remaining_lower.startswith("imagenes") or
        remaining_lower.startswith("imagen ")
    )
    
    if not starts_with_imagenes:
        # Si no empieza con "imagen", añadir el prefijo
        text = f"imágenes {text}"
    else:
        # Si ya empieza con "imágenes", asegurar que no haya duplicados
        text = re.sub(r"^imágenes\s+imágenes\s*", "imágenes ", text, flags=re.IGNORECASE)
    
    # v1.4.8: Verificación final - si aún contiene pronombres problemáticos, devolver solo "imágenes"
    problematic_patterns = [
        r"\bél\b", r"\bella\b", r"\bsuyas\b", r"\bsuyos\b",
        r"\bde él\b", r"\bde ella\b",
    ]
    for pattern in problematic_patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return "imágenes"
    
    return text.strip()


def _normalize_image_query(goal: str, fallback_focus: Optional[str] = None) -> str:
    """
    Normaliza la query para búsquedas de imágenes en DuckDuckGo.
    
    Prioridad:
    1. Si hay pronombres y fallback_focus -> usar siempre fallback_focus.
    2. Si hay fallback_focus -> usar fallback_focus.
    3. Entidad detectada en el propio goal.
    4. Goal limpiado de verbos imperativos comunes.
    
    v1.4: Evita duplicados "de de ..." y normaliza espacios.
    v1.4.2: Corrige uso de pronombres con fallback_focus.
    """
    text = goal.strip()
    lower = text.lower()
    
    # v1.4.2: Definir pronombres relevantes
    PRONOUN_TOKENS = [
        " su ", " sus ", " suyo", " suya", " suyos", " suyas",
        " él", " ella", " ellos", " ellas",
    ]
    
    # v1.4.2: Detectar si el objetivo contiene pronombres
    has_pronoun = any(token in f" {lower} " for token in PRONOUN_TOKENS)
    
    # v1.4.2: 1) Pronombres + focus_entity -> usar siempre la entidad
    if has_pronoun and fallback_focus:
        clean_entity = fallback_focus.strip()
        query = f"imágenes de {clean_entity}"
        # Normalizar duplicados "de de ..." y espacios múltiples
        query = query.replace("de de ", "de ")
        query = query.replace("  ", " ").strip()
        return query
    
    # v1.4.2: 2) Sin pronombres pero con focus_entity -> también preferir la entidad
    if fallback_focus:
        clean_entity = fallback_focus.strip()
        query = f"imágenes de {clean_entity}"
        # Normalizar duplicados "de de ..." y espacios múltiples
        query = query.replace("de de ", "de ")
        query = query.replace("  ", " ").strip()
        return query
    
    # 3) Entidad del propio sub-goal
    focus = _extract_focus_entity_from_goal(text)
    
    if focus:
        # Limpiar entidad de palabras conectoras
        clean_entity = focus.strip()
        # Construir query: siempre "imágenes de <entidad>"
        query = f"imágenes de {clean_entity}"
    else:
        # 4) Sin entidad clara: limpiar verbos imperativos típicos
        cleaned = re.sub(
            r"\b(muéstrame|muestrame|muestra|mira|ver|enséñame|enseñame|ensename|busca|buscar)\b",
            "",
            text,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:¡!¿?")
        query = cleaned or goal.strip()
    
    # v1.4: Normalizar duplicados "de de ..." y espacios múltiples
    query = query.replace("de de ", "de ")
    query = query.replace("  ", " ").strip()
    
    return query


def _extract_focus_entity_from_goal(goal: str, fallback_focus_entity: Optional[str] = None) -> Optional[str]:
    """
    Extrae la entidad principal del sub-goal (ej. 'Ada Lovelace', 'Charles Babbage').
    Usada solo para trazabilidad y control.
    
    v1.4: Si el sub-goal contiene pronombres y no se extrae entidad explícita,
    retorna fallback_focus_entity.
    """
    goal_lower = goal.lower()
    
    # v1.4: Detectar pronombres
    pronouns = ["su", "sus", "suyas", "suyos", "él", "ella", "le", "la", "lo"]
    has_pronoun = any(pronoun in goal_lower for pronoun in pronouns)
    
    # Buscar y recortar "en wikipedia" o "en la wikipedia"
    topic_part = goal
    for suffix in [" en wikipedia", " en la wikipedia"]:
        if goal_lower.endswith(suffix):
            topic_part = goal[:len(goal) - len(suffix)].strip()
            break
    
    # Si no encontramos el sufijo, usar todo el texto
    if topic_part == goal:
        topic_part = goal.strip()
    
    # Dividir en tokens
    tokens = topic_part.split()
    if not tokens:
        # v1.4: Si hay pronombre y no hay tokens, usar fallback
        if has_pronoun and fallback_focus_entity:
            return fallback_focus_entity
        return None
    
    # Recorrer desde el final hacia atrás, acumulando palabras capitalizadas
    accumulated = []
    short_connectors = {"de", "del", "la", "el", "y", "en"}
    
    for token in reversed(tokens):
        # Limpiar puntuación del token
        clean_token = token.strip(" ,;.")
        if not clean_token:
            continue
        
        # Si es una palabra corta conectora, la incluimos para no cortar apellidos compuestos
        if clean_token.lower() in short_connectors:
            accumulated.append(clean_token)
            continue
        
        # Si la primera letra es alfabética y mayúscula, es un nombre propio
        if clean_token[0].isalpha() and clean_token[0].isupper():
            accumulated.append(clean_token)
        else:
            # Si encontramos una palabra no capitalizada, paramos
            break
    
    if not accumulated:
        # v1.4: Si hay pronombre y no se extrajo entidad, usar fallback
        if has_pronoun and fallback_focus_entity:
            return fallback_focus_entity
        return None
    
    # Invertir para obtener el orden normal
    entity = " ".join(reversed(accumulated))
    # Limpiar comas o puntos finales
    entity = entity.strip(" ,;.")
    
    return entity if entity else None


def _extract_wikipedia_title_from_goal(goal: str) -> Optional[str]:
    """
    Extrae un candidato de título de artículo a partir del objetivo textual.
    
    Busca palabras capitalizadas al final del texto (después de eliminar "en wikipedia").
    """
    goal_lower = goal.lower()
    
    # Buscar y recortar "en wikipedia" o "en la wikipedia"
    topic_part = goal
    for suffix in [" en wikipedia", " en la wikipedia"]:
        if goal_lower.endswith(suffix):
            topic_part = goal[:len(goal) - len(suffix)].strip()
            break
    
    # Si no encontramos el sufijo, usar todo el texto
    if topic_part == goal:
        topic_part = goal.strip()
    
    # Dividir en tokens
    tokens = topic_part.split()
    if not tokens:
        return None
    
    # Recorrer desde el final hacia atrás, acumulando palabras capitalizadas
    accumulated = []
    short_connectors = {"de", "del", "la", "el", "y", "en"}
    
    for token in reversed(tokens):
        # Limpiar puntuación del token
        clean_token = token.strip(" ,;.")
        if not clean_token:
            continue
        
        # Si es una palabra corta conectora, la incluimos para no cortar apellidos compuestos
        if clean_token.lower() in short_connectors:
            accumulated.append(clean_token)
            continue
        
        # Si la primera letra es alfabética y mayúscula, es un nombre propio
        if clean_token[0].isalpha() and clean_token[0].isupper():
            accumulated.append(clean_token)
        else:
            # Si encontramos una palabra no capitalizada, paramos
            break
    
    if not accumulated:
        return None
    
    # Invertir para obtener el orden normal
    title = " ".join(reversed(accumulated))
    # Limpiar comas o puntos finales
    title = title.strip(" ,;.")
    
    return title if title else None


def _build_wikipedia_article_url(search_url: str, title: str) -> str:
    """
    Construye la URL de artículo en Wikipedia a partir de una URL de búsqueda y un título.
    
    Extrae el esquema y host de search_url (ej: https://es.wikipedia.org)
    y genera la URL del artículo con el título dado.
    """
    from urllib.parse import urlparse
    
    # Extraer esquema + host de search_url
    parsed = urlparse(search_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    
    # Generar slug: reemplazar espacios por _ y usar quote_plus para escaparlo
    slug = title.strip().replace(" ", "_")
    encoded_slug = quote_plus(slug, safe="_")
    
    return f"{base}/wiki/{encoded_slug}"


async def _maybe_resolve_wikipedia_search(
    browser: BrowserController,
    goal: str,
    final_observation: Optional[BrowserObservation],
    focus_entity: Optional[str] = None,
) -> tuple[Optional[BrowserObservation], List[StepResult]]:
    """
    Resuelve determinísticamente una búsqueda de Wikipedia navegando al artículo correcto.
    
    v1.4: Solo resuelve artículos por entidad, nunca por frases literales.
    Si no hay entidad clara, no resuelve nada.
    v1.4: Endurecido - verifica que focus_entity esté contenido en final_title después de navegar.
    
    Devuelve (nueva_observación, [step_result]) si tiene éxito, o (final_observation, []) si no aplica o falla.
    """
    resolver_steps: List[StepResult] = []
    
    # Validaciones iniciales
    if final_observation is None:
        return (final_observation, resolver_steps)
    
    if not _is_wikipedia_search_url(final_observation.url or ""):
        return (final_observation, resolver_steps)
    
    goal_lower = goal.lower()
    if "wikipedia" not in goal_lower:
        return (final_observation, resolver_steps)
    
    # v1.4: Obtener entidad efectiva usando _normalize_wikipedia_query
    # Solo resolvemos si tenemos una entidad clara
    article_title = _normalize_wikipedia_query(goal, focus_entity=focus_entity)
    
    if not article_title:
        # No sabemos qué artículo concreto buscar; no tocamos nada
        return (final_observation, resolver_steps)
    
    try:
        # Construir URL del artículo usando solo la entidad
        from urllib.parse import urlparse
        
        parsed = urlparse(final_observation.url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        slug = article_title.replace(" ", "_")
        encoded_slug = quote_plus(slug, safe="_")
        article_url = f"{base}/wiki/{encoded_slug}"
        
        # Navegar al artículo
        action = BrowserAction(type="open_url", args={"url": article_url})
        error = await _execute_action(action, browser)
        
        if error:
            # Si hay error, devolver la observación original sin romper el flujo
            return (final_observation, resolver_steps)
        
        # Obtener la nueva observación
        article_observation = await browser.get_observation()
        
        # v1.4: Endurecer verificación - normalizar y comparar
        final_title = (article_observation.title or "").strip()
        final_title_normalized = final_title.lower()
        # Quitar paréntesis y su contenido
        final_title_normalized = re.sub(r"\s*\([^)]*\)\s*", "", final_title_normalized)
        
        # Normalizar focus_entity
        focus_normalized = ""
        if focus_entity:
            focus_normalized = focus_entity.lower().strip()
            focus_normalized = re.sub(r"\s*\([^)]*\)\s*", "", focus_normalized)
        
        # Verificación: si focus_entity NO está contenido en final_title, no continuar
        if focus_entity and focus_normalized:
            if focus_normalized not in final_title_normalized:
                # NO navegar más automáticamente - registrar error
                error_step = StepResult(
                    observation=article_observation,
                    last_action=action,
                    error=None,
                    info={
                        "resolver_error": "article_mismatch",
                        "expected_entity": focus_entity,
                        "final_title": final_title,
                        "resolver": "wikipedia_article_v2_failed",
                    }
                )
                resolver_steps.append(error_step)
                # Devolver la observación original (de la búsqueda)
                return (final_observation, resolver_steps)
        
        # Crear StepResult de éxito
        step_result = StepResult(
            observation=article_observation,
            last_action=action,
            error=None,
            info={
                "resolver": "wikipedia_article_v2",
                "article_title": article_title,
                "from_search_url": final_observation.url,
            }
        )
        
        resolver_steps.append(step_result)
        return (article_observation, resolver_steps)
    
    except Exception:
        # En caso de error, no rompemos el flujo
        return (final_observation, resolver_steps)


async def _run_llm_task_single(
    browser: BrowserController,
    goal: str,
    max_steps: int = 8,
    focus_entity: Optional[str] = None,
    reset_context: bool = False,
    sub_goal_index: Optional[int] = None,
    execution_profile: Optional[ExecutionProfile] = None,
    context_strategies: Optional[List[ContextStrategy]] = None,
    session_context: Optional[SessionContext] = None,
    retry_context: Optional[Dict[str, Any]] = None,
) -> Tuple[List[StepResult], str]:
    """
    Ejecuta el agente LLM para un único objetivo (sin descomposición)
    y genera una respuesta final en lenguaje natural basada en la última
    observación.
    
    v1.3: Acepta focus_entity para normalizar queries.
    v1.4: Acepta reset_context para forzar contexto limpio al inicio.
    v1.4: Aislamiento estricto de steps - solo usa steps_local para el prompt.
    v1.9.0: Acepta ExecutionProfile para controlar el comportamiento.
    v2.1.0: Acepta context_strategies para selección de estrategias por petición.
    v2.2.0: Acepta session_context para detección de instrucciones de file upload.
    """
    # v1.4: Crear estructura local, no compartida
    steps_local: List[StepResult] = []

    # v1.4: Calcular focus_entity si no se proporciona
    if focus_entity is None:
        focus_entity = _extract_focus_entity_from_goal(goal)

    # v1.4: Orientación dura a Wikipedia si el objetivo lo pide
    # Solo si no estamos reseteando contexto (para evitar duplicar navegación)
    if not reset_context:
        text_lower = goal.lower()
        if "wikipedia" in text_lower:
            # v1.4: Usar query normalizada con focus_entity
            query = _normalize_wikipedia_query(goal, focus_entity=focus_entity)
            if query:
                search_param = quote_plus(query)
                wikipedia_url = f"https://es.wikipedia.org/wiki/Especial:Buscar?search={search_param}"

                forced_action = BrowserAction(type="open_url", args={"url": wikipedia_url})

                try:
                    error = await _execute_action(forced_action, browser)
                    if error:
                        try:
                            current_obs = await browser.get_observation()
                        except Exception:
                            from backend.shared.models import BrowserObservation
                            current_obs = BrowserObservation(
                                url="",
                                title="",
                                visible_text_excerpt="",
                                clickable_texts=[],
                                input_hints=[]
                            )
                        steps_local.append(
                            StepResult(
                                observation=current_obs,
                                last_action=forced_action,
                                error=error,
                                info={"phase": "forced_wikipedia_error"},
                            )
                        )
                    else:
                        obs = await browser.get_observation()
                        steps_local.append(
                            StepResult(
                                observation=obs,
                                last_action=forced_action,
                                error=None,
                                info={"phase": "forced_wikipedia"},
                            )
                        )
                except Exception as exc:  # pragma: no cover - defensivo
                    try:
                        current_obs = await browser.get_observation()
                    except Exception:
                        from backend.shared.models import BrowserObservation
                        current_obs = BrowserObservation(
                            url="",
                            title="",
                            visible_text_excerpt="",
                            clickable_texts=[],
                            input_hints=[]
                        )
                    steps_local.append(
                        StepResult(
                            observation=current_obs,
                            last_action=forced_action,
                            error=str(exc),
                            info={"phase": "forced_wikipedia_error"},
                        )
                    )

    # Ejecutar el agente LLM normal a partir del contexto actual
    # v1.4: Pasar focus_entity y reset_context a run_llm_agent
    # v1.9.0: Pasar execution_profile si está disponible
    more_steps = await run_llm_agent(
        goal=goal,
        browser=browser,
        max_steps=max_steps,
        focus_entity=focus_entity,
        reset_context=reset_context,
        execution_profile=execution_profile
    )
    # v1.4: Añadir solo a steps_local, no usar all_steps externos
    steps_local.extend(more_steps)

    # Obtener la última observación disponible (solo de steps_local)
    last_observation: Optional[BrowserObservation] = None
    for step in reversed(steps_local):
        if step.observation is not None:
            last_observation = step.observation
            break

    if last_observation is None:
        # Fallback duro si por alguna razón no hay observación
        return steps_local, "No he podido obtener ninguna observación del navegador para responder."

    # Resolver determinísticamente búsquedas de Wikipedia si es necesario
    # v1.4: Pasar focus_entity a _maybe_resolve_wikipedia_search
    resolved_observation, resolver_steps = await _maybe_resolve_wikipedia_search(
        browser, goal, last_observation, focus_entity=focus_entity
    )
    if resolved_observation is not None:
        steps_local.extend(resolver_steps)
        last_observation = resolved_observation

    # v1.4: Marcar todos los steps con sub_goal_index si se proporciona
    if sub_goal_index is not None:
        for s in steps_local:
            info = dict(s.info or {})
            info["sub_goal_index"] = sub_goal_index
            if focus_entity:
                info["focus_entity"] = focus_entity
            s.info = info

    # v1.4: Construir el prompt usando solo steps_local (todos son del sub-objetivo actual)
    # Filtrar por sub_goal_index si se proporciona (aunque todos deberían ser del mismo)
    relevant_steps = steps_local
    if sub_goal_index is not None:
        relevant_steps = [
            s for s in steps_local
            if s.info.get("sub_goal_index") == sub_goal_index
        ]
        # Si no hay steps filtrados, usar todos los del sub-objetivo actual
        if not relevant_steps:
            relevant_steps = steps_local
    
    # Si hay focus_entity, priorizar steps donde aparezca en title o url
    if focus_entity and relevant_steps:
        focus_entity_lower = focus_entity.lower()
        prioritized_steps = []
        other_steps = []
        for step in relevant_steps:
            if step.observation:
                title_lower = (step.observation.title or "").lower()
                url_lower = (step.observation.url or "").lower()
                if focus_entity_lower in title_lower or focus_entity_lower in url_lower:
                    prioritized_steps.append(step)
                else:
                    other_steps.append(step)
        # Si encontramos steps prioritarios, usarlos; si no, usar todos
        if prioritized_steps:
            relevant_steps = prioritized_steps + other_steps
    
    # Construir bloque de observaciones relevantes
    observations_text = ""
    if relevant_steps:
        observations_parts = []
        for step in relevant_steps:
            if step.observation:
                obs = step.observation
                obs_text = f"URL: {obs.url or 'N/A'}\n"
                obs_text += f"Título: {obs.title or 'N/A'}\n"
                if obs.visible_text_excerpt:
                    obs_text += f"Contenido: {obs.visible_text_excerpt[:500]}...\n"
                observations_parts.append(obs_text)
        if observations_parts:
            observations_text = "\n---\n".join(observations_parts)
    
    # Construir el prompt para el LLM de respuesta final
    url = last_observation.url or ""
    title = last_observation.title or ""
    visible = last_observation.visible_text_excerpt or ""

    system_prompt = SYSTEM_PROMPT_ANSWER

    user_prompt = (
        f"Objetivo original del usuario:\n{goal}\n\n"
    )
    
    # v2.6.0: Añadir contexto de retry si existe
    if retry_context and retry_context.get("attempt_index", 0) > 0:
        retry_prompt_text = _build_retry_prompt_context(retry_context)
        user_prompt += retry_prompt_text
    
    # v1.4: Añadir bloque de observaciones relevantes si hay
    if observations_text:
        user_prompt += (
            "Observaciones relevantes del agente:\n"
            f"{observations_text}\n\n"
        )
        # Si hay focus_entity pero no se encontró en las fuentes, añadir nota
        if focus_entity:
            found_entity = False
            for step in relevant_steps:
                if step.observation:
                    title_lower = (step.observation.title or "").lower()
                    url_lower = (step.observation.url or "").lower()
                    if focus_entity.lower() in title_lower or focus_entity.lower() in url_lower:
                        found_entity = True
                        break
            if not found_entity:
                user_prompt += (
                    "Nota: No se encontró una fuente que mencione explícitamente la entidad esperada "
                    f"({focus_entity}). Se utilizan las mejores páginas disponibles para responder igualmente.\n\n"
                )
    
    user_prompt += (
        f"Última URL visitada por el agente:\n{url}\n\n"
        f"Título de la página:\n{title}\n\n"
        "Contenido de la página (extracto del texto visible):\n"
        f"{visible}\n\n"
        "Instrucciones importantes:\n"
        "- Prioriza la información procedente de Wikipedia cuando el objetivo sea 'quién fue X' o 'información sobre X'.\n"
        "- Prioriza la información procedente de las páginas de imágenes cuando el objetivo hable de 'imágenes', 'fotos' o 'fotografías'.\n"
        "- No debes bloquear la respuesta solo porque haya otras páginas menos relevantes en el historial de pasos.\n"
        "- Ignora las páginas que claramente no estén relacionadas con la entidad del objetivo actual.\n"
        "- Indica siempre de qué página principal (URL y título) has sacado la información para tu respuesta.\n"
        "- Si realmente no encuentras ninguna fuente útil relacionada con la entidad, dilo explícitamente.\n\n"
        "Usa esta información para responder al objetivo del usuario en español."
    )
    
    # v1.4: Calcular tamaño real del prompt para logging
    prompt_len = len(system_prompt) + len(user_prompt)

    client = AsyncOpenAI(base_url=LLM_API_BASE, api_key=LLM_API_KEY)
    try:
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
        )
        final_answer = response.choices[0].message.content or ""
    except Exception as exc:  # pragma: no cover - defensivo
        final_answer = (
            "He tenido un problema al generar la respuesta final a partir de la página "
            f"visitada. Detalle técnico: {exc}"
        )

    # v1.4: Almacenar prompt_len en el último step para logging posterior
    # v2.2.0: Intentar construir instrucción de file upload si aplica
    # v2.3.0: Intentar ejecutar upload si hay instrucción y el goal es de subida
    if steps_local:
        last_step = steps_local[-1]
        info = dict(last_step.info or {})
        info["prompt_len"] = prompt_len
        
        # v2.2.0: Detectar y construir instrucción de file upload
        upload_instruction = None
        try:
            from backend.agents.file_upload import _maybe_build_file_upload_instruction
            from backend.agents.document_repository import DocumentRepository
            from backend.config import DOCUMENT_REPOSITORY_BASE_DIR
            from pathlib import Path
            
            if session_context is not None:
                document_repo = DocumentRepository(Path(DOCUMENT_REPOSITORY_BASE_DIR))
                upload_instruction = _maybe_build_file_upload_instruction(
                    goal=goal,
                    focus_entity=focus_entity,
                    session_context=session_context,
                    document_repository=document_repo,
                )
                
                if upload_instruction:
                    info["file_upload_instruction"] = upload_instruction.to_dict()
                    logger.info(
                        f"[file-upload] Added upload instruction to step: {upload_instruction.description}"
                    )
        except Exception as e:
            logger.warning(f"[file-upload] Error building upload instruction: {e}", exc_info=True)
        
        # v2.3.0: Intentar ejecutar upload si hay instrucción y el goal es claramente de subida
        if upload_instruction:
            goal_lower = goal.lower()
            upload_keywords = [
                "sube", "subir", "adjunta", "adjuntar",
                "sube el", "sube la", "sube un", "sube una",
                "adjunta el", "adjunta la", "adjunta un", "adjunta una",
                "subir documento", "subir documentación", "adjuntar documento", "adjuntar documentación",
            ]
            has_upload_intent = any(keyword in goal_lower for keyword in upload_keywords)
            
            if has_upload_intent:
                try:
                    upload_step = await _maybe_execute_file_upload(browser, upload_instruction)
                    if upload_step:
                        steps_local.append(upload_step)
                        # v2.4.0: Extraer status del nuevo formato
                        upload_status = upload_step.info.get('upload_status', {})
                        status = upload_status.get('status') if isinstance(upload_status, dict) else upload_status
                        logger.info(
                            f"[file-upload] Upload executed: {upload_instruction.description} -> "
                            f"status={status}"
                        )
                except Exception as e:
                    logger.warning(f"[file-upload] Error executing upload: {e}", exc_info=True)
        
        last_step.info = info

    return steps_local, final_answer


async def run_llm_task_with_answer(
    goal: str,
    browser: BrowserController,
    max_steps: int = 8,
    context_strategies: Optional[List[str]] = None,
    execution_profile_name: Optional[str] = None,
    disabled_sub_goal_indices: Optional[List[int]] = None,
) -> tuple[List[StepResult], str, str, str, List[SourceInfo]]:
    """
    Orquesta la ejecución del agente para uno o varios sub-objetivos.

    - Si el objetivo no se descompone, delega en _run_llm_task_single.
    - Si se descompone en varios sub-objetivos, los ejecuta en secuencia,
      reutilizando el mismo navegador y agregando las respuestas.
    
    v1.5.0: Recolecta métricas de ejecución usando AgentMetrics.
    v1.7.0: Usa SessionContext para mantener memoria de entidades durante la ejecución.
    v1.9.0: Infiere y aplica ExecutionProfile desde el texto del objetivo.
    v2.1.0: Acepta context_strategies para selección de estrategias por petición.
    v2.7.0: Acepta execution_profile_name para selección explícita del perfil de ejecución.
    
    Args:
        goal: Objetivo del usuario
        browser: Controlador del navegador
        max_steps: Número máximo de pasos por sub-objetivo
        context_strategies: Lista opcional de nombres de estrategias de contexto
        execution_profile_name: Nombre del perfil de ejecución ("fast", "balanced", "thorough") o None
    """
    # v2.7.0: Determinar ExecutionProfile desde execution_profile_name o inferirlo
    if execution_profile_name:
        valid_profiles = {"fast", "balanced", "thorough"}
        if execution_profile_name in valid_profiles:
            if execution_profile_name == "fast":
                execution_profile = ExecutionProfile.fast()
            elif execution_profile_name == "thorough":
                execution_profile = ExecutionProfile.thorough()
            else:  # "balanced"
                execution_profile = ExecutionProfile.default()
            logger.debug(
                "[execution-profile] name=%r effective=%r",
                execution_profile_name,
                execution_profile.mode,
            )
        else:
            logger.warning(
                "[execution-profile] Invalid profile name %r, falling back to from_goal_text",
                execution_profile_name
            )
            execution_profile = ExecutionProfile.from_goal_text(goal)
    else:
        # Comportamiento por defecto: inferir desde el texto del objetivo
        execution_profile = ExecutionProfile.from_goal_text(goal)
        logger.debug(
            "[execution-profile] inferred from goal text: %r",
            execution_profile.mode,
        )
    
    # v2.1.0: Construir estrategias de contexto desde nombres
    from backend.config import DEFAULT_CAE_BASE_URL
    active_strategies = build_context_strategies(context_strategies, cae_base_url=DEFAULT_CAE_BASE_URL)
    if context_strategies:
        strategy_names_str = ", ".join(context_strategies)
        logger.debug(f"[context-strategies] using strategies: {strategy_names_str}")
    else:
        logger.debug("[context-strategies] using default strategies")
    
    # v2.7.0: ExecutionProfile ya se determinó arriba desde execution_profile_name o desde goal text
    logger.info(f"[profile] using execution profile: {execution_profile.to_dict()}")
    
    # v1.7.0: Inicializar contexto de sesión
    session_context = SessionContext()
    session_context.update_goal(goal)
    
    # v1.5.0: Inicializar métricas
    # v2.9.0: Inicializar contadores de sub-goals saltados
    agent_metrics = AgentMetrics()
    agent_metrics.start()
    agent_metrics.skipped_sub_goals_count = len(disabled_sub_goal_indices or [])
    agent_metrics.skipped_sub_goal_indices = sorted(list(disabled_sub_goal_indices or []))
    
    # v1.4: Entidad global del objetivo completo
    # Primero intentamos desde el goal completo, luego desde el primer sub-goal con entidad
    global_focus_entity = _extract_focus_entity_from_goal(goal)
    
    sub_goals = _decompose_goal(goal)
    if not sub_goals:
        # Fallback de seguridad: usar el objetivo original
        sub_goals = [goal]
    
    # v2.9.0: Filtrar sub-goals deshabilitados por el usuario
    disabled = set(disabled_sub_goal_indices or [])
    effective_sub_goals = [
        (idx, sub_goal)
        for idx, sub_goal in enumerate(sub_goals, start=1)
        if idx not in disabled
    ]
    
    # v2.9.0: Si todos los sub-goals están deshabilitados, devolver respuesta amigable
    if not effective_sub_goals:
        # Crear respuesta sin ejecutar nada
        empty_steps: List[StepResult] = []
        empty_answer = "No se ha ejecutado ningún sub-objetivo porque todos han sido desactivados en el plan."
        
        # Crear métricas básicas
        agent_metrics = AgentMetrics()
        agent_metrics.start()
        agent_metrics.plan_confirmed = True
        agent_metrics.skipped_sub_goals_count = len(disabled_sub_goal_indices or [])
        agent_metrics.skipped_sub_goal_indices = sorted(list(disabled_sub_goal_indices or []))
        agent_metrics.end()
        
        metrics_summary = agent_metrics.to_summary_dict()
        if empty_steps:
            empty_steps[-1].info = empty_steps[-1].info or {}
            empty_steps[-1].info["metrics"] = metrics_summary
        
        return empty_steps, empty_answer, "", "", []
    
    # v2.9.0: Usar effective_sub_goals en lugar de sub_goals completos
    # Convertir effective_sub_goals a lista simple para compatibilidad con código existente
    # Pero mantener mapeo de índices originales
    effective_sub_goals_dict = {idx: sg for idx, sg in effective_sub_goals}
    sub_goals_to_execute = [sg for _, sg in effective_sub_goals]
    
    # v1.9.0: Filtrar sub-goals según restricciones del perfil
    # v2.9.0: Mantener mapeo de índices originales después del filtro del perfil
    original_sub_goals = sub_goals_to_execute.copy()
    sub_goals_to_execute = [sg for sg in sub_goals_to_execute if not execution_profile.should_skip_goal(sg)]
    
    # v2.9.0: Reconstruir effective_sub_goals solo con los que pasan el filtro del perfil
    effective_sub_goals = [(idx, sg) for idx, sg in effective_sub_goals if sg in sub_goals_to_execute]
    if len(sub_goals_to_execute) < len(original_sub_goals):
        skipped = len(original_sub_goals) - len(sub_goals_to_execute)
        logger.info(f"[profile] skipped {skipped} sub-goal(s) due to profile restrictions")
    
    # v1.4: Si no hay entidad global del goal completo, intentar desde el primer sub-goal
    if not global_focus_entity:
        for sub_goal in sub_goals_to_execute:
            candidate = _extract_focus_entity_from_goal(sub_goal)
            if candidate:
                global_focus_entity = candidate
                break

    # Caso simple: un solo objetivo → comportamiento actual
    if len(sub_goals) == 1:
        sub_goal = sub_goals[0]
        session_context.update_goal(goal, sub_goal)
        
        # v1.7.0: Resolver focus_entity usando SessionContext si hay pronombres
        focus_entity = _extract_focus_entity_from_goal(sub_goal, fallback_focus_entity=global_focus_entity)
        if not focus_entity:
            # Si no hay entidad explícita y hay pronombres, usar contexto
            if goal_uses_pronouns(sub_goal):
                focus_entity = session_context.resolve_entity_reference(sub_goal)
            if not focus_entity:
                focus_entity = global_focus_entity
        
        # v1.4: Primer sub-goal siempre resetea contexto
        # v2.9.0: Usar índice original del sub-goal
        t0 = time.perf_counter()
        steps, final_answer = await _run_llm_task_single(
            browser, sub_goal, max_steps, focus_entity=focus_entity, reset_context=True, sub_goal_index=original_idx, execution_profile=execution_profile, context_strategies=active_strategies, session_context=session_context
        )
        t1 = time.perf_counter()
        
        # v1.7.0: Actualizar contexto con la entidad confirmada
        if focus_entity:
            session_context.update_entity(focus_entity)
        
        # v1.5.0: Extraer métricas del último step y añadirlas a AgentMetrics
        metrics_data = None
        for step in reversed(steps):
            if step.info and "metrics_subgoal" in step.info:
                metrics_data = step.info["metrics_subgoal"]
                break
        
        if metrics_data:
            agent_metrics.add_subgoal_metrics(
                goal=metrics_data["goal"],
                focus_entity=metrics_data.get("focus_entity"),
                goal_type=metrics_data["goal_type"],
                steps_taken=metrics_data["steps_taken"],
                early_stop_reason=metrics_data.get("early_stop_reason"),
                elapsed_seconds=metrics_data["elapsed_seconds"],
                success=metrics_data["success"],
            )
        else:
            # Fallback: calcular métricas básicas si no están en StepResult
            agent_metrics.add_subgoal_metrics(
                goal=sub_goal,
                focus_entity=focus_entity,
                goal_type=_infer_goal_type(sub_goal),
                steps_taken=len(steps),
                early_stop_reason=None,
                elapsed_seconds=t1 - t0,
                success=False,
            )
        
        # v1.5.0: Logging de métricas por sub-objetivo
        if metrics_data:
            logger.info(
                "[metrics] sub-goal idx=1 type=%s steps=%d early_stop=%s elapsed=%.2fs success=%s",
                metrics_data["goal_type"],
                metrics_data["steps_taken"],
                metrics_data.get("early_stop_reason") or "none",
                metrics_data["elapsed_seconds"],
                metrics_data["success"],
            )
        else:
            logger.info(
                "[sub-goal] idx=1 sub_goal=%r focus_entity=%r steps=%d elapsed=%.2fs",
                sub_goal,
                focus_entity,
                len(steps),
                t1 - t0,
            )
        
        # Añadir marcado de focus_entity a todos los steps
        # v2.5.1: Actualizar métricas de uploads y verificación mientras se procesan los steps
        for s in steps:
            info = dict(s.info or {})
            if focus_entity:
                info["focus_entity"] = focus_entity
            s.info = info
            
            # v2.5.1: Registrar uploads y verificaciones en métricas
            if info.get("upload_status"):
                agent_metrics.register_upload_attempt(info["upload_status"])
            
            if info.get("upload_verification"):
                upload_verification = info["upload_verification"]
                if isinstance(upload_verification, dict):
                    verification_status = upload_verification.get("status")
                    agent_metrics.register_upload_verification(verification_status)
            
            # v3.2.0: Registrar confirmaciones visuales
            if info.get("visual_confirmation"):
                visual_confirmation = info["visual_confirmation"]
                if isinstance(visual_confirmation, dict):
                    agent_metrics.visual_confirmations_attempted += 1
                    if not visual_confirmation.get("confirmed", False):
                        agent_metrics.visual_confirmations_failed += 1
        
        # v1.5.0: Finalizar métricas y obtener resumen
        agent_metrics.finish()
        metrics_summary = agent_metrics.to_summary_dict()
        # v2.1.0: Añadir información de estrategias activas
        if context_strategies:
            metrics_summary["summary"]["context_strategies"] = context_strategies
        logger.info("[metrics] summary=%r", metrics_summary)
        
        # Calcular source_url, source_title y sources para mantener compatibilidad
        last_observation: Optional[BrowserObservation] = None
        for step in reversed(steps):
            if step.observation is not None:
                last_observation = step.observation
                break
        
        source_url = last_observation.url or "" if last_observation else ""
        source_title = last_observation.title or "" if last_observation else ""
        
        sources: List[SourceInfo] = []
        if source_url:
            sources.append(SourceInfo(url=source_url, title=source_title or None))
        
        seen_urls = {source_url} if source_url else set()
        for step in reversed(steps):
            obs = step.observation
            if not obs or not obs.url:
                continue
            url = obs.url
            if url in seen_urls:
                continue
            seen_urls.add(url)
            sources.append(SourceInfo(url=url, title=(obs.title or None)))
            if len(sources) >= 3:
                break
        
        # v1.6.0: Construir respuesta estructurada
        structured_answer = _build_final_answer(
            original_goal=goal,
            sub_goals=sub_goals,
            sub_goal_answers=[final_answer],
            all_steps=steps,
            agent_metrics=agent_metrics,
        )
        
        # v1.5.0 y v1.7.0: Añadir métricas, estructura y contexto al último step
        if steps:
            last_step = steps[-1]
            info = dict(last_step.info or {})
            info["metrics"] = metrics_summary
            info["structured_answer"] = structured_answer
            info["session_context"] = session_context.to_debug_dict()
            last_step.info = info
        
        # v1.6.0: Usar answer_text estructurado como final_answer (mantiene compatibilidad)
        final_answer = structured_answer["answer_text"]
        
        return steps, final_answer, source_url, source_title, sources

    all_steps: List[StepResult] = []
    answers: List[str] = []
    all_observations: List[BrowserObservation] = []

    # v2.9.0: Iterar sobre effective_sub_goals manteniendo índices originales
    for original_idx, sub_goal in effective_sub_goals:
        # v2.9.0: Saltar si este sub-goal fue filtrado por el perfil
        if sub_goal not in sub_goals_to_execute:
            continue
        # v1.7.0: Actualizar contexto con el sub-goal actual
        session_context.update_goal(goal, sub_goal)
        
        # v1.7.0: Resolver focus_entity usando SessionContext
        direct_entity = _extract_focus_entity_from_goal(sub_goal)
        
        if direct_entity:
            # Si el sub-objetivo menciona explícitamente una entidad (ej. "Charles Babbage")
            sub_focus_entity = direct_entity
        else:
            # No hay entidad explícita - usar contexto si hay pronombres
            if goal_uses_pronouns(sub_goal):
                sub_focus_entity = session_context.resolve_entity_reference(sub_goal)
            else:
                sub_focus_entity = None
            
            # Fallback: usar la global si existe
            if not sub_focus_entity:
                sub_focus_entity = global_focus_entity
        
        # v1.7.0: Logging con información de contexto
        logger.info(
            f"[cometlocal] sub_goal_index={idx} sub_goal={sub_goal!r} focus_entity={sub_focus_entity!r} "
            f"context_entity={session_context.current_focus_entity!r}"
        )
        
        # Refuerzo de contexto al inicio de cada sub-goal
        # Si el sub-goal contiene "wikipedia", forzar contexto limpio
        context_steps: List[StepResult] = []
        if "wikipedia" in sub_goal.lower():
            # v1.4: Normalizar la query usando sub_focus_entity como fallback
            query = _normalize_wikipedia_query(sub_goal, focus_entity=sub_focus_entity)
            if query:
                search_param = quote_plus(query)
                wikipedia_search_url = f"https://es.wikipedia.org/wiki/Especial:Buscar?search={search_param}"
                
                forced_action = BrowserAction(type="open_url", args={"url": wikipedia_search_url})
                
                try:
                    error = await _execute_action(forced_action, browser)
                    if error:
                        try:
                            current_obs = await browser.get_observation()
                        except Exception:
                            from backend.shared.models import BrowserObservation
                            current_obs = BrowserObservation(
                                url="",
                                title="",
                                visible_text_excerpt="",
                                clickable_texts=[],
                                input_hints=[]
                            )
                        context_steps.append(
                            StepResult(
                                observation=current_obs,
                                last_action=forced_action,
                                error=error,
                                info={"phase": "context_cleanup_error"},
                            )
                        )
                    else:
                        obs = await browser.get_observation()
                        context_steps.append(
                            StepResult(
                                observation=obs,
                                last_action=forced_action,
                                error=None,
                                info={"phase": "context_cleanup"},
                            )
                        )
                except Exception as exc:  # pragma: no cover - defensivo
                    try:
                        current_obs = await browser.get_observation()
                    except Exception:
                        from backend.shared.models import BrowserObservation
                        current_obs = BrowserObservation(
                            url="",
                            title="",
                            visible_text_excerpt="",
                            clickable_texts=[],
                            input_hints=[]
                        )
                    context_steps.append(
                        StepResult(
                            observation=current_obs,
                            last_action=forced_action,
                            error=str(exc),
                            info={"phase": "context_cleanup_error"},
                        )
                    )
        
        # v2.6.0: Retry loop para sub-objetivos
        retry_policy = RetryPolicy()
        attempt_index = 0
        retry_context: Dict[str, Any] = {
            "attempt_index": 0,
            "last_upload_status": None,
            "last_verification_status": None,
            "last_error_message": None,
        }
        
        all_subgoal_steps_retry: List[StepResult] = []
        final_answer_retry = ""
        metrics_data_final = None
        success_final = False
        
        while True:
            # v1.4: Ejecutar el sub-objetivo
            # v2.9.0: Primer sub-goal efectivo resetea contexto solo en el primer intento
            # Usar original_idx para determinar si es el primero
            reset_ctx = (original_idx == 1) and (attempt_index == 0)
            t0 = time.perf_counter()
            
            # v2.6.0: Pasar retry_context al ejecutor
            steps, answer = await _run_llm_task_single(
                browser, sub_goal, max_steps, focus_entity=sub_focus_entity, reset_context=reset_ctx, 
                sub_goal_index=idx, execution_profile=execution_profile, context_strategies=active_strategies, 
                session_context=session_context, retry_context=retry_context if attempt_index > 0 else None
            )
            t1 = time.perf_counter()
            
            # Acumular steps de este intento
            all_subgoal_steps_retry.extend(steps)
            final_answer_retry = answer
            
            # v1.5.0: Extraer métricas del último step
            metrics_data = None
            for step in reversed(steps):
                if step.info and "metrics_subgoal" in step.info:
                    metrics_data = step.info["metrics_subgoal"]
                    break
            
            # v2.6.0: Evaluar si se necesita retry
            should_retry, upload_status, verification_status, error_message = _evaluate_subgoal_for_retry(
                steps, metrics_data, retry_policy
            )
            
            # Actualizar retry_context para el siguiente intento
            retry_context["last_upload_status"] = upload_status
            retry_context["last_verification_status"] = verification_status
            retry_context["last_error_message"] = error_message
            
            # Determinar si el intento fue exitoso
            success = metrics_data.get("success") if metrics_data else False
            # También considerar éxito si upload está confirmado
            if not success and upload_status == "success" and verification_status == "confirmed":
                success = True
            
            # Si fue exitoso, salir del loop
            if success:
                success_final = True
                metrics_data_final = metrics_data
                logger.debug(
                    "[retry] sub-goal=%d attempt=%d success=True",
                    original_idx, attempt_index
                )
                break
            
            # Si no se debe hacer retry o no se puede, salir
            if not should_retry or not retry_policy.can_retry(attempt_index):
                if should_retry and not retry_policy.can_retry(attempt_index):
                    # Se agotaron los retries
                    agent_metrics.register_retry_exhausted()
                    logger.debug(
                        "[retry] sub-goal=%d retries exhausted",
                        original_idx
                    )
                metrics_data_final = metrics_data
                break
            
            # Preparar siguiente intento
            attempt_index += 1
            retry_context["attempt_index"] = attempt_index
            agent_metrics.register_retry_attempt()
            logger.debug(
                "[retry] sub-goal=%d attempt=%d reason=%s",
                original_idx, attempt_index, upload_status or verification_status or "goal_failure"
            )
            
            # Backoff antes del siguiente intento
            await asyncio.sleep(retry_policy.backoff_seconds)
        
        # Si hubo retry exitoso, registrar éxito
        if attempt_index > 0 and success_final:
            agent_metrics.register_retry_success()
            logger.debug(
                "[retry] sub-goal=%d retry succeeded after %d attempts",
                original_idx, attempt_index + 1
            )
        
        # Usar steps y answer finales
        steps = all_subgoal_steps_retry
        answer = final_answer_retry
        metrics_data = metrics_data_final
        
        # v1.7.0: Actualizar contexto con la entidad confirmada después de completar el sub-goal
        if sub_focus_entity:
            session_context.update_entity(sub_focus_entity)
        
        # v1.5.0: Añadir métricas a AgentMetrics
        if metrics_data:
            agent_metrics.add_subgoal_metrics(
                goal=metrics_data["goal"],
                focus_entity=metrics_data.get("focus_entity"),
                goal_type=metrics_data["goal_type"],
                steps_taken=metrics_data["steps_taken"],
                early_stop_reason=metrics_data.get("early_stop_reason"),
                elapsed_seconds=metrics_data["elapsed_seconds"],
                success=metrics_data["success"] or success_final,
            )
            # v1.5.0: Logging de métricas por sub-objetivo
            # v2.9.0: Usar original_idx
            logger.info(
                "[metrics] sub-goal idx=%d type=%s steps=%d early_stop=%s elapsed=%.2fs success=%s",
                original_idx,
                metrics_data["goal_type"],
                metrics_data["steps_taken"],
                metrics_data.get("early_stop_reason") or "none",
                metrics_data["elapsed_seconds"],
                metrics_data["success"] or success_final,
            )
        else:
            # Fallback: calcular métricas básicas si no están en StepResult
            agent_metrics.add_subgoal_metrics(
                goal=sub_goal,
                focus_entity=sub_focus_entity,
                goal_type=_infer_goal_type(sub_goal),
                steps_taken=len(steps),
                early_stop_reason=None,
                elapsed_seconds=t1 - t0,
                success=success_final,
            )
            logger.info(
                "[sub-goal] idx=%d sub_goal=%r focus_entity=%r steps=%d elapsed=%.2fs",
                original_idx,
                sub_goal,
                sub_focus_entity,
                len(steps),
                t1 - t0,
            )
        
        # Combinar context_steps con steps
        all_subgoal_steps = context_steps + steps

        # Anotar en info a qué sub-objetivo pertenece cada paso
        # v2.5.1: Actualizar métricas de uploads y verificación mientras se procesan los steps
        # v2.9.0: Usar original_idx para mantener índices originales aunque se salten algunos
        for s in all_subgoal_steps:
            info = dict(s.info or {})
            info["sub_goal_index"] = original_idx
            info["sub_goal"] = sub_goal
            # v1.4: Añadir focus_entity si está disponible
            if sub_focus_entity:
                info["focus_entity"] = sub_focus_entity
            s.info = info
            
            # v2.5.1: Registrar uploads y verificaciones en métricas
            if info.get("upload_status"):
                agent_metrics.register_upload_attempt(info["upload_status"])
            
            if info.get("upload_verification"):
                upload_verification = info["upload_verification"]
                if isinstance(upload_verification, dict):
                    verification_status = upload_verification.get("status")
                    agent_metrics.register_upload_verification(verification_status)
            
            # v3.2.0: Registrar confirmaciones visuales
            if info.get("visual_confirmation"):
                visual_confirmation = info["visual_confirmation"]
                if isinstance(visual_confirmation, dict):
                    agent_metrics.visual_confirmations_attempted += 1
                    if not visual_confirmation.get("confirmed", False):
                        agent_metrics.visual_confirmations_failed += 1
            
            all_steps.append(s)
        
        # Guardar la última observación de este sub-objetivo
        for step in reversed(steps):
            if step.observation is not None:
                all_observations.append(step.observation)
                break

        # v1.6.0: Guardar respuesta sin numeración (la numeración se añade en _build_final_answer)
        answer = answer.strip()
        if answer:
            answers.append(answer)
        else:
            answers.append("(Sin información relevante encontrada para este sub-objetivo)")

    # v1.6.0: Construir respuesta estructurada
    agent_metrics.finish()
    metrics_summary = agent_metrics.to_summary_dict()
    logger.info("[metrics] summary=%r", metrics_summary)
    
    structured_answer = _build_final_answer(
        original_goal=goal,
        sub_goals=sub_goals,
        sub_goal_answers=answers,
        all_steps=all_steps,
        agent_metrics=agent_metrics,
    )
    
    # v1.6.0: Usar answer_text estructurado como final_answer (mantiene compatibilidad)
    final_answer = structured_answer["answer_text"]
    
    logger.info("[structured-answer] built final answer with %d sections", len(structured_answer["sections"]))
    
    # Calcular source_url, source_title y sources desde todas las observaciones
    last_observation: Optional[BrowserObservation] = None
    if all_observations:
        last_observation = all_observations[-1]
    else:
        # Fallback: buscar en todos los steps
        for step in reversed(all_steps):
            if step.observation is not None:
                last_observation = step.observation
                break

    source_url = last_observation.url or "" if last_observation else ""
    source_title = last_observation.title or "" if last_observation else ""

    sources: List[SourceInfo] = []
    if source_url:
        sources.append(SourceInfo(url=source_url, title=source_title or None))

    seen_urls = {source_url} if source_url else set()

    # Recorrer todas las observaciones (de más reciente a más antigua)
    for obs in reversed(all_observations):
        if not obs or not obs.url:
            continue
        url = obs.url
        if url in seen_urls:
            continue
        seen_urls.add(url)
        sources.append(SourceInfo(url=url, title=(obs.title or None)))
        if len(sources) >= 3:
            break

    # v1.5.0, v1.6.0, v1.7.0 y v1.9.0: Añadir métricas, estructura, contexto y perfil al último step
    # v2.1.0: Añadir información de estrategias activas
    if all_steps:
        last_step = all_steps[-1]
        info = dict(last_step.info or {})
        info["metrics"] = metrics_summary
        info["structured_answer"] = structured_answer
        info["session_context"] = session_context.to_debug_dict()
        info["execution_profile"] = execution_profile.to_dict()
        if context_strategies:
            info["context_strategies"] = context_strategies
        last_step.info = info
    
    # v1.9.0: Añadir execution_profile a metrics_summary
    # v2.1.0: Añadir información de estrategias activas
    # v2.7.0: Asegurar que context_strategies siempre esté presente
    if metrics_summary and "summary" in metrics_summary:
        metrics_summary["summary"]["execution_profile"] = execution_profile.to_dict()
        if context_strategies:
            metrics_summary["summary"]["context_strategies"] = context_strategies
        else:
            # Si no se especificaron, usar las estrategias por defecto
            default_strategy_names = [s.name for s in DEFAULT_CONTEXT_STRATEGIES]
            metrics_summary["summary"]["context_strategies"] = default_strategy_names

    return all_steps, final_answer, source_url, source_title, sources

