import sys
import asyncio
import os
import webbrowser
import threading
from typing import Optional, List

# En Windows, necesitamos un event loop que soporte subprocess (para Playwright)
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pathlib import Path
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
from backend.simulation.routes import router as simulation_router
from backend.training.routes import router as training_router, set_training_browser

# Constantes de rutas
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="CometLocal Backend")

# CORS abierto para desarrollo (luego afinaremos)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar routers
app.include_router(simulation_router)
app.include_router(training_router)

browser = BrowserController()

# Configurar el browser para el router de training
set_training_browser(browser)


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
    # NO arrancamos Playwright/Chromium al startup - solo cuando el executor lo necesite
    
    # Inicializar cliente LLM compartido
    from openai import AsyncOpenAI
    from backend.config import LLM_API_BASE, LLM_API_KEY
    app.state.llm_client = AsyncOpenAI(
        base_url=LLM_API_BASE,
        api_key=LLM_API_KEY,
    )
    
    # Abrir navegador del sistema para la UI del chat si OPEN_UI_ON_START=1
    if os.getenv("OPEN_UI_ON_START") == "1":
        ui_url = "http://127.0.0.1:8000/"
        
        # Abrir en background thread para no bloquear startup
        def open_browser():
            try:
                webbrowser.open(ui_url)
                print(f"[STARTUP] Abierto navegador del sistema en {ui_url}")
            except Exception as e:
                print(f"[STARTUP] Error al abrir navegador: {e}")
        
        # Ejecutar en thread separado con pequeño delay para asegurar que el servidor está listo
        def delayed_open():
            import time
            time.sleep(1)  # Esperar 1 segundo para que el servidor esté listo
            open_browser()
        
        thread = threading.Thread(target=delayed_open, daemon=True)
        thread.start()


@app.on_event("shutdown")
async def shutdown_event():
    # Cerramos el navegador solo si está iniciado (lazy initialization)
    if browser.page is not None:
        await browser.close()


@app.get("/health")
async def health():
    return {"status": "ok", "detail": "CometLocal backend running con navegador"}


@app.get("/", include_in_schema=False)
async def root_index():
    """
    Página principal de CometLocal (UI del agente).
    """
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/index.html", include_in_schema=False)
async def explicit_index():
    """
    Alias explícito para index.html.
    """
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/form-sandbox", include_in_schema=False)
async def form_sandbox_ui():
    """
    Sandbox de formularios para entrenar y probar el form filler.
    """
    return FileResponse(FRONTEND_DIR / "form_sandbox.html")


@app.get("/simulation/portal_a/login.html", include_in_schema=False)
async def simulation_portal_a_login():
    """
    Página de login del portal CAE simulado A.
    """
    return FileResponse(FRONTEND_DIR / "simulation" / "portal_a" / "login.html")


@app.get("/simulation/portal_a/dashboard.html", include_in_schema=False)
async def simulation_portal_a_dashboard():
    """
    Dashboard simulado del Portal CAE A.
    """
    return FileResponse(FRONTEND_DIR / "simulation" / "portal_a" / "dashboard.html")


@app.get("/simulation/portal_a/upload.html", include_in_schema=False)
async def simulation_portal_a_upload():
    """
    Formulario simulado de subida de documentación para un trabajador.
    """
    return FileResponse(FRONTEND_DIR / "simulation" / "portal_a" / "upload.html")


