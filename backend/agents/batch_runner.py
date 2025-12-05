"""
Motor de ejecución batch autónoma para múltiples objetivos.

v3.0.0: Permite ejecutar una lista de objetivos de forma secuencial
sin intervención humana, generando un informe final estructurado.
"""

import logging
import time
from typing import List, Optional, Dict, Any
from pathlib import Path
import json
from datetime import datetime

from backend.shared.models import (
    BatchAgentRequest,
    BatchAgentGoal,
    BatchAgentResponse,
    BatchAgentGoalResult,
)
from backend.agents.agent_runner import run_llm_task_with_answer
from backend.browser.browser import BrowserController
from backend.config import ENABLE_BATCH_PERSISTENCE, BATCH_RUNS_DIR

logger = logging.getLogger(__name__)


async def run_batch_agent(
    batch_request: BatchAgentRequest,
    browser: BrowserController,
) -> BatchAgentResponse:
    """
    Ejecuta un batch de objetivos de forma autónoma.
    
    v3.0.0: Ejecuta cada objetivo secuencialmente usando run_llm_task_with_answer,
    captura resultados y métricas, y genera un resumen agregado.
    
    Args:
        batch_request: Petición batch con lista de objetivos
        browser: Controlador del navegador (compartido para todo el batch)
        
    Returns:
        BatchAgentResponse con resultados por objetivo y resumen global
    """
    start_time = time.perf_counter()
    
    # Inicializar contadores globales
    total_goals = len(batch_request.goals)
    success_count = 0
    failure_count = 0
    consecutive_failures = 0
    aborted_due_to_failures = False
    max_consecutive = batch_request.max_consecutive_failures or 5
    
    results: List[BatchAgentGoalResult] = []
    
    logger.info(
        f"[batch] Starting batch execution: {total_goals} goals, "
        f"max_consecutive_failures={max_consecutive}"
    )
    
    for idx, batch_goal in enumerate(batch_request.goals, start=1):
        # Verificar si debemos abortar por fallos consecutivos
        if consecutive_failures >= max_consecutive:
            logger.warning(
                f"[batch] Aborting batch after {consecutive_failures} consecutive failures "
                f"(max={max_consecutive})"
            )
            aborted_due_to_failures = True
            
            # Marcar objetivos restantes como no ejecutados
            for remaining_goal in batch_request.goals[idx - 1:]:
                results.append(
                    BatchAgentGoalResult(
                        id=remaining_goal.id,
                        goal=remaining_goal.goal,
                        success=False,
                        error_message=f"Batch aborted due to {consecutive_failures} consecutive failures",
                        final_answer=None,
                        metrics_summary=None,
                        sections=None,
                        structured_sources=None,
                        file_upload_instructions=None,
                    )
                )
                failure_count += 1
            break
        
        # Resolver execution_profile_name efectivo
        execution_profile_name = (
            batch_goal.execution_profile_name
            or batch_request.default_execution_profile_name
        )
        
        # Resolver context_strategies efectivas
        context_strategies = (
            batch_goal.context_strategies
            or batch_request.default_context_strategies
        )
        
        logger.info(
            f"[batch] Executing goal {idx}/{total_goals}: id={batch_goal.id!r} "
            f"goal={batch_goal.goal[:50]}..."
        )
        
        goal_start_time = time.perf_counter()
        
        try:
            # Ejecutar objetivo usando el motor normal
            steps, final_answer, source_url, source_title, sources = (
                await run_llm_task_with_answer(
                    goal=batch_goal.goal,
                    browser=browser,
                    max_steps=8,
                    context_strategies=context_strategies,
                    execution_profile_name=execution_profile_name,
                    disabled_sub_goal_indices=None,  # En batch no hay selección manual
                )
            )
            
            # Extraer información estructurada del último step
            structured_answer = None
            metrics_summary = None
            file_upload_instructions = None
            
            if steps:
                last_step = steps[-1]
                if last_step.info:
                    if "structured_answer" in last_step.info:
                        structured_answer = last_step.info["structured_answer"]
                    if "metrics" in last_step.info:
                        metrics_summary = last_step.info["metrics"]
                        # v3.0.0: Marcar modo batch en métricas
                        if metrics_summary and "summary" in metrics_summary:
                            metrics_summary["summary"]["mode"] = "batch"
            
            # Extraer file_upload_instructions de todos los steps
            file_upload_instructions_list = []
            seen_paths = set()
            for step in steps:
                if step.info and "file_upload_instruction" in step.info:
                    instruction_dict = step.info["file_upload_instruction"]
                    path_str = instruction_dict.get("path", "")
                    if path_str and path_str not in seen_paths:
                        seen_paths.add(path_str)
                        file_upload_instructions_list.append(instruction_dict)
            
            goal_elapsed = time.perf_counter() - goal_start_time
            
            # Marcar como éxito (por simplificar en v3.0.0, basta con no-excepción)
            success = True
            error_message = None
            
            # Extraer secciones y structured_sources de structured_answer
            sections = None
            structured_sources = None
            if structured_answer:
                sections = structured_answer.get("sections")
                structured_sources = structured_answer.get("sources")
            
            result = BatchAgentGoalResult(
                id=batch_goal.id,
                goal=batch_goal.goal,
                success=success,
                error_message=error_message,
                final_answer=final_answer,
                metrics_summary=metrics_summary,
                sections=sections,
                structured_sources=structured_sources,
                file_upload_instructions=file_upload_instructions_list if file_upload_instructions_list else None,
            )
            
            results.append(result)
            success_count += 1
            consecutive_failures = 0  # Reset contador de fallos consecutivos
            
            logger.info(
                f"[batch] Goal {idx}/{total_goals} completed successfully: "
                f"id={batch_goal.id!r} elapsed={goal_elapsed:.2f}s"
            )
            
        except Exception as e:
            goal_elapsed = time.perf_counter() - goal_start_time
            error_msg = str(e)
            
            logger.error(
                f"[batch] Goal {idx}/{total_goals} failed: id={batch_goal.id!r} "
                f"error={error_msg} elapsed={goal_elapsed:.2f}s",
                exc_info=True
            )
            
            result = BatchAgentGoalResult(
                id=batch_goal.id,
                goal=batch_goal.goal,
                success=False,
                error_message=error_msg,
                final_answer=None,
                metrics_summary=None,
                sections=None,
                structured_sources=None,
                file_upload_instructions=None,
            )
            
            results.append(result)
            failure_count += 1
            consecutive_failures += 1
    
    end_time = time.perf_counter()
    elapsed_seconds = end_time - start_time
    
    # Construir resumen global
    failure_ratio = failure_count / total_goals if total_goals > 0 else 0.0
    
    summary = {
        "total_goals": total_goals,
        "success_count": success_count,
        "failure_count": failure_count,
        "failure_ratio": round(failure_ratio, 3),
        "aborted_due_to_failures": aborted_due_to_failures,
        "max_consecutive_failures": max_consecutive,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "mode": "batch",
    }
    
    response = BatchAgentResponse(
        goals=results,
        summary=summary,
    )
    
    logger.info(
        f"[batch] Batch execution completed: "
        f"total={total_goals} success={success_count} failure={failure_count} "
        f"elapsed={elapsed_seconds:.2f}s"
    )
    
    # v3.0.0: Persistencia opcional
    if ENABLE_BATCH_PERSISTENCE:
        try:
            _persist_batch_result(response)
        except Exception as e:
            logger.warning(f"[batch] Failed to persist batch result: {e}", exc_info=True)
    
    return response


def _persist_batch_result(response: BatchAgentResponse) -> None:
    """
    Persiste el resultado del batch en un archivo JSON.
    
    v3.0.0: Guarda el resultado completo para análisis posterior.
    """
    runs_dir = Path(BATCH_RUNS_DIR)
    runs_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = runs_dir / f"batch_{timestamp}.json"
    
    # Convertir a dict para serialización
    result_dict = {
        "summary": response.summary,
        "goals": [
            {
                "id": g.id,
                "goal": g.goal,
                "success": g.success,
                "error_message": g.error_message,
                "final_answer": g.final_answer,
                "metrics_summary": g.metrics_summary,
                "sections": g.sections,
                "structured_sources": g.structured_sources,
                "file_upload_instructions": g.file_upload_instructions,
            }
            for g in response.goals
        ],
    }
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, indent=2, ensure_ascii=False)
    
    logger.info(f"[batch] Persisted batch result to: {filename}")



