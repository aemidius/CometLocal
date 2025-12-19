"""
Módulo para generar Planner Hints: recomendaciones del LLM sobre el plan de ejecución.

v4.0.0: El LLM revisa el objetivo, ReasoningSpotlight, ExecutionPlan y memoria
para generar sugerencias sobre qué sub-objetivos son críticos, qué riesgos ve,
si recomienda cambiar el perfil de ejecución, etc.
"""

import json
import logging
from typing import Optional, Dict, Any

from openai import AsyncOpenAI

from backend.shared.models import (
    PlannerHints,
    PlannerHintSubGoal,
    PlannerHintProfileSuggestion,
    PlannerHintGlobal,
)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.shared.models import ReasoningSpotlight
from backend.agents.execution_plan import ExecutionPlan
from backend.memory import MemoryStore
from backend.config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_PLANNER_HINTS = """
Eres un revisor experto de planes de ejecución para un agente web automatizado. Tu tarea es analizar
un plan de ejecución propuesto y generar recomendaciones útiles antes de que se ejecute.

Tu respuesta DEBE ser un objeto JSON con la siguiente estructura:
{
    "sub_goals": [
        {
            "sub_goal_index": int,
            "sub_goal_text": "string",
            "suggested_enabled": bool | null,  // true = recomienda ejecutar, false = recomienda NO ejecutar, null = sin opinión
            "priority": "low" | "medium" | "high" | null,
            "risk_level": "low" | "medium" | "high" | null,
            "rationale": "string" | null
        }
    ],
    "profile_suggestion": {
        "suggested_profile": "fast" | "balanced" | "thorough" | null,
        "rationale": "string" | null
    } | null,
    "global_insights": {
        "summary": "string" | null,
        "risks": ["string"],
        "opportunities": ["string"]
    } | null,
    "llm_raw_notes": "string" | null
}

Instrucciones detalladas:
1. **sub_goals**: Analiza cada sub-objetivo del plan. Para cada uno:
   - Asigna una prioridad (low/medium/high) si es relevante
   - Evalúa el nivel de riesgo (low/medium/high) si hay posibles problemas
   - Sugiere si debería ejecutarse (suggested_enabled: true/false) solo si tienes una recomendación clara
   - Proporciona un rationale breve explicando tu razonamiento
   - Si un sub-objetivo parece redundante, peligroso o poco útil, marca suggested_enabled: false
   - Si un sub-objetivo es crítico, marca priority: "high" y suggested_enabled: true

2. **profile_suggestion**: Evalúa si el perfil de ejecución actual (fast/balanced/thorough) es adecuado:
   - Si el plan es simple y directo, sugiere "fast"
   - Si hay ambigüedades o complejidad, sugiere "balanced" o "thorough"
   - Si hay memoria de errores previos, considera un perfil más cuidadoso
   - Proporciona rationale explicando por qué

3. **global_insights**: Proporciona una visión general:
   - summary: Resumen breve (2-3 líneas) del análisis
   - risks: Lista de riesgos globales que podrían afectar la ejecución
   - opportunities: Lista de oportunidades (ej. reutilizar contexto, agrupar tareas, etc.)

4. **llm_raw_notes**: Incluye notas internas de tu razonamiento (opcional, para diagnóstico)

IMPORTANTE:
- Si un sub_goal_index no existe en el plan, ignóralo (no lo incluyas en la respuesta)
- Si no tienes una recomendación clara para algo, usa null
- Sé conciso pero útil
- Prioriza la seguridad y evitar errores costosos
"""


