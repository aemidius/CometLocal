"""
Módulo para generar Outcome Judge Report: auto-evaluación post-ejecución.

v4.1.0: El LLM analiza pasos, métricas, planner_hints, spotlight y memoria
para generar un informe estructurado de calidad, problemas detectados
y recomendaciones para futuras ejecuciones.
"""

import json
import logging
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from openai import AsyncOpenAI
from pydantic import ValidationError

from backend.shared.models import (
    OutcomeJudgeReport,
    OutcomeSubGoalReview,
    OutcomeGlobalReview,
)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.shared.models import ReasoningSpotlight, PlannerHints, StepResult
    from backend.agents.execution_plan import ExecutionPlan
    from backend.memory import MemoryStore

from backend.config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_OUTCOME_JUDGE = """
Eres un evaluador experto de ejecuciones de un agente web automatizado. Tu tarea es analizar
una ejecución completa y generar un informe estructurado de calidad, problemas detectados
y recomendaciones para futuras ejecuciones.

Tu respuesta DEBE ser un objeto JSON con la siguiente estructura:
{
    "goal": "string",
    "execution_profile_name": "string" | null,
    "context_strategies": ["string"] | null,
    "global_review": {
        "overall_success": bool | null,
        "global_score": float | null,  // 0.0–1.0
        "main_issues": ["string"],
        "main_strengths": ["string"],
        "recommendations": ["string"]
    } | null,
    "sub_goals": [
        {
            "sub_goal_index": int,
            "sub_goal_text": "string",
            "success": bool | null,
            "score": float | null,  // 0.0–1.0
            "issues": ["string"],
            "warnings": ["string"],
            "strengths": ["string"],
            "suggested_retries": bool | null,
            "suggested_profile": "fast" | "balanced" | "thorough" | null,
            "suggested_changes": "string" | null
        }
    ],
    "next_run_profile_suggestion": "fast" | "balanced" | "thorough" | null,
    "next_run_notes": "string" | null,
    "llm_raw_notes": "string" | null
}

Instrucciones detalladas:
1. **goal, execution_profile_name, context_strategies**: Copia estos campos directamente de la entrada.

2. **global_review**: Evalúa la ejecución completa:
   - overall_success: ¿Se cumplió el objetivo general? (true/false/null si no está claro)
   - global_score: Puntuación global de 0.0 a 1.0 (0.0 = fallo total, 1.0 = éxito perfecto)
   - main_issues: Lista de problemas principales detectados (ej. "Muchos retries en subidas de archivos", "Errores recurrentes en formularios")
   - main_strengths: Lista de fortalezas principales (ej. "Navegación fluida", "Confirmaciones visuales exitosas")
   - recommendations: Recomendaciones de alto nivel (ej. "Considerar usar perfil 'thorough' para subidas de archivos", "Aumentar timeouts en formularios")

3. **sub_goals**: Para cada sub-objetivo ejecutado:
   - sub_goal_index: El índice original del sub-objetivo
   - sub_goal_text: El texto del sub-objetivo
   - success: ¿Se cumplió este sub-objetivo? (true/false/null)
   - score: Puntuación de 0.0 a 1.0 para este sub-objetivo
   - issues: Lista de problemas específicos detectados (ej. "Upload falló 3 veces", "No se confirmó visualmente")
   - warnings: Advertencias menores (ej. "Tiempo de ejecución alto", "Muchos pasos necesarios")
   - strengths: Fortalezas específicas (ej. "Navegación eficiente", "Confirmación visual exitosa")
   - suggested_retries: ¿Recomiendas reintentar este sub-objetivo en el futuro? (true/false/null)
   - suggested_profile: ¿Recomiendas cambiar a otro perfil para este sub-objetivo? ("fast"/"balanced"/"thorough"/null)
   - suggested_changes: Texto breve con sugerencias específicas para mejorar este sub-objetivo

4. **next_run_profile_suggestion**: Si recomiendas cambiar el perfil global para la próxima ejecución similar.

5. **next_run_notes**: Notas útiles para la próxima vez que se intente algo similar (ej. "Esta plataforma requiere más tiempo de espera", "Los uploads suelen fallar en esta página").

6. **llm_raw_notes**: Un breve resumen (2-3 líneas) de tu razonamiento general.

Contexto adicional proporcionado:
- ExecutionPlan: Plan original con sub-objetivos y estrategias
- Steps: Timeline de pasos ejecutados con acciones, observaciones y errores
- Metrics: Estadísticas de ejecución (retries, uploads, visual confirmations, etc.)
- PlannerHints: Recomendaciones previas del LLM sobre el plan
- ReasoningSpotlight: Análisis previo de ambigüedades y riesgos
- Memory: Historial de ejecuciones previas (si disponible)

Ejemplo de objetivo: "Sube el documento de reconocimiento médico para Juan Pérez en la plataforma Ecoordina"
"""


