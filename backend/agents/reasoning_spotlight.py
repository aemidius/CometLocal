"""
Motor de Reasoning Spotlight para análisis previo de objetivos.

v3.8.0: Analiza el objetivo del usuario antes de planificar o ejecutar,
identificando ambigüedades, generando interpretaciones alternativas,
detectando riesgos y proponiendo preguntas de clarificación.
"""

import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from backend.config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL
from backend.shared.models import (
    ReasoningSpotlight,
    ReasoningInterpretation,
    ReasoningAmbiguity,
    ReasoningQuestion,
)
from backend.agents.execution_profile import ExecutionProfile

logger = logging.getLogger(__name__)


REASONING_SPOTLIGHT_SYSTEM_PROMPT = """Eres un analista de objetivos para un agente autónomo de navegación web.

Tu tarea es analizar el objetivo que el usuario quiere que el agente ejecute y generar un "Reasoning Spotlight"
que incluya:

1. **Interpretaciones alternativas** (al menos 2): Diferentes formas de entender el objetivo, cada una con un nivel de confianza (0.0-1.0).

2. **Ambigüedades detectadas**: Identifica áreas donde el objetivo es vago, poco claro o ambiguo. Clasifica cada ambigüedad como:
   - "low": Ambigüedad menor que no impedirá la ejecución
   - "medium": Ambigüedad moderada que podría causar confusión
   - "high": Ambigüedad crítica que podría llevar a acciones incorrectas

   Ejemplos de ambigüedades:
   - Términos vagos: "revisa los documentos" (¿qué documentos?)
   - Falta de identificadores: "sube el documento" (¿cuál documento? ¿de quién?)
   - Acciones imposibles sin contexto: "entra en la plataforma" (¿qué plataforma? ¿qué credenciales?)
   - Referencias ambiguas: "el trabajador" (¿cuál trabajador si hay varios?)

3. **Preguntas de clarificación** (0-3): Solo si el modo es interactivo (no batch). Preguntas que ayudarían a desambiguar el objetivo.

4. **Riesgos percibidos**: Lista de riesgos potenciales, como:
   - Ambigüedad crítica que podría llevar a acciones incorrectas
   - Request que podría afectar a datos incorrectos
   - Subidas sin confirmar trabajador/empresa
   - Confusión entre plataformas
   - Acciones destructivas sin confirmación

5. **Notas del LLM**: Breve razonamiento (2-3 líneas) explicando cómo entiendes el objetivo.

Responde SOLO con un objeto JSON válido con esta estructura:
{
  "interpretations": [
    {"interpretation": "descripción", "confidence": 0.85},
    {"interpretation": "descripción alternativa", "confidence": 0.70}
  ],
  "ambiguities": [
    {"description": "descripción de la ambigüedad", "severity": "medium"}
  ],
  "recommended_questions": [
    {"question": "¿Qué documento específicamente?", "rationale": "El objetivo no especifica qué documento subir"}
  ],
  "perceived_risks": [
    "Riesgo 1",
    "Riesgo 2"
  ],
  "llm_notes": "Breve explicación de 2-3 líneas sobre cómo entiendo el objetivo"
}

IMPORTANTE:
- Si el modo es "batch", NO generes preguntas de clarificación (recommended_questions debe ser []).
- Si el modo es "interactive", puedes generar 1-3 preguntas.
- Genera al menos 2 interpretaciones.
- Sé específico y útil en las ambigüedades y riesgos.
"""