@app.get("/training", include_in_schema=False)
async def training_ui():
    """
    Devuelve la Training UI estática.
    """
    return FileResponse(FRONTEND_DIR / "training.html")


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
    import logging
    logger = logging.getLogger(__name__)
    
    # Logging de entrada para debugging
    # Normalizar confirmed: siempre boolean, nunca None
    confirmed_raw = payload.execution_confirmed if hasattr(payload, 'execution_confirmed') else None
    confirmed = bool(confirmed_raw) if confirmed_raw is not None else False
    confirmed_normalized = confirmed
    
    plan_only = payload.plan_only if hasattr(payload, 'plan_only') and payload.plan_only else False
    steps_len = len(payload.steps) if hasattr(payload, 'steps') and isinstance(payload.steps, list) else "n/a"
    
    # Print explícito para debugging
    print(
        "[DEBUG_AGENT] /agent/answer llamado:",
        "goal=", repr(payload.goal),
        "confirmed_raw=", confirmed_raw,
        "confirmed_normalized=", confirmed_normalized,
        "plan_only=", plan_only,
        "steps_len=", steps_len,
        "execution_profile_name=", payload.execution_profile_name,
        "execution_mode=", payload.execution_mode,
    )
    
    logger.info(
        "[agent_answer_endpoint] goal=%r confirmed=%s plan_only=%s steps_len=%s execution_profile_name=%r execution_mode=%r",
        payload.goal,
        confirmed,
        plan_only,
        steps_len,
        payload.execution_profile_name,
        payload.execution_mode,
    )
    
    # Este endpoint es siempre interactivo, nunca batch
    is_batch_request = False
    
    # v2.8.0: Manejar flujo de planificación
    from backend.agents.agent_runner import build_execution_plan, _decompose_goal, ExecutionProfile
    from backend.agents.document_repository import DocumentRepository
    from backend.agents.context_strategies import build_context_strategies, DEFAULT_CONTEXT_STRATEGIES
    from backend.config import DOCUMENT_REPOSITORY_BASE_DIR, DEFAULT_CAE_BASE_URL
    from pathlib import Path
    
    # Obtener el cliente LLM correctamente desde la aplicación
    # Asegurar que llm_client está siempre definido (puede ser None si no está inicializado)
    llm_client = getattr(app.state, "llm_client", None)
    
    if llm_client is None:
        logger.warning("[agent_answer_endpoint] No llm_client available in app.state.llm_client - PlannerHints and OutcomeJudge will be skipped")
    
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
        print("[DEBUG_AGENT] Modo plan_only=True: solo generando plan, NO ejecutando navegador")
        logger.info("[agent_answer_endpoint] Modo plan_only: solo generando plan, NO ejecutando")
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
            if llm_client is not None:
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
                    logger.info("[app] Generated planner hints for pre-flight review")
                except Exception as e:
                    logger.warning(f"[app] Failed to generate planner hints: {e}", exc_info=True)
                    planner_hints = None
            else:
                logger.warning("[app] Planner hints skipped: no llm_client available")
        
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
        logger.info("[agent_answer_endpoint] Ejecución cancelada por el usuario")
        # v4.3.0: Normalizar execution_mode
        execution_mode = payload.execution_mode
        if execution_mode not in (None, "live", "dry_run"):
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
    execution_mode = payload.execution_mode
    if execution_mode not in (None, "live", "dry_run"):
        logger.warning(f"[agent-answer] Invalid execution_mode={execution_mode!r}, falling back to 'live'")
        execution_mode = "live"
    if execution_mode is None:
        execution_mode = "live"
    
    # Ejecución normal (v2.7.0)
    # Cuando execution_confirmed es True (o None/omitted), ejecutar el agente con navegador
    print("[DEBUG_AGENT] confirmed=True → iniciando ejecución de agente con navegador")
    logger.info("[agent_answer_endpoint] Iniciando ejecución del agente con navegador (confirmed=%s)", confirmed)
    logger.info("[agent_answer_endpoint] Parámetros: goal=%r, execution_profile_name=%r, context_strategies=%r, execution_mode=%r",
                payload.goal, payload.execution_profile_name, payload.context_strategies, execution_mode)
    
    # Verificar que el browser esté iniciado
    if not browser.page:
        print("[DEBUG_AGENT] WARNING: browser.page es None, iniciando browser...")
        await browser.start(headless=False)
    
    # v2.8.0+: Ejecutor determinista de navegación para steps confirmados
    # Ejecuta navegación ANTES de que el LLM procese los steps
    if payload.steps and isinstance(payload.steps, list) and len(payload.steps) > 0:
        from backend.agents.agent_runner import (
            execute_step_with_playwright,
            _has_executable_actions,
            generate_executable_actions_from_dom,
        )
        
        logger.info(f"[agent_answer_endpoint] Ejecutando {len(payload.steps)} steps con executor determinista")
        print(f"[DEBUG_AGENT] Ejecutando {len(payload.steps)} steps con executor determinista")
        
        # Ejecutar primero todos los steps de navegación
        navigation_executed = False
        for step_index, step in enumerate(payload.steps, start=1):
            # Verificar que no sea Wikipedia o Images (no tocarlos)
            strategy = step.get("strategy", "").lower() if isinstance(step, dict) else ""
            if strategy in ("wikipedia", "images"):
                logger.info(f"[agent_answer_endpoint] Saltando step {step_index} (strategy={strategy})")
                continue
            
            # Ejecutar acción determinista si el step lo requiere
            try:
                action_result = await execute_step_with_playwright(
                    step=step if isinstance(step, dict) else {},
                    step_index=step_index,
                    browser=browser,
                    execution_context={"goal": payload.goal, "execution_mode": execution_mode},
                )
                if action_result:
                    logger.info(f"[agent_answer_endpoint] Step {step_index} ejecutado: {action_result}")
                    print(f"[DEBUG_AGENT] Step {step_index} ejecutado: {action_result}")
                    # Si fue navegación, marcar que se navegó
                    if "navigated" in action_result.lower():
                        navigation_executed = True
            except Exception as e:
                logger.warning(f"[agent_answer_endpoint] Error al ejecutar step {step_index} con executor determinista: {e}", exc_info=True)
                # Continuar con el siguiente step aunque haya error
        
        # v2.8.0+: ActionPlanner - Generar acciones ejecutables si no las hay
        if navigation_executed and not _has_executable_actions(payload.steps):
            logger.info("[agent_answer_endpoint] Steps no tienen acciones ejecutables, generando desde DOM...")
            print("[DEBUG_AGENT] Steps no tienen acciones ejecutables, generando desde DOM...")
            
            try:
                # Obtener cliente LLM
                llm_client = getattr(app.state, "llm_client", None)
                if llm_client is None:
                    logger.warning("[agent_answer_endpoint] No llm_client disponible para ActionPlanner")
                else:
                    # Generar acciones ejecutables desde el DOM
                    generated_actions = await generate_executable_actions_from_dom(
                        goal=payload.goal,
                        browser=browser,
                        llm_client=llm_client,
                    )
                    
                    if generated_actions and len(generated_actions) > 0:
                        logger.info(f"[agent_answer_endpoint] Phase 1 actions: {len(generated_actions)}")
                        print(f"[DEBUG_AGENT] Phase 1 actions: {len(generated_actions)}")
                        
                        # Guardar URL antes de ejecutar acciones
                        previous_url = browser.page.url if browser.page else None
                        
                        # Convertir acciones generadas en steps y ejecutarlas
                        # Usar step_index continuando desde los steps originales
                        base_step_index = len(payload.steps) + 1
                        for action_idx, action in enumerate(generated_actions, start=1):
                            step_index = base_step_index + action_idx - 1
                            
                            # Convertir acción a formato de step
                            step = {
                                "action": action.get("action"),
                                "selector": action.get("selector"),
                                "value": action.get("value"),
                                "url": action.get("url"),  # Para navigate
                                "filepath": action.get("filepath"),  # Para upload
                                "expected_actions": [action.get("action")],
                            }
                            
                            try:
                                # Inicializar execution_context con flags si no existen
                                exec_ctx = {"goal": payload.goal, "execution_mode": execution_mode}
                                # Preservar flags existentes si hay
                                if hasattr(payload, 'execution_context') and payload.execution_context:
                                    exec_ctx.update(payload.execution_context)
                                
                                action_result = await execute_step_with_playwright(
                                    step=step,
                                    step_index=step_index,
                                    browser=browser,
                                    execution_context=exec_ctx,
                                )
                                
                                # Actualizar flags en el contexto
                                if action_result and "upload" in action_result.lower():
                                    exec_ctx["upload_done"] = True
                                if action_result and ("submit" in action_result.lower() or "clicked" in action_result.lower()):
                                    # Verificar si fue click en "Simular subida"
                                    if "simular subida" in str(step.get("selector", "")).lower() or "simular subida" in str(action_result).lower():
                                        exec_ctx["submit_done"] = True
                                if action_result:
                                    logger.info(f"[agent_answer_endpoint] Acción generada {action_idx} ejecutada: {action_result}")
                                    print(f"[DEBUG_AGENT] Acción generada {action_idx} ejecutada: {action_result}")
                            except Exception as e:
                                logger.warning(f"[agent_answer_endpoint] Error al ejecutar acción generada {action_idx}: {e}", exc_info=True)
                                # Continuar con la siguiente acción aunque haya error
                        
                        # v2.8.0+: Inicializar flags de ejecución (en memoria para esta ejecución)
                        execution_flags = {"upload_done": False, "submit_done": False, "sim_clicked": False}
                        
                        # v2.8.0+: Segunda pasada - Verificar si la página cambió
                        if browser.page:
                            # Esperar un momento para que la página se cargue completamente
                            await browser.page.wait_for_timeout(2000)
                            try:
                                await browser.page.wait_for_load_state("networkidle", timeout=3000)
                            except Exception:
                                pass  # Ignorar timeout
                            
                            current_url = browser.page.url
                            
                            # Corte duro: Si ya estamos en upload.html y ambas acciones están hechas, NO generar más fases
                            if "upload.html" in current_url.lower() and execution_flags["upload_done"] and execution_flags["sim_clicked"]:
                                logger.info(f"[agent_answer_endpoint] Upload flow completed, skipping further phases")
                                print(f"[DEBUG_AGENT] Upload flow completed, skipping further phases")
                                # Terminar la parte de acciones - NO continuar con fases adicionales
                                # No entrar en el else, salir del bloque
                            elif "upload.html" in current_url.lower():
                                # Si estamos en upload.html pero falta alguna acción, continuar
                                logger.info(f"[agent_answer_endpoint] In upload.html, upload_done={execution_flags['upload_done']}, sim_clicked={execution_flags['sim_clicked']}")
                            else:
                                # Verificar si la URL cambió o contiene "dashboard"
                                url_changed = (previous_url and current_url != previous_url) or "dashboard" in current_url.lower()
                                
                                if url_changed:
                                    logger.info(f"[agent_answer_endpoint] URL cambió a {current_url}, generando acciones de segunda fase...")
                                    print(f"[DEBUG_AGENT] URL cambió a {current_url}, generando acciones de segunda fase...")
                                    
                                    try:
                                        # Generar acciones de segunda fase
                                        phase2_actions = await generate_executable_actions_from_dom(
                                            goal=payload.goal,
                                            browser=browser,
                                            llm_client=llm_client,
                                            phase=2,
                                            previous_url=previous_url,
                                        )
                                        
                                        if phase2_actions and len(phase2_actions) > 0:
                                            logger.info(f"[agent_answer_endpoint] Phase 2 actions: {len(phase2_actions)}")
                                            print(f"[DEBUG_AGENT] Phase 2 actions: {len(phase2_actions)}")
                                            
                                            # Ejecutar acciones de segunda fase
                                            phase2_base_index = base_step_index + len(generated_actions)
                                            for action_idx, action in enumerate(phase2_actions, start=1):
                                                step_index = phase2_base_index + action_idx - 1
                                                
                                                # Convertir acción a formato de step
                                                step = {
                                                    "action": action.get("action"),
                                                    "selector": action.get("selector"),
                                                    "value": action.get("value"),
                                                    "url": action.get("url"),  # Para navigate
                                                    "filepath": action.get("filepath"),  # Para upload
                                                    "expected_actions": [action.get("action")],
                                                }
                                                
                                                try:
                                                    # Pasar execution_flags en el contexto
                                                    exec_ctx_phase2 = {"goal": payload.goal, "execution_mode": execution_mode, "execution_flags": execution_flags}
                                                    
                                                    action_result = await execute_step_with_playwright(
                                                        step=step,
                                                        step_index=step_index,
                                                        browser=browser,
                                                        execution_context=exec_ctx_phase2,
                                                    )
                                                    
                                                    # Actualizar flags según el resultado
                                                    if action_result:
                                                        logger.info(f"[agent_answer_endpoint] Acción fase 2 {action_idx} ejecutada: {action_result}")
                                                        print(f"[DEBUG_AGENT] Acción fase 2 {action_idx} ejecutada: {action_result}")
                                                        
                                                        # Detectar si fue upload o submit
                                                        if "upload" in action_result.lower() and "uploaded file" in action_result.lower():
                                                            execution_flags["upload_done"] = True
                                                            logger.info(f"[agent_answer_endpoint] Flag upload_done establecido en fase 2")
                                                        # Detectar click en "Simular subida"
                                                        if "simular subida" in str(step.get("selector", "")).lower() or "simular subida" in action_result.lower():
                                                            execution_flags["sim_clicked"] = True
                                                            execution_flags["submit_done"] = True
                                                            logger.info(f"[agent_answer_endpoint] Flag sim_clicked establecido en fase 2")
                                                        elif "submit" in action_result.lower() or "clicked" in action_result.lower():
                                                            execution_flags["submit_done"] = True
                                                            logger.info(f"[agent_answer_endpoint] Flag submit_done establecido en fase 2")
                                                except Exception as e:
                                                    logger.warning(f"[agent_answer_endpoint] Error al ejecutar acción fase 2 {action_idx}: {e}", exc_info=True)
                                                    # Continuar con la siguiente acción aunque haya error
                                            
                                            # v2.8.0+: Tercera pasada - Verificar si la URL cambió a upload.html
                                            if browser.page:
                                                # Esperar un momento para que la página se cargue completamente
                                                await browser.page.wait_for_timeout(2000)
                                                try:
                                                    await browser.page.wait_for_load_state("networkidle", timeout=3000)
                                                except Exception:
                                                    pass  # Ignorar timeout
                                                
                                                current_url_phase2 = browser.page.url
                                                
                                                # Corte duro: Verificar flags antes de lanzar Phase 3
                                                # Si Phase 2 ya ejecutó upload+click "Simular subida", NO lanzar Phase 3
                                                if "upload.html" in current_url_phase2.lower():
                                                    if execution_flags["upload_done"] and execution_flags["sim_clicked"]:
                                                        logger.info(f"[agent_answer_endpoint] Upload flow completed, skipping Phase 3")
                                                        print(f"[DEBUG_AGENT] Upload flow completed, skipping Phase 3")
                                                        # NO generar Phase 3
                                                    elif not (execution_flags["upload_done"] and execution_flags["sim_clicked"]):
                                                        logger.info(f"[agent_answer_endpoint] URL cambió a upload.html ({current_url_phase2}), generando acciones de fase 3...")
                                                        print(f"[DEBUG_AGENT] URL cambió a upload.html ({current_url_phase2}), generando acciones de fase 3...")
                                                        
                                                        try:
                                                            # Generar acciones de tercera fase
                                                            phase3_actions = await generate_executable_actions_from_dom(
                                                                goal=payload.goal,
                                                                browser=browser,
                                                                llm_client=llm_client,
                                                                phase=3,
                                                                previous_url=current_url,
                                                            )
                                                            
                                                            if phase3_actions and len(phase3_actions) > 0:
                                                                logger.info(f"[agent_answer_endpoint] Phase 3 actions: {len(phase3_actions)}")
                                                                print(f"[DEBUG_AGENT] Phase 3 actions: {len(phase3_actions)}")
                                                                
                                                                # Ejecutar acciones de tercera fase
                                                                phase3_base_index = phase2_base_index + len(phase2_actions)
                                                                for action_idx, action in enumerate(phase3_actions, start=1):
                                                                    step_index = phase3_base_index + action_idx - 1
                                                                    
                                                                    # Convertir acción a formato de step
                                                                    step = {
                                                                        "action": action.get("action"),
                                                                        "selector": action.get("selector"),
                                                                        "value": action.get("value"),
                                                                        "url": action.get("url"),  # Para navigate
                                                                        "filepath": action.get("filepath"),  # Para upload
                                                                        "expected_actions": [action.get("action")],
                                                                    }
                                                                    
                                                                    try:
                                                                        # Pasar execution_flags en el contexto
                                                                        exec_ctx_phase3 = {"goal": payload.goal, "execution_mode": execution_mode, "execution_flags": execution_flags}
                                                                        
                                                                        action_result = await execute_step_with_playwright(
                                                                            step=step,
                                                                            step_index=step_index,
                                                                            browser=browser,
                                                                            execution_context=exec_ctx_phase3,
                                                                        )
                                                                        
                                                                        # Actualizar flags según el resultado
                                                                        if action_result:
                                                                            logger.info(f"[agent_answer_endpoint] Acción fase 3 {action_idx} ejecutada: {action_result}")
                                                                            print(f"[DEBUG_AGENT] Acción fase 3 {action_idx} ejecutada: {action_result}")
                                                                            
                                                                            # Detectar si fue upload o submit
                                                                            if "upload" in action_result.lower() and "uploaded file" in action_result.lower():
                                                                                execution_flags["upload_done"] = True
                                                                                logger.info(f"[agent_answer_endpoint] Flag upload_done establecido en fase 3")
                                                                            # Detectar click en "Simular subida"
                                                                            if "simular subida" in str(step.get("selector", "")).lower() or "simular subida" in action_result.lower():
                                                                                execution_flags["sim_clicked"] = True
                                                                                execution_flags["submit_done"] = True
                                                                                logger.info(f"[agent_answer_endpoint] Flag sim_clicked establecido en fase 3")
                                                                            elif "submit" in action_result.lower() or "clicked" in action_result.lower():
                                                                                execution_flags["submit_done"] = True
                                                                                logger.info(f"[agent_answer_endpoint] Flag submit_done establecido en fase 3")
                                                                    except Exception as e:
                                                                        logger.warning(f"[agent_answer_endpoint] Error al ejecutar acción fase 3 {action_idx}: {e}", exc_info=True)
                                                                        # Continuar con la siguiente acción aunque haya error
                                                            else:
                                                                logger.info("[agent_answer_endpoint] No se generaron acciones ejecutables en fase 3")
                                                        except Exception as e:
                                                            logger.warning(f"[agent_answer_endpoint] Error en ActionPlanner fase 3: {e}", exc_info=True)
                                                            # Continuar sin romper el flujo
                                        else:
                                            logger.info("[agent_answer_endpoint] No se generaron acciones ejecutables en fase 2")
                                    except Exception as e:
                                        logger.warning(f"[agent_answer_endpoint] Error en ActionPlanner fase 2: {e}", exc_info=True)
                                        # Continuar sin romper el flujo
                    else:
                        logger.info("[agent_answer_endpoint] No se generaron acciones ejecutables desde DOM")
            except Exception as e:
                logger.warning(f"[agent_answer_endpoint] Error en ActionPlanner: {e}", exc_info=True)
                # Continuar sin romper el flujo
    
    # v2.9.0: Pasar disabled_sub_goal_indices
    # v4.3.0: Pasar execution_mode
    print(f"[DEBUG_AGENT] Llamando a run_llm_task_with_answer con goal={repr(payload.goal[:100])}, execution_mode={execution_mode}")
    steps, final_answer, source_url, source_title, sources = await run_llm_task_with_answer(
        goal=payload.goal,
        browser=browser,
        max_steps=payload.max_steps,
        context_strategies=payload.context_strategies,
        execution_profile_name=payload.execution_profile_name,
        disabled_sub_goal_indices=payload.disabled_sub_goal_indices,
        execution_mode=execution_mode,
    )
    
    print(f"[DEBUG_AGENT] run_llm_task_with_answer() completado, steps={len(steps)}, final_answer={repr(final_answer[:100]) if final_answer else None}")
    logger.info("[agent_answer_endpoint] Ejecución completada: steps=%d, final_answer=%r", len(steps), final_answer[:100] if final_answer else None)
    
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
        if llm_client is not None:
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
        else:
            logger.warning("[app] Outcome judge skipped: no llm_client available")
    
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
    import logging
    logger = logging.getLogger(__name__)
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