async def build_outcome_judge_report(
    llm_client: AsyncOpenAI,
    goal: str,
    execution_plan: Optional["ExecutionPlan"],
    steps: List["StepResult"],
    final_answer: str,
    metrics_summary: Optional[Dict[str, Any]],
    planner_hints: Optional["PlannerHints"],
    spotlight: Optional["ReasoningSpotlight"],
    memory_store: Optional["MemoryStore"] = None,
    platform: Optional[str] = None,
    company_name: Optional[str] = None,
) -> OutcomeJudgeReport:
    """
    Genera un informe de Outcome Judge basado en la ejecución completa.
    
    Args:
        llm_client: Cliente LLM asíncrono.
        goal: El objetivo original del usuario.
        execution_plan: El plan de ejecución generado (si existe).
        steps: Lista de pasos ejecutados.
        final_answer: La respuesta final del agente.
        metrics_summary: Resumen de métricas de ejecución.
        planner_hints: Recomendaciones previas del LLM sobre el plan.
        spotlight: El Reasoning Spotlight (análisis previo del objetivo).
        memory_store: Instancia de MemoryStore para acceder a la memoria persistente.
        platform: Nombre de la plataforma (si aplica, para memoria).
        company_name: Nombre de la empresa (si aplica, para memoria).
    
    Returns:
        Un objeto OutcomeJudgeReport con la evaluación del LLM.
    """
    logger.info(f"[OutcomeJudge] Building report for goal: {goal}")
    
    # Preparar contexto para el LLM
    context_info: Dict[str, Any] = {
        "goal": goal,
        "final_answer": final_answer,
        "execution_plan": execution_plan.to_dict() if execution_plan else None,
        "steps_summary": _build_steps_summary(steps),
        "metrics_summary": metrics_summary or {},
        "planner_hints": planner_hints.model_dump() if planner_hints else None,
        "reasoning_spotlight": spotlight.model_dump() if spotlight else None,
    }
    
    # Añadir información de memoria si está disponible
    if memory_store:
        memory_context: Dict[str, Any] = {}
        if company_name:
            company_mem = memory_store.load_company(company_name, platform)
            if company_mem:
                memory_context["company_memory"] = company_mem.model_dump()
        if platform:
            platform_mem = memory_store.load_platform(platform)
            if platform_mem:
                memory_context["platform_memory"] = platform_mem.model_dump()
        if memory_context:
            context_info["persistent_memory"] = memory_context
    
    # Extraer execution_profile_name y context_strategies del plan o métricas
    execution_profile_name = None
    context_strategies = None
    if execution_plan:
        execution_profile_name = execution_plan.execution_profile.get("name") if execution_plan.execution_profile else None
        context_strategies = execution_plan.context_strategies
    elif metrics_summary:
        # Intentar extraer del summary si no hay plan
        profile_info = metrics_summary.get("summary", {}).get("execution_profile", {})
        execution_profile_name = profile_info.get("name") if isinstance(profile_info, dict) else None
    
    user_content = f"""
    Analiza la siguiente ejecución completa del agente y genera un informe estructurado de evaluación.
    
    Contexto:
    {json.dumps(context_info, indent=2, ensure_ascii=False)}
    
    Genera la respuesta en formato JSON siguiendo estrictamente el SYSTEM_PROMPT.
    """
    
    try:
        response = await llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_OUTCOME_JUDGE},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            response_model=OutcomeJudgeReport,  # Usar Pydantic para validación
        )
        
        report = response
        
        # Asegurar que goal, execution_profile_name y context_strategies están correctos
        report.goal = goal
        report.execution_profile_name = execution_profile_name
        report.context_strategies = context_strategies
        
        # Filtrar sub-goals con índices fuera de rango (si hay execution_plan)
        if execution_plan:
            valid_sub_goal_indices = {sg.index for sg in execution_plan.sub_goals}
            report.sub_goals = [
                sg for sg in report.sub_goals if sg.sub_goal_index in valid_sub_goal_indices
            ]
        
        logger.info(f"[OutcomeJudge] Report built for goal: {goal}")
        return report
        
    except ValidationError as e:
        logger.warning(f"[OutcomeJudge] LLM returned invalid JSON for goal '{goal}': {e}", exc_info=True)
        return OutcomeJudgeReport(
            goal=goal,
            execution_profile_name=execution_profile_name,
            context_strategies=context_strategies,
            llm_raw_notes=f"Error de validación en la respuesta del LLM: {e}\nOutput original: {getattr(e, 'raw_output', 'N/A')}"
        )
    except Exception as e:
        logger.warning(f"[OutcomeJudge] Error building report for goal '{goal}': {e}", exc_info=True)
        return OutcomeJudgeReport(
            goal=goal,
            execution_profile_name=execution_profile_name,
            context_strategies=context_strategies,
            llm_raw_notes=f"Fallo en la generación de Outcome Judge Report: {e}"
        )


def _build_steps_summary(steps: List["StepResult"]) -> List[Dict[str, Any]]:
    """
    Construye un resumen comprimido de los pasos para el LLM.
    
    Args:
        steps: Lista de StepResult completos.
    
    Returns:
        Lista de diccionarios con información resumida de cada paso.
    """
    summary = []
    for i, step in enumerate(steps, start=1):
        step_info: Dict[str, Any] = {
            "step_number": i,
            "action_type": step.last_action.type if step.last_action else None,
            "url": step.observation.url,
            "title": step.observation.title,
            "error": step.error,
        }
        
        # Extraer información relevante del info dict
        if step.info:
            if "sub_goal_index" in step.info:
                step_info["sub_goal_index"] = step.info["sub_goal_index"]
            if "early_stop_reason" in step.info:
                step_info["early_stop_reason"] = step.info["early_stop_reason"]
            if "upload_summary" in step.info:
                step_info["upload_summary"] = step.info["upload_summary"]
            if "visual_action" in step.info:
                step_info["visual_action"] = step.info["visual_action"]
            if "retry_count" in step.info:
                step_info["retry_count"] = step.info["retry_count"]
        
        summary.append(step_info)
    
    return summary