async def build_reasoning_spotlight(
    raw_goal: str,
    execution_profile: Optional[ExecutionProfile] = None,
    is_batch: bool = False,
) -> ReasoningSpotlight:
    """
    Construye un Reasoning Spotlight analizando el objetivo del usuario.
    
    v3.8.0: Genera interpretaciones alternativas, detecta ambigüedades, propone preguntas
    de clarificación, identifica riesgos y produce notas del LLM sobre cómo entiende el objetivo.
    
    Args:
        raw_goal: El objetivo original del usuario
        execution_profile: Perfil de ejecución (opcional, para determinar si es interactivo)
        is_batch: Si es True, no se generarán preguntas de clarificación
        
    Returns:
        ReasoningSpotlight con el análisis completo
    """
    # Inicializar cliente LLM
    client = AsyncOpenAI(
        base_url=LLM_API_BASE,
        api_key=LLM_API_KEY,
    )
    
    # Determinar si es modo interactivo
    is_interactive = not is_batch
    if execution_profile:
        # Si el perfil es batch, forzar is_batch
        if execution_profile.mode == "batch":
            is_interactive = False
        elif execution_profile.mode in ["interactive", "fast", "balanced", "thorough"]:
            is_interactive = True
    
    mode_text = "batch" if not is_interactive else "interactive"
    
    user_content = f"""OBJETIVO DEL USUARIO:
{raw_goal}

MODO: {mode_text}

Analiza este objetivo y genera el Reasoning Spotlight según las instrucciones.
{"IMPORTANTE: Como es modo batch, NO generes preguntas de clarificación." if not is_interactive else "Puedes generar 1-3 preguntas de clarificación si son útiles."}
"""

    try:
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": REASONING_SPOTLIGHT_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,  # Temperatura más baja para análisis más consistente
        )
        content = response.choices[0].message.content or ""
    except Exception as e:
        logger.warning(f"[reasoning-spotlight] Error al generar spotlight: {e}")
        # Devolver spotlight vacío pero válido en caso de error
        return ReasoningSpotlight(
            raw_goal=raw_goal,
            interpretations=[
                ReasoningInterpretation(
                    interpretation=f"Interpretación por defecto: {raw_goal}",
                    confidence=0.5,
                )
            ],
            ambiguities=[],
            recommended_questions=[],
            perceived_risks=[],
            llm_notes="No se pudo generar análisis automático debido a un error.",
        )
    
    # Parsear respuesta JSON
    try:
        # Limpiar el contenido (puede tener markdown code blocks)
        content_clean = content.strip()
        if content_clean.startswith("```json"):
            content_clean = content_clean[7:]
        elif content_clean.startswith("```"):
            content_clean = content_clean[3:]
        if content_clean.endswith("```"):
            content_clean = content_clean[:-3]
        content_clean = content_clean.strip()
        
        obj = json.loads(content_clean)
        
        # Validar y construir interpretaciones
        interpretations = []
        if "interpretations" in obj and isinstance(obj["interpretations"], list):
            for interp in obj["interpretations"]:
                if isinstance(interp, dict) and "interpretation" in interp:
                    confidence = float(interp.get("confidence", 0.5))
                    # Asegurar que la confianza está en [0, 1]
                    confidence = max(0.0, min(1.0, confidence))
                    interpretations.append(
                        ReasoningInterpretation(
                            interpretation=interp["interpretation"],
                            confidence=confidence,
                        )
                    )
        
        # Si no hay interpretaciones válidas, crear una por defecto
        if len(interpretations) < 2:
            interpretations.append(
                ReasoningInterpretation(
                    interpretation=f"Interpretación principal: {raw_goal}",
                    confidence=0.7,
                )
            )
            if len(interpretations) == 1:
                interpretations.append(
                    ReasoningInterpretation(
                        interpretation=f"Interpretación alternativa: Ejecutar el objetivo tal como está expresado",
                        confidence=0.5,
                    )
                )
        
        # Validar y construir ambigüedades
        ambiguities = []
        if "ambiguities" in obj and isinstance(obj["ambiguities"], list):
            for amb in obj["ambiguities"]:
                if isinstance(amb, dict) and "description" in amb:
                    severity = amb.get("severity", "medium")
                    if severity not in ["low", "medium", "high"]:
                        severity = "medium"
                    ambiguities.append(
                        ReasoningAmbiguity(
                            description=amb["description"],
                            severity=severity,
                        )
                    )
        
        # Validar y construir preguntas de clarificación
        recommended_questions = []
        if is_interactive and "recommended_questions" in obj and isinstance(obj["recommended_questions"], list):
            for q in obj["recommended_questions"]:
                if isinstance(q, dict) and "question" in q:
                    recommended_questions.append(
                        ReasoningQuestion(
                            question=q["question"],
                            rationale=q.get("rationale"),
                        )
                    )
        # Si es batch, asegurar que no hay preguntas
        if not is_interactive:
            recommended_questions = []
        
        # Validar y construir riesgos percibidos
        perceived_risks = []
        if "perceived_risks" in obj and isinstance(obj["perceived_risks"], list):
            for risk in obj["perceived_risks"]:
                if isinstance(risk, str) and risk.strip():
                    perceived_risks.append(risk.strip())
        
        # Notas del LLM
        llm_notes = None
        if "llm_notes" in obj and isinstance(obj["llm_notes"], str):
            llm_notes = obj["llm_notes"].strip()
        
        return ReasoningSpotlight(
            raw_goal=raw_goal,
            interpretations=interpretations,
            ambiguities=ambiguities,
            recommended_questions=recommended_questions,
            perceived_risks=perceived_risks,
            llm_notes=llm_notes,
        )
        
    except json.JSONDecodeError as e:
        logger.warning(f"[reasoning-spotlight] Error al parsear JSON del LLM: {e}")
        logger.debug(f"[reasoning-spotlight] Contenido recibido: {content[:500]}")
        # Devolver spotlight con interpretación por defecto
        return ReasoningSpotlight(
            raw_goal=raw_goal,
            interpretations=[
                ReasoningInterpretation(
                    interpretation=f"Interpretación por defecto: {raw_goal}",
                    confidence=0.5,
                ),
                ReasoningInterpretation(
                    interpretation="No se pudo analizar el objetivo automáticamente",
                    confidence=0.3,
                ),
            ],
            ambiguities=[
                ReasoningAmbiguity(
                    description="No se pudo analizar el objetivo automáticamente para detectar ambigüedades",
                    severity="medium",
                )
            ],
            recommended_questions=[],
            perceived_risks=["Error al analizar el objetivo automáticamente"],
            llm_notes="Error al procesar el análisis automático del objetivo.",
        )
    except Exception as e:
        logger.error(f"[reasoning-spotlight] Error inesperado: {e}", exc_info=True)
        # Devolver spotlight básico
        return ReasoningSpotlight(
            raw_goal=raw_goal,
            interpretations=[
                ReasoningInterpretation(
                    interpretation=f"Interpretación por defecto: {raw_goal}",
                    confidence=0.5,
                )
            ],
            ambiguities=[],
            recommended_questions=[],
            perceived_risks=[],
            llm_notes=None,
        )