async def build_planner_hints(
    llm_client: AsyncOpenAI,
    goal: str,
    execution_plan: ExecutionPlan,
    spotlight: Optional["ReasoningSpotlight"],
    memory_store: Optional[MemoryStore],
    platform: Optional[str] = None,
    company_name: Optional[str] = None,
) -> PlannerHints:
    """
    Genera recomendaciones del LLM sobre el plan de ejecución.
    
    v4.0.0: Revisa el objetivo, ReasoningSpotlight, ExecutionPlan y memoria
    para generar sugerencias sobre qué sub-objetivos son críticos, qué riesgos ve,
    si recomienda cambiar el perfil de ejecución, etc.
    
    Args:
        llm_client: Cliente LLM asíncrono
        goal: Objetivo original del usuario
        execution_plan: Plan de ejecución generado
        spotlight: ReasoningSpotlight (análisis previo del objetivo)
        memory_store: MemoryStore para acceder a memoria persistente (opcional)
        platform: Nombre de la plataforma (opcional, para cargar memoria)
        company_name: Nombre de la empresa (opcional, para cargar memoria)
        
    Returns:
        PlannerHints con recomendaciones del LLM
    """
    logger.info(f"[PlannerHints] Building hints for goal: {goal}")
    
    # Construir contexto para el LLM
    plan_dict = execution_plan.to_dict()
    
    # Preparar información de memoria si está disponible
    memory_summary: Dict[str, Any] = {}
    if memory_store:
        try:
            if company_name:
                company_memory = memory_store.load_company(company_name, platform)
                if company_memory:
                    memory_summary["company"] = {
                        "required_docs_counts": dict(company_memory.required_docs_counts),
                        "missing_docs_counts": dict(company_memory.missing_docs_counts),
                        "upload_error_counts": dict(company_memory.upload_error_counts),
                        "notes": company_memory.notes,
                    }
            
            if platform:
                platform_memory = memory_store.load_platform(platform)
                if platform_memory:
                    memory_summary["platform"] = {
                        "visual_click_usage": platform_memory.visual_click_usage,
                        "visual_recovery_usage": platform_memory.visual_recovery_usage,
                        "upload_error_counts": platform_memory.upload_error_counts,
                        "ocr_usage": platform_memory.ocr_usage,
                        "notes": platform_memory.notes,
                    }
        except Exception as e:
            logger.warning(f"[PlannerHints] Error loading memory: {e}")
    
    # Preparar información de spotlight
    spotlight_summary: Optional[Dict[str, Any]] = None
    if spotlight:
        spotlight_summary = {
            "interpretations": [
                {"interpretation": interp.interpretation, "confidence": interp.confidence}
                for interp in spotlight.interpretations
            ],
            "ambiguities": [
                {"description": amb.description, "severity": amb.severity}
                for amb in spotlight.ambiguities
            ],
            "perceived_risks": spotlight.perceived_risks,
            "llm_notes": spotlight.llm_notes,
        }
    
    # Construir prompt para el LLM
    user_content = f"""
Analiza el siguiente plan de ejecución y genera recomendaciones.

OBJETIVO ORIGINAL:
{goal}

PLAN DE EJECUCIÓN:
{json.dumps(plan_dict, indent=2, ensure_ascii=False)}

PERFIL DE EJECUCIÓN ACTUAL:
{execution_plan.execution_profile.get('name', 'balanced')}

ESTRATEGIAS DE CONTEXTO:
{', '.join(execution_plan.context_strategies) if execution_plan.context_strategies else 'Ninguna específica'}
"""
    
    if spotlight_summary:
        user_content += f"""

ANÁLISIS PREVIO DEL OBJETIVO (ReasoningSpotlight):
{json.dumps(spotlight_summary, indent=2, ensure_ascii=False)}
"""
    
    if memory_summary:
        user_content += f"""

MEMORIA PERSISTENTE (historial previo):
{json.dumps(memory_summary, indent=2, ensure_ascii=False)}
"""
    
    user_content += """

Genera recomendaciones siguiendo las instrucciones del SYSTEM_PROMPT.
Responde SOLO con el objeto JSON, sin texto adicional.
"""
    
    try:
        # v4.7 FIX: Usar response_format={"type": "text"} para evitar errores de compatibilidad
        # Luego parsear JSON de forma tolerante
        response = await llm_client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_PLANNER_HINTS},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            response_format={"type": "text"},
        )
    except (TypeError, ValueError, AttributeError) as e:
        # Capturar errores específicos de response_format.type incompatibility
        error_msg = str(e).lower()
        if "response_format" in error_msg or "type" in error_msg:
            logger.info("[PlannerHints] disabled due to response_format incompatibility, trying without response_format")
            # Intentar sin response_format
            try:
                response = await llm_client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT_PLANNER_HINTS},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=0.3,
                )
            except Exception as e2:
                logger.warning(f"[PlannerHints] Error al llamar LLM: {e2}")
                # Devolver PlannerHints vacío sin traceback ruidoso
                return PlannerHints(
                    goal=goal,
                    execution_profile_name=execution_plan.execution_profile.get("name"),
                    context_strategies=execution_plan.context_strategies,
                    sub_goals=[],
                    profile_suggestion=None,
                    global_insights=None,
                    llm_raw_notes=None,
                )
        else:
            # Si no es un error de response_format, re-lanzar para el catch general
            raise
    
    try:
        # Parsear respuesta JSON de forma tolerante
        response_text = response.choices[0].message.content
        if not response_text:
            logger.warning("[PlannerHints] Empty response from LLM")
            return PlannerHints(
                goal=goal,
                execution_profile_name=execution_plan.execution_profile.get("name"),
                context_strategies=execution_plan.context_strategies,
                sub_goals=[],
                profile_suggestion=None,
                global_insights=None,
                llm_raw_notes=None,
            )
        
        # Intentar extraer JSON del texto (puede venir con markdown o texto adicional)
        import re
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(0)
        
        response_data = json.loads(response_text)
        
        # Validar y filtrar sub-goals con índices fuera de rango
        valid_sub_goals = []
        plan_sub_goal_indices = {sg.index for sg in execution_plan.sub_goals}
        
        for sg_data in response_data.get("sub_goals", []):
            sub_goal_index = sg_data.get("sub_goal_index")
            if sub_goal_index is not None and sub_goal_index in plan_sub_goal_indices:
                # Encontrar el texto del sub-goal correspondiente
                sub_goal_text = next(
                    (sg.sub_goal for sg in execution_plan.sub_goals if sg.index == sub_goal_index),
                    sg_data.get("sub_goal_text", "")
                )
                
                valid_sub_goals.append(
                    PlannerHintSubGoal(
                        sub_goal_index=sub_goal_index,
                        sub_goal_text=sub_goal_text,
                        suggested_enabled=sg_data.get("suggested_enabled"),
                        priority=sg_data.get("priority"),
                        risk_level=sg_data.get("risk_level"),
                        rationale=sg_data.get("rationale"),
                    )
                )
            else:
                logger.debug(f"[PlannerHints] Ignoring out-of-range sub_goal_index: {sub_goal_index}")
        
        # Construir profile_suggestion
        profile_suggestion = None
        if response_data.get("profile_suggestion"):
            ps_data = response_data["profile_suggestion"]
            profile_suggestion = PlannerHintProfileSuggestion(
                suggested_profile=ps_data.get("suggested_profile"),
                rationale=ps_data.get("rationale"),
            )
        
        # Construir global_insights
        global_insights = None
        if response_data.get("global_insights"):
            gi_data = response_data["global_insights"]
            global_insights = PlannerHintGlobal(
                summary=gi_data.get("summary"),
                risks=gi_data.get("risks", []),
                opportunities=gi_data.get("opportunities", []),
            )
        
        # Construir PlannerHints
        hints = PlannerHints(
            goal=goal,
            execution_profile_name=execution_plan.execution_profile.get("name"),
            context_strategies=execution_plan.context_strategies,
            sub_goals=valid_sub_goals,
            profile_suggestion=profile_suggestion,
            global_insights=global_insights,
            llm_raw_notes=response_data.get("llm_raw_notes") or response_text[:500],  # Limitar tamaño
        )
        
        logger.info(f"[PlannerHints] Generated {len(valid_sub_goals)} sub-goal hints")
        return hints
        
    except json.JSONDecodeError as e:
        logger.warning(f"[PlannerHints] Failed to parse LLM response as JSON: {e}")
        # Crear PlannerHints mínimo con el texto original
        return PlannerHints(
            goal=goal,
            execution_profile_name=execution_plan.execution_profile.get("name"),
            context_strategies=execution_plan.context_strategies,
            sub_goals=[],
            profile_suggestion=None,
            global_insights=None,
            llm_raw_notes=response_text if 'response_text' in locals() else f"Error parsing JSON: {e}",
        )
    except Exception as e:
        logger.warning(f"[PlannerHints] Error building hints: {e}", exc_info=True)
        # Crear PlannerHints vacío pero válido
        return PlannerHints(
            goal=goal,
            execution_profile_name=execution_plan.execution_profile.get("name"),
            context_strategies=execution_plan.context_strategies,
            sub_goals=[],
            profile_suggestion=None,
            global_insights=None,
            llm_raw_notes=f"Error generating hints: {e}",
        )

