import sys
import asyncio
from typing import Optional, List

# En Windows, necesitamos un event loop que soporte subprocess (para Playwright)
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.browser.browser import BrowserController
from backend.shared.models import (
    StepResult,
    AgentAnswerRequest,
    AgentAnswerResponse,
    SourceInfo,
    FileUploadInstructionDTO,
    BatchAgentRequest,
    BatchAgentResponse,
    CAEBatchRequest,
    CAEBatchResponse,
)
from backend.agents.agent_runner import run_simple_agent, run_llm_agent, run_llm_task_with_answer

app = FastAPI(title="CometLocal Backend")

# CORS abierto para desarrollo (luego afinaremos)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

browser = BrowserController()


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    agent_reply: str
    opened_url: Optional[str] = None
    status: str = "ok"


class AgentRunRequest(BaseModel):
    goal: str
    max_steps: int = 5


class AgentRunLLMRequest(BaseModel):
    goal: str
    max_steps: int = 8


@app.on_event("startup")
async def startup_event():
    # Arrancamos el navegador al iniciar la app
    await browser.start(headless=False)


@app.on_event("shutdown")
async def shutdown_event():
    # Cerramos el navegador al apagar la app
    await browser.close()


@app.get("/health")
async def health():
    return {"status": "ok", "detail": "CometLocal backend running con navegador"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    print("DEBUG: función chat NUEVA cargada ✅")
    """
    Intérprete simple de comandos:
      - "abre <url>"             -> abre una URL
      - "acepta cookies"         -> intenta aceptar cookies
      - "rechaza cookies"        -> intenta rechazar cookies
      - "haz click en <texto>"   -> hace click en un elemento con ese texto
      - "escribe <texto>"        -> escribe texto en el campo activo o más razonable
      - "pulsa enter"            -> pulsa Enter
      - "busca <algo> en google" -> abre Google (si hace falta) y busca
    """
    text = req.message.strip()
    opened_url: Optional[str] = None

    lower = text.lower()

    # 1) Abrir URL
    if lower.startswith("abre ") or lower.startswith("open "):

        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            candidate = parts[1].strip()
            if candidate.startswith("http://") or candidate.startswith("https://"):
                opened_url = candidate
                await browser.goto(candidate)
                reply = f"He abierto la URL: {candidate}"
            else:
                reply = (
                    f"He entendido que quieres abrir una URL, "
                    f"pero '{candidate}' no parece una URL válida."
                )
        else:
            reply = "Dime qué URL quieres que abra, por ejemplo: 'abre https://www.google.com'."

    # 2) Aceptar cookies
    elif "acepta cookies" in lower or "accept cookies" in lower:
        ok = await browser.accept_cookies()
        if ok:
            reply = "He intentado aceptar las cookies y he pulsado un botón de aceptar."
        else:
            reply = "He buscado botones para aceptar cookies, pero no he encontrado ninguno claro."

    # 3) Rechazar cookies
    elif "rechaza cookies" in lower or "reject cookies" in lower:
        ok = await browser.reject_cookies()
        if ok:
            reply = "He intentado rechazar las cookies y he pulsado un botón de rechazar."
        else:
            reply = "He buscado botones para rechazar cookies, pero no he encontrado ninguno claro."

    # 4) Google search: "busca ... en google"
    elif lower.startswith("busca ") and " en google" in lower:
        start_idx = lower.find("busca ") + len("busca ")
        end_idx = lower.rfind(" en google")
        if end_idx > start_idx:
            query = text[start_idx:end_idx].strip().strip('"')
            ok = await browser.google_search(query)
            if ok:
                reply = f"He buscado '{query}' en Google."
            else:
                reply = "He intentado buscar en Google, pero algo ha fallado."
        else:
            reply = "No he entendido bien qué quieres buscar en Google."

    # 5) Click en un elemento por texto
    elif lower.startswith("haz click en ") or lower.startswith("clic en ") or lower.startswith("click en "):
        label = text
        for prefix in ("haz click en ", "clic en ", "click en "):
            if lower.startswith(prefix):
                label = text[len(prefix):].strip().strip('"')
                break

        if not label:
            reply = "Dime sobre qué texto quieres hacer click."
        else:
            ok = await browser.click_by_text(label)
            if ok:
                reply = f"He intentado hacer click en un elemento con texto parecido a '{label}'."
            else:
                reply = f"No he encontrado ningún elemento claro para hacer click con texto '{label}'."

    # 6) Escribir texto
    elif lower.startswith("escribe ") or lower.startswith("escriba "):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            reply = "Dime qué quieres que escriba, por ejemplo: 'escribe hola mundo'."
        else:
            to_type = parts[1].strip().strip('"')
            ok = await browser.type_text(to_type)
            if ok:
                reply = f"He escrito: '{to_type}'."
            else:
                reply = "He intentado escribir, pero no he encontrado ningún campo de texto adecuado."

    # 7) Pulsar Enter
    elif "pulsa enter" in lower or "presiona enter" in lower or "press enter" in lower:
        await browser.press_enter()
        reply = "He pulsado la tecla Enter."

    # 8) Resto: respuesta simple
    else:
        reply = (
            f"He recibido tu mensaje: '{text}'. "
            "De momento entiendo: 'abre <url>', 'acepta cookies', 'rechaza cookies', " 
            "'haz click en <texto>', 'escribe <texto>', 'pulsa enter' y 'busca <algo> en google'."
        )

    return ChatResponse(agent_reply=reply, opened_url=opened_url)


@app.post("/agent/run", response_model=List[StepResult])
async def run_agent_endpoint(payload: AgentRunRequest):
    """
    Runs the simple agent with the given goal.
    Returns a list of step results showing the agent's execution.
    """
    steps = await run_simple_agent(
        goal=payload.goal,
        browser=browser,
        max_steps=payload.max_steps,
    )
    return steps


@app.post("/agent/run_llm", response_model=List[StepResult])
async def run_llm_agent_endpoint(payload: AgentRunLLMRequest):
    """
    Runs the LLM-based agent with the given goal.
    Returns a list of step results showing the agent's execution.
    """
    steps = await run_llm_agent(
        goal=payload.goal,
        browser=browser,
        max_steps=payload.max_steps,
    )
    return steps


@app.post("/agent/answer", response_model=AgentAnswerResponse)
async def agent_answer_endpoint(payload: AgentAnswerRequest):
    """
    Runs the LLM-based agent and generates a final natural-language answer
    based on the last observation and the original goal.
    """
    # v2.8.0: Manejar flujo de planificación
    from backend.agents.agent_runner import build_execution_plan, _decompose_goal, ExecutionProfile
    from backend.agents.document_repository import DocumentRepository
    from backend.agents.context_strategies import build_context_strategies, DEFAULT_CONTEXT_STRATEGIES
    from backend.config import DOCUMENT_REPOSITORY_BASE_DIR, DEFAULT_CAE_BASE_URL
    from pathlib import Path
    
    # v3.8.0: Generar Reasoning Spotlight antes de planificar o ejecutar
    reasoning_spotlight = None
    # v4.0.0: Planner Hints (se genera en plan_only, pero inicializamos aquí)
    planner_hints = None
    try:
        from backend.agents.reasoning_spotlight import build_reasoning_spotlight
        
        # Determinar ExecutionProfile para el spotlight
        if payload.execution_profile_name:
            valid_profiles = {"fast", "balanced", "thorough"}
            if payload.execution_profile_name in valid_profiles:
                if payload.execution_profile_name == "fast":
                    execution_profile = ExecutionProfile.fast()
                elif payload.execution_profile_name == "thorough":
                    execution_profile = ExecutionProfile.thorough()
                else:
                    execution_profile = ExecutionProfile.default()
            else:
                execution_profile = ExecutionProfile.from_goal_text(payload.goal)
        else:
            execution_profile = ExecutionProfile.from_goal_text(payload.goal)
        
        # Generar spotlight (no es batch, es endpoint interactivo)
        reasoning_spotlight = await build_reasoning_spotlight(
            raw_goal=payload.goal,
            execution_profile=execution_profile,
            is_batch=False,
        )
    except Exception as e:
        logger.warning(f"[agent-answer] Error al generar Reasoning Spotlight: {e}", exc_info=True)
        # Continuar sin spotlight si hay error
    
    if payload.plan_only:
        # Solo generar y devolver el plan, NO ejecutar
        # Determinar ExecutionProfile
        if payload.execution_profile_name:
            valid_profiles = {"fast", "balanced", "thorough"}
            if payload.execution_profile_name in valid_profiles:
                if payload.execution_profile_name == "fast":
                    execution_profile = ExecutionProfile.fast()
                elif payload.execution_profile_name == "thorough":
                    execution_profile = ExecutionProfile.thorough()
                else:
                    execution_profile = ExecutionProfile.default()
            else:
                execution_profile = ExecutionProfile.from_goal_text(payload.goal)
        else:
            execution_profile = ExecutionProfile.from_goal_text(payload.goal)
        
        # Construir estrategias de contexto
        strategy_names = payload.context_strategies if payload.context_strategies else [s.name for s in DEFAULT_CONTEXT_STRATEGIES]
        
        # Descomponer goal
        sub_goals = _decompose_goal(payload.goal)
        if not sub_goals:
            sub_goals = [payload.goal]
        
        # Obtener repositorio de documentos
        document_repository = DocumentRepository(Path(DOCUMENT_REPOSITORY_BASE_DIR))
        
        # Generar plan
        execution_plan = build_execution_plan(
            goal=payload.goal,
            sub_goals=sub_goals,
            execution_profile=execution_profile,
            context_strategies=strategy_names,
            document_repository=document_repository,
        )
        
        # v4.0.0: Generar Planner Hints si estamos en modo pre-flight
        planner_hints: Optional["PlannerHints"] = None
        if payload.plan_only and not is_batch_request:
            try:
                from backend.agents.llm_planner_hints import build_planner_hints
                # Construir MemoryStore si estamos en contexto CAE (opcional)
                memory_store = None
                platform = None
                company_name = None
                
                # Intentar extraer platform/company_name del goal si es contexto CAE
                goal_lower = payload.goal.lower()
                if "cae" in goal_lower or "plataforma" in goal_lower:
                    try:
                        from backend.memory import MemoryStore
                        from backend.config import MEMORY_BASE_DIR
                        memory_store = MemoryStore(MEMORY_BASE_DIR)
                        # TODO: Extraer platform y company_name del goal o de otro lugar si está disponible
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.debug(f"[app] Failed to initialize memory store for planner hints: {e}")
                
                planner_hints = await build_planner_hints(
                    llm_client=llm_client,
                    goal=payload.goal,
                    execution_plan=execution_plan,
                    spotlight=reasoning_spotlight,
                    memory_store=memory_store,
                    platform=platform,
                    company_name=company_name,
                )
                import logging
                logger = logging.getLogger(__name__)
                logger.info("[app] Generated planner hints for pre-flight review")
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"[app] Failed to generate planner hints: {e}", exc_info=True)
                planner_hints = None
        
        # v4.3.0: Normalizar execution_mode para plan_only también
        execution_mode = payload.execution_mode
        if execution_mode not in (None, "live", "dry_run"):
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[agent-answer] Invalid execution_mode={execution_mode!r}, falling back to 'live'")
            execution_mode = "live"
        if execution_mode is None:
            execution_mode = "live"
        
        # Devolver solo el plan
        return AgentAnswerResponse(
            goal=payload.goal,
            final_answer="Plan de ejecución generado. Por favor, revisa y confirma para ejecutar.",
            steps=[],
            source_url=None,
            source_title=None,
            sources=[],
            sections=None,
            structured_sources=None,
            metrics_summary=None,
            file_upload_instructions=None,
            execution_plan=execution_plan.to_dict(),
            execution_cancelled=None,
            reasoning_spotlight=reasoning_spotlight,  # v3.8.0
            planner_hints=planner_hints,  # v4.0.0
            execution_mode=execution_mode,  # v4.3.0
        )
    
    # v2.8.0: Manejar cancelación
    if payload.execution_confirmed is False:
        # v4.3.0: Normalizar execution_mode
        execution_mode = payload.execution_mode
        if execution_mode not in (None, "live", "dry_run"):
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"[agent-answer] Invalid execution_mode={execution_mode!r}, falling back to 'live'")
            execution_mode = "live"
        if execution_mode is None:
            execution_mode = "live"
        
        return AgentAnswerResponse(
            goal=payload.goal,
            final_answer="La ejecución fue cancelada por el usuario antes de iniciarse.",
            steps=[],
            source_url=None,
            source_title=None,
            sources=[],
            sections=None,
            structured_sources=None,
            metrics_summary=None,
            file_upload_instructions=None,
            execution_plan=None,
            execution_cancelled=True,
            reasoning_spotlight=reasoning_spotlight,  # v3.8.0
            execution_mode=execution_mode,  # v4.3.0
        )
    
    # v4.3.0: Normalizar execution_mode
    import logging
    logger = logging.getLogger(__name__)
    execution_mode = payload.execution_mode
    if execution_mode not in (None, "live", "dry_run"):
        logger.warning(f"[agent-answer] Invalid execution_mode={execution_mode!r}, falling back to 'live'")
        execution_mode = "live"
    if execution_mode is None:
        execution_mode = "live"
    
    # Ejecución normal (v2.7.0)
    # v2.9.0: Pasar disabled_sub_goal_indices
    # v4.3.0: Pasar execution_mode
    steps, final_answer, source_url, source_title, sources = await run_llm_task_with_answer(
        goal=payload.goal,
        browser=browser,
        max_steps=payload.max_steps,
        context_strategies=payload.context_strategies,
        execution_profile_name=payload.execution_profile_name,
        disabled_sub_goal_indices=payload.disabled_sub_goal_indices,
        execution_mode=execution_mode,
    )
    
    # v1.6.0: Extraer información estructurada del último step si está disponible
    structured_answer = None
    metrics_summary = None
    if steps:
        last_step = steps[-1]
        if last_step.info and "structured_answer" in last_step.info:
            structured_answer = last_step.info["structured_answer"]
        if last_step.info and "metrics" in last_step.info:
            metrics_summary = last_step.info["metrics"]
            # v3.8.0: Actualizar métricas con spotlight si está disponible
            if reasoning_spotlight and metrics_summary:
                # Registrar spotlight en métricas
                from backend.agents.agent_runner import AgentMetrics
                temp_metrics = AgentMetrics(execution_mode=execution_mode or "live")
                temp_metrics.register_reasoning_spotlight(reasoning_spotlight)
                spotlight_info = temp_metrics.to_summary_dict()["summary"]["spotlight_info"]
                # Añadir spotlight_info a metrics_summary (crear copia para no modificar el original)
                metrics_summary = dict(metrics_summary) if isinstance(metrics_summary, dict) else metrics_summary
                if "summary" not in metrics_summary:
                    metrics_summary["summary"] = {}
                metrics_summary["summary"]["spotlight_info"] = spotlight_info
    
    # v4.1.0: Generar Outcome Judge Report después de la ejecución
    outcome_judge = None
    if not is_batch_request and steps and metrics_summary:
        try:
            from backend.agents.outcome_judge import build_outcome_judge_report
            # Construir MemoryStore si estamos en contexto CAE (opcional)
            memory_store = None
            platform = None
            company_name = None
            
            # Intentar extraer platform/company_name del goal si es contexto CAE
            goal_lower = payload.goal.lower()
            if "cae" in goal_lower or "plataforma" in goal_lower:
                try:
                    from backend.memory import MemoryStore
                    from backend.config import MEMORY_BASE_DIR
                    memory_store = MemoryStore(MEMORY_BASE_DIR)
                    # TODO: Extraer platform y company_name del goal o de otro lugar si está disponible
                except Exception as e:
                    logger.debug(f"[app] Failed to initialize memory store for outcome judge: {e}")
            
            # En ejecución normal, no tenemos execution_plan (solo se genera en plan_only)
            execution_plan_obj = None
            
            outcome_judge = await build_outcome_judge_report(
                llm_client=llm_client,
                goal=payload.goal,
                execution_plan=execution_plan_obj,
                steps=steps,
                final_answer=final_answer,
                metrics_summary=metrics_summary,
                planner_hints=planner_hints,
                spotlight=reasoning_spotlight,
                memory_store=memory_store,
                platform=platform,
                company_name=company_name,
            )
            
            # Actualizar métricas con outcome judge
            if outcome_judge and metrics_summary:
                from backend.agents.agent_runner import AgentMetrics
                temp_metrics = AgentMetrics(execution_mode=execution_mode or "live")
                temp_metrics.register_outcome_judge(outcome_judge)
                outcome_judge_info = temp_metrics.to_summary_dict()["summary"]["outcome_judge_info"]
                if "summary" not in metrics_summary:
                    metrics_summary["summary"] = {}
                metrics_summary["summary"]["outcome_judge_info"] = outcome_judge_info
            
            logger.info("[app] Generated outcome judge report for execution")
        except Exception as e:
            logger.warning(f"[app] Failed to generate outcome judge report: {e}", exc_info=True)
            outcome_judge = None
    
    # v2.2.0: Recoger instrucciones de file upload de todos los steps
    file_upload_instructions: List[FileUploadInstructionDTO] = []
    seen_paths = set()
    for step in steps:
        if step.info and "file_upload_instruction" in step.info:
            instruction_dict = step.info["file_upload_instruction"]
            path_str = instruction_dict.get("path", "")
            # Deduplicar por path
            if path_str and path_str not in seen_paths:
                seen_paths.add(path_str)
                file_upload_instructions.append(FileUploadInstructionDTO(**instruction_dict))
    
    return AgentAnswerResponse(
        goal=payload.goal,
        final_answer=final_answer,
        steps=steps,
        source_url=source_url,
        source_title=source_title,
        sources=sources,
        sections=structured_answer["sections"] if structured_answer else None,
        structured_sources=structured_answer["sources"] if structured_answer else None,
        metrics_summary=metrics_summary,
        file_upload_instructions=file_upload_instructions if file_upload_instructions else None,
        execution_plan=None,
        execution_cancelled=None,
        reasoning_spotlight=reasoning_spotlight,  # v3.8.0
        planner_hints=planner_hints,  # v4.0.0
        outcome_judge=outcome_judge,  # v4.1.0
        execution_mode=execution_mode,  # v4.3.0
    )


@app.post("/agent/batch", response_model=BatchAgentResponse)
async def agent_batch_endpoint(request: BatchAgentRequest):
    """
    Ejecuta un batch de objetivos de forma autónoma.
    
    v3.0.0: Permite ejecutar múltiples objetivos secuencialmente sin intervención humana.
    """
    from backend.agents.batch_runner import run_batch_agent
    
    try:
        response = await run_batch_agent(
            batch_request=request,
            browser=browser,
        )
        return response
    except Exception as e:
        logger.error(f"[batch-endpoint] Fatal error in batch execution: {e}", exc_info=True)
        # Devolver respuesta de error estructurada
        error_result = BatchAgentResponse(
            goals=[],
            summary={
                "total_goals": len(request.goals),
                "success_count": 0,
                "failure_count": len(request.goals),
                "failure_ratio": 1.0,
                "aborted_due_to_failures": True,
                "max_consecutive_failures": request.max_consecutive_failures or 5,
                "elapsed_seconds": 0.0,
                "mode": "batch",
                "fatal_error": str(e),
            },
        )
        return error_result
