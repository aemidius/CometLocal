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
from backend.executor.runs_viewer import create_runs_viewer_router
from backend.config import BATCH_RUNS_DIR

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
app.include_router(create_runs_viewer_router(runs_root=BASE_DIR / BATCH_RUNS_DIR))

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


@app.get("/simulation/portal_a_v2/login.html", include_in_schema=False)
async def simulation_portal_a_v2_login():
    """
    Página de login del portal CAE simulado A v2.
    """
    return FileResponse(FRONTEND_DIR / "simulation" / "portal_a_v2" / "login.html")


@app.get("/simulation/portal_a_v2/dashboard.html", include_in_schema=False)
async def simulation_portal_a_v2_dashboard():
    """
    Dashboard simulado del Portal CAE A v2.
    """
    return FileResponse(FRONTEND_DIR / "simulation" / "portal_a_v2" / "dashboard.html")


@app.get("/simulation/portal_a_v2/upload.html", include_in_schema=False)
async def simulation_portal_a_v2_upload():
    """
    Formulario simulado de subida de documentación para un trabajador (Portal A v2).
    """
    return FileResponse(FRONTEND_DIR / "simulation" / "portal_a_v2" / "upload.html")


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
    print("[DEBUG_AGENT] confirmed=True -> iniciando ejecución de agente con navegador")
    logger.info("[agent_answer_endpoint] Iniciando ejecución del agente con navegador (confirmed=%s)", confirmed)
    logger.info("[agent_answer_endpoint] Parámetros: goal=%r, execution_profile_name=%r, context_strategies=%r, execution_mode=%r",
                payload.goal, payload.execution_profile_name, payload.context_strategies, execution_mode)
    
    # v4.9.0 FIX: Detectar si el usuario está proporcionando credenciales (respuesta a needs_user_input)
    # Parsear credenciales del texto y guardarlas sin ejecutar Playwright ni planner
    goal_text = payload.goal.strip()
    goal_lower = goal_text.lower()
    
    # Detectar patrones de credenciales en el texto
    import re
    parsed_creds = {}
    
    # Patrón 1: "Empresa 123, usuario demo, contraseña demo" (formato completo)
    full_pattern = re.search(
        r'empresa\s*[:=]?\s*(\S+)[,;]?\s*(?:usuario|user)\s*[:=]?\s*(\S+)[,;]?\s*(?:contraseña|password|pass)\s*[:=]?\s*(\S+)',
        goal_text,
        re.IGNORECASE
    )
    if full_pattern:
        parsed_creds['company_code'] = full_pattern.group(1).strip(',;')
        parsed_creds['username'] = full_pattern.group(2).strip(',;')
        parsed_creds['password'] = full_pattern.group(3).strip(',;')
    else:
        # Patrón 2: "123, demo, demo" (orden: empresa, usuario, contraseña)
        simple_pattern = re.search(r'^(\S+)\s*[,;]\s*(\S+)\s*[,;]\s*(\S+)', goal_text, re.IGNORECASE)
        if simple_pattern:
            parsed_creds['company_code'] = simple_pattern.group(1).strip(',;')
            parsed_creds['username'] = simple_pattern.group(2).strip(',;')
            parsed_creds['password'] = simple_pattern.group(3).strip(',;')
        else:
            # Patrón 3: Campos individuales
            empresa_match = re.search(r'empresa\s*[:=]?\s*(\S+)', goal_text, re.IGNORECASE)
            if empresa_match:
                parsed_creds['company_code'] = empresa_match.group(1).strip(',;')
            
            usuario_match = re.search(r'(?:usuario|user)\s*[:=]?\s*(\S+)', goal_text, re.IGNORECASE)
            if usuario_match:
                parsed_creds['username'] = usuario_match.group(1).strip(',;')
            
            password_match = re.search(r'(?:contraseña|password|pass)\s*[:=]?\s*(\S+)', goal_text, re.IGNORECASE)
            if password_match:
                parsed_creds['password'] = password_match.group(1).strip(',;')
    
    # Si detectamos credenciales, guardarlas pero continuar con ejecución si hay objetivo
    if parsed_creds and ('company_code' in parsed_creds or 'username' in parsed_creds or 'password' in parsed_creds):
        logger.info(f"[agent_answer_endpoint] Credenciales detectadas en goal, guardando en memoria...")
        print(f"[DEBUG_AGENT] Credenciales detectadas: {parsed_creds}")
        
        # Inicializar memory_store
        memory_store = None
        try:
            from backend.memory import MemoryStore
            from backend.config import MEMORY_BASE_DIR
            from backend.shared.models import PlatformMemory
            memory_store = MemoryStore(MEMORY_BASE_DIR)
        except Exception as e:
            logger.warning(f"[agent_answer_endpoint] No se pudo inicializar memory_store: {e}")
        
        if memory_store:
            try:
                # Cargar o crear PlatformMemory para portal_a
                portal = "portal_a"
                platform_memory = memory_store.load_platform(portal)
                if not platform_memory:
                    platform_memory = PlatformMemory(platform=portal)
                
                # Actualizar credenciales parseadas
                if 'company_code' in parsed_creds:
                    platform_memory.last_company_code = parsed_creds['company_code']
                if 'username' in parsed_creds:
                    platform_memory.last_username = parsed_creds['username']
                if 'password' in parsed_creds:
                    platform_memory.last_password = parsed_creds['password']
                
                # Guardar en memoria
                memory_store.save_platform(platform_memory)
                logger.info(f"[agent_answer_endpoint] Credenciales guardadas en memoria para {portal}")
                print(f"[DEBUG_AGENT] Credenciales guardadas: empresa={parsed_creds.get('company_code')}, usuario={parsed_creds.get('username')}")
            except Exception as e:
                logger.error(f"[agent_answer_endpoint] Error al guardar credenciales: {e}")
        
        # Detectar si el goal contiene SOLO credenciales (sin objetivo) o credenciales + objetivo
        # Palabras clave que indican un objetivo de ejecución (excluyendo palabras de credenciales)
        objective_keywords = [
            "accede", "navega", "entra", "sube", "subir", "reconocimiento", 
            "simula subida", "simular subida", "portal", "login", "dashboard", "upload", 
            "documento", "trabajador", "worker", "w-", "para w-", "médico", "caducidad",
            "emisión", "fecha", "sube", "subir archivo"
        ]
        # Si el goal contiene credenciales pero también palabras clave de objetivo, continuar ejecución
        # Si el goal es SOLO credenciales (sin objetivo), devolver early
        has_objective = any(keyword in goal_lower for keyword in objective_keywords)
        
        # Si el goal contiene palabras clave de objetivo, continuar con ejecución
        # Si NO contiene objetivo, devolver early pidiendo el objetivo
        if not has_objective:
            logger.info(f"[agent_answer_endpoint] Goal contiene solo credenciales sin objetivo, solicitando objetivo...")
            print(f"[DEBUG_AGENT] Goal contiene solo credenciales sin objetivo, solicitando objetivo...")
            return AgentAnswerResponse(
                goal=payload.goal,
                final_answer="Credenciales guardadas. ¿Qué acción quieres ejecutar en el Portal A? (ej: sube un reconocimiento médico para W-001)",
                steps=[],
                source_url=None,
                source_title=None,
                sources=[],
                sections=None,
                structured_sources=None,
                metrics_summary={
                    "needs_user_input": True,
                    "missing_fields": ["objetivo"],
                },
                file_upload_instructions=None,
                execution_plan=None,
                execution_cancelled=None,
                reasoning_spotlight=None,
                planner_hints=None,
                outcome_judge=None,
                execution_mode=execution_mode,
            )
        else:
            # Credenciales + objetivo: guardar credenciales y continuar con ejecución
            logger.info(f"[agent_answer_endpoint] Credenciales guardadas, continuando con ejecución del objetivo...")
            print(f"[DEBUG_AGENT] Credenciales guardadas, continuando con ejecución del objetivo...")
            # NO hacer return, continuar con el flujo normal
    
    # v4.9.0 FIX: Gating - Verificar credenciales ANTES de iniciar Playwright
    # Esto evita abrir el navegador si faltan credenciales
    requires_login_upload = (
        ("portal a" in goal_lower or "portal_a" in goal_lower) and
        ("sube" in goal_lower or "subir" in goal_lower or "reconocimiento" in goal_lower or "simula subida" in goal_lower)
    )
    
    if requires_login_upload:
        # Inicializar memory_store para verificar credenciales
        memory_store = None
        try:
            from backend.memory import MemoryStore
            from backend.config import MEMORY_BASE_DIR
            from backend.agents.agent_runner import get_memory_defaults
            memory_store = MemoryStore(MEMORY_BASE_DIR)
        except Exception as e:
            logger.debug(f"[agent_answer_endpoint] No se pudo inicializar memory_store: {e}")
            # Importar get_memory_defaults aunque falle memory_store
            try:
                from backend.agents.agent_runner import get_memory_defaults
            except ImportError:
                logger.error("[agent_answer_endpoint] No se pudo importar get_memory_defaults")
                get_memory_defaults = None
        
        # Intentar obtener credenciales desde memoria
        if get_memory_defaults:
            defaults = get_memory_defaults(portal="portal_a", memory_store=memory_store)
        else:
            defaults = {}
        missing_creds = []
        
        if not defaults.get("company_code"):
            missing_creds.append("empresa")
        if not defaults.get("username"):
            missing_creds.append("usuario")
        if not defaults.get("password"):
            missing_creds.append("contraseña")
        
        if missing_creds:
            question = f"Necesito credenciales para Portal A: {', '.join(missing_creds)}."
            logger.info(f"[agent_answer_endpoint] Credenciales faltantes detectadas: {missing_creds}")
            print(f"[DEBUG_AGENT] Credenciales faltantes detectadas: {missing_creds}")
            
            # Devolver respuesta inmediata sin ejecutar nada más (SIN iniciar Playwright)
            return AgentAnswerResponse(
                goal=payload.goal,
                final_answer=question,
                steps=[],
                source_url=None,
                source_title=None,
                sources=[],
                sections=None,
                structured_sources=None,
                metrics_summary={
                    "needs_user_input": True,
                    "missing_fields": missing_creds,
                },
                file_upload_instructions=None,
                execution_plan=None,
                execution_cancelled=None,
                reasoning_spotlight=None,
                planner_hints=None,
                outcome_judge=None,
                execution_mode=execution_mode,
            )
    
    # Guard-rail adicional: No inicializar Playwright si no hay intención de navegación
    # Solo inicializar si el goal contiene URLs o acciones que requieren navegador
    goal_text = payload.goal.strip()
    goal_lower = goal_text.lower()
    has_navigation_intent = (
        "http" in goal_text or
        "://" in goal_text or
        "navega" in goal_lower or
        "accede" in goal_lower or
        "entra" in goal_lower or
        "portal" in goal_lower or
        "login" in goal_lower or
        "dashboard" in goal_lower or
        "sube" in goal_lower or
        "subir" in goal_lower or
        (payload.steps and isinstance(payload.steps, list) and len(payload.steps) > 0)
    )
    
    # Verificar que el browser esté iniciado (solo si hay intención de navegación y pasamos el gating de credenciales)
    if has_navigation_intent:
        if not browser.page:
            print("[DEBUG_AGENT] WARNING: browser.page es None, iniciando browser...")
            await browser.start(headless=False)
    else:
        logger.info(f"[agent_answer_endpoint] No hay intención de navegación detectada, saltando inicialización de Playwright")
        print(f"[DEBUG_AGENT] No hay intención de navegación, saltando Playwright")
    
    # v2.8.0+: Ejecutor determinista de navegación para steps confirmados
    # Ejecuta navegación ANTES de que el LLM procese los steps
    if payload.steps and isinstance(payload.steps, list) and len(payload.steps) > 0:
        from backend.agents.agent_runner import (
            execute_step_with_playwright,
            _has_executable_actions,
            generate_executable_actions_from_dom,
            get_memory_defaults,
        )
        
        logger.info(f"[agent_answer_endpoint] Ejecutando {len(payload.steps)} steps con executor determinista")
        print(f"[DEBUG_AGENT] Ejecutando {len(payload.steps)} steps con executor determinista")
        
        # v4.9.0: Resolver URLs de portales si faltan
        # Normalizar goal: lower(), strip(), reemplazar múltiples espacios
        import re
        goal_norm = re.sub(r'\s+', ' ', payload.goal.lower().strip())
        
        # Helper para cargar URL de plataforma desde JSON
        def resolve_platform_url(platform_id: str) -> Optional[str]:
            """Carga la URL de login de una plataforma desde su JSON."""
            try:
                from backend.memory import MemoryStore
                from backend.config import MEMORY_BASE_DIR
                import json
                from pathlib import Path
                
                platforms_dir = Path(MEMORY_BASE_DIR) / "platforms"
                platform_file = platforms_dir / f"{platform_id}.json"
                
                if not platform_file.exists():
                    logger.warning(f"[PLATFORM] JSON not found for {platform_id}")
                    return None
                
                with open(platform_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                base_url = data.get("base_url")
                if not base_url:
                    logger.warning(f"[PLATFORM] base_url not found in {platform_id}.json")
                    return None
                
                # Construir URL de login
                login_url = f"{base_url.rstrip('/')}/login.html"
                return login_url
            except Exception as e:
                logger.warning(f"[PLATFORM] Error loading {platform_id}: {e}")
                return None
        
        # CAMBIO 1 y 2: Matching con prioridad ALTA para v2 antes de v1
        resolved_platform = None
        resolved_url = None
        
        if "portal a v2" in goal_norm or "portal_a_v2" in goal_norm or "portal cae a v2" in goal_norm:
            resolved_platform = "portal_a_v2"
            resolved_url = resolve_platform_url("portal_a_v2")
            if not resolved_url:
                # Fallback si no se puede cargar del JSON
                resolved_url = "http://127.0.0.1:8000/simulation/portal_a_v2/login.html"
        elif "portal a" in goal_norm or "portal_a" in goal_norm:
            resolved_platform = "portal_a"
            from backend.config import DEFAULT_PORTAL_A_URL
            resolved_url = DEFAULT_PORTAL_A_URL
        
        # Si se resolvió una plataforma, inyectar URL en el step de navegación
        if resolved_platform and resolved_url:
            # Buscar el primer step que requiera navigate
            for step in payload.steps:
                if not isinstance(step, dict):
                    continue
                expected_actions = step.get("expected_actions", [])
                if isinstance(expected_actions, str):
                    expected_actions = [expected_actions]
                if "navigate" in expected_actions or step.get("action") == "navigate":
                    # Si no tiene URL, inyectar la URL resuelta
                    if not step.get("url") and not step.get("target_url"):
                        step["target_url"] = resolved_url
                        logger.info(f"[PLATFORM] resolved={resolved_platform} url={resolved_url}")
                        print(f"[DEBUG_AGENT] Resolved platform: {resolved_platform} -> {resolved_url}")
                        break
        elif "portal b" in goal_norm or "portal_b" in goal_norm:
            # Buscar el primer step que requiera navigate
            for step in payload.steps:
                if not isinstance(step, dict):
                    continue
                expected_actions = step.get("expected_actions", [])
                if isinstance(expected_actions, str):
                    expected_actions = [expected_actions]
                if "navigate" in expected_actions or step.get("action") == "navigate":
                    # Si no tiene URL, inyectar la URL por defecto
                    if not step.get("url") and not step.get("target_url"):
                        from backend.config import DEFAULT_PORTAL_B_URL
                        step["target_url"] = DEFAULT_PORTAL_B_URL
                        logger.info(f"[agent_answer_endpoint] Resolved portal B default URL -> {DEFAULT_PORTAL_B_URL}")
                        print(f"[DEBUG_AGENT] Resolved portal B default URL -> {DEFAULT_PORTAL_B_URL}")
                        break
        
        # Ejecutar primero todos los steps de navegación
        navigation_executed = False
        did_real_action = False  # v4.7 FIX: Detectar si se ejecutaron acciones reales (fill/click/select/upload/submit)
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
                    action_result_lower = action_result.lower()
                    
                    # Si fue navegación, marcar que se navegó
                    if "navigated" in action_result_lower:
                        navigation_executed = True
                    
                    # v4.7 FIX: Detectar acciones reales (no skips)
                    # Si la acción fue skip, no cuenta como acción real
                    is_skip = (
                        "skip" in action_result_lower or
                        "already at" in action_result_lower or
                        "already past" in action_result_lower
                    )
                    if not is_skip:
                        # Detectar si fue una acción real (fill/click/select/upload/submit)
                        if any(keyword in action_result_lower for keyword in [
                            "filled", "clicked", "selected", "uploaded", "submitted",
                            "fill", "click", "select", "upload", "submit"
                        ]):
                            did_real_action = True
            except Exception as e:
                logger.warning(f"[agent_answer_endpoint] Error al ejecutar step {step_index} con executor determinista: {e}", exc_info=True)
                # Continuar con el siguiente step aunque haya error
        
        # v2.8.0+: ActionPlanner - Generar acciones ejecutables si no las hay
        # v4.7 FIX: Continuar con DOM actions si:
        # - Se navegó Y no hay acciones ejecutables, O
        # - NO se ejecutaron acciones reales (aunque se haya skippeado navegación)
        should_generate_dom_actions = (
            (navigation_executed and not _has_executable_actions(payload.steps)) or
            (not did_real_action and browser.page is not None)
        )
        
        if should_generate_dom_actions:
            logger.info("[agent_answer_endpoint] Steps no tienen acciones ejecutables, generando desde DOM...")
            print("[DEBUG_AGENT] Steps no tienen acciones ejecutables, generando desde DOM...")
            
            try:
                # Obtener cliente LLM
                llm_client = getattr(app.state, "llm_client", None)
                if llm_client is None:
                    logger.warning("[agent_answer_endpoint] No llm_client disponible para ActionPlanner")
                else:
                    # Generar acciones ejecutables desde el DOM
                    # v4.9.0: Reutilizar memory_store si ya está inicializado, si no inicializarlo
                    if 'memory_store' not in locals() or memory_store is None:
                        try:
                            from backend.memory import MemoryStore
                            from backend.config import MEMORY_BASE_DIR
                            memory_store = MemoryStore(MEMORY_BASE_DIR)
                        except Exception as e:
                            logger.debug(f"[agent_answer_endpoint] No se pudo inicializar memory_store: {e}")
                            memory_store = None
                    
                    generated_actions = await generate_executable_actions_from_dom(
                        goal=payload.goal,
                        browser=browser,
                        llm_client=llm_client,
                        memory_store=memory_store,
                    )
                    
                    # v4.9.0: Si no se generaron acciones porque faltan datos, devolver pregunta
                    if generated_actions is None:
                        # Detectar qué falta
                        missing_info = []
                        if not memory_store:
                            missing_info.append("memoria")
                        else:
                            defaults = get_memory_defaults(portal="portal_a", memory_store=memory_store)
                            if not defaults.get("company_code"):
                                missing_info.append("empresa")
                            if not defaults.get("username"):
                                missing_info.append("usuario")
                            if not defaults.get("password"):
                                missing_info.append("contraseña")
                        
                        if missing_info:
                            question = f"¿Qué {'/'.join(missing_info)} debo usar para Portal A?"
                            logger.info(f"[agent_answer_endpoint] Solicitud de datos faltantes: {question}")
                            return AgentAnswerResponse(
                                goal=payload.goal,
                                final_answer=question,
                                steps=[],
                                source_url=None,
                                source_title=None,
                                sources=[],
                                sections=None,
                                structured_sources=None,
                                metrics_summary={
                                    "needs_user_input": True,
                                    "missing_fields": missing_info,
                                },
                                file_upload_instructions=None,
                                execution_plan=None,
                                execution_cancelled=None,
                                reasoning_spotlight=None,
                                planner_hints=None,
                                outcome_judge=None,
                                execution_mode=execution_mode,
                            )
                    
                    if generated_actions and len(generated_actions) > 0:
                        logger.info(f"[agent_answer_endpoint] Phase 1 actions: {len(generated_actions)}")
                        print(f"[DEBUG_AGENT] Phase 1 actions: {len(generated_actions)}")
                        
                        # v2.8.0+: Inicializar flags de ejecución (en memoria para esta ejecución)
                        execution_flags = {"upload_done": False, "submit_done": False, "sim_clicked": False}
                        
                        # v4.8+: Inicializar ExecutionPolicyState (una vez por ejecución)
                        from backend.agents.agent_runner import ExecutionPolicyState
                        policy_state = ExecutionPolicyState()
                        execution_context_base = {"goal": payload.goal, "execution_mode": execution_mode, "execution_flags": execution_flags, "policy_state": policy_state}
                        
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
                                # Usar execution_context_base que ya tiene policy_state inicializado
                                exec_ctx = execution_context_base.copy()
                                
                                action_result = await execute_step_with_playwright(
                                    step=step,
                                    step_index=step_index,
                                    browser=browser,
                                    execution_context=exec_ctx,
                                )
                                
                                # Verificar si debemos detener la ejecución (corte por éxito)
                                if policy_state.should_stop():
                                    if policy_state.log_stop_once():
                                        logger.info("[POLICY] Stop execution early due to SUCCESS result.")
                                        print("[POLICY] Stop execution early due to SUCCESS result.")
                                    # Romper el bucle de acciones y marcar que NO se deben generar fases siguientes
                                    break  # Salir del bucle de acciones
                                
                                # Actualizar flags en el contexto
                                if action_result and "upload" in action_result.lower():
                                    execution_flags["upload_done"] = True
                                if action_result and ("submit" in action_result.lower() or "clicked" in action_result.lower()):
                                    # Verificar si fue click en "Simular subida"
                                    if "simular subida" in str(step.get("selector", "")).lower() or "simular subida" in str(action_result).lower():
                                        execution_flags["submit_done"] = True
                                        execution_flags["sim_clicked"] = True
                                if action_result:
                                    logger.info(f"[agent_answer_endpoint] Acción generada {action_idx} ejecutada: {action_result}")
                                    print(f"[DEBUG_AGENT] Acción generada {action_idx} ejecutada: {action_result}")
                            except Exception as e:
                                logger.warning(f"[agent_answer_endpoint] Error al ejecutar acción generada {action_idx}: {e}", exc_info=True)
                                # Continuar con la siguiente acción aunque haya error
                        
                        # v2.8.0+: Segunda pasada - Verificar si la página cambió
                        # CORTE INMEDIATO: Si ya hay SUCCESS, NO generar fases siguientes
                        if policy_state.should_stop():
                            logger.info("[agent_answer_endpoint] SUCCESS detectado en Phase 1, cortando ejecución inmediatamente (no generar Phase 2/3)")
                            print("[DEBUG_AGENT] SUCCESS detectado en Phase 1, cortando ejecución inmediatamente (no generar Phase 2/3)")
                        elif browser.page:
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
                                
                                # v4.11.0: DOM-change replan para upload v2
                                # Si estamos en upload v2 y el DOM está listo sin cambio de URL, también generar Phase 3
                                is_upload_v2 = "/simulation/portal_a_v2/upload.html" in current_url.lower()
                                dom_ready_v2 = False
                                
                                if is_upload_v2 and not url_changed:
                                    from backend.agents.agent_runner import await_upload_form_render_v2
                                    if browser.page:
                                        dom_ready_v2 = await await_upload_form_render_v2(browser.page)
                                        if dom_ready_v2:
                                            logger.info("[DEBUG_AGENT] Upload v2 DOM ready without navigation -> generating next phase actions")
                                            print("[DEBUG_AGENT] Upload v2 DOM ready without navigation -> generating next phase actions")
                                
                                if url_changed or dom_ready_v2:
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
                                            memory_store=memory_store,
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
                                                    # Usar execution_context_base que ya tiene policy_state
                                                    exec_ctx_phase2 = execution_context_base.copy()
                                                    
                                                    action_result = await execute_step_with_playwright(
                                                        step=step,
                                                        step_index=step_index,
                                                        browser=browser,
                                                        execution_context=exec_ctx_phase2,
                                                    )
                                                    
                                                    # Verificar si debemos detener la ejecución (corte por éxito)
                                                    if policy_state.should_stop():
                                                        if policy_state.log_stop_once():
                                                            logger.info("[POLICY] Stop execution early due to SUCCESS result.")
                                                            print("[POLICY] Stop execution early due to SUCCESS result.")
                                                        break  # Salir del bucle de acciones
                                                    
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
                                            # CORTE INMEDIATO: Si ya hay SUCCESS, NO generar Phase 3
                                            if policy_state.should_stop():
                                                logger.info("[agent_answer_endpoint] SUCCESS detectado en Phase 2, cortando ejecución inmediatamente (no generar Phase 3)")
                                                print("[DEBUG_AGENT] SUCCESS detectado en Phase 2, cortando ejecución inmediatamente (no generar Phase 3)")
                                            elif browser.page:
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
                                                        # v4.11.0: DOM-change replan para upload v2
                                                        # Verificar si estamos en upload v2 y el DOM está listo
                                                        is_upload_v2 = "/simulation/portal_a_v2/upload.html" in current_url_phase2.lower()
                                                        url_changed_phase2 = (current_url and current_url_phase2 != current_url)
                                                        dom_ready_v2_phase2 = False
                                                        
                                                        if is_upload_v2 and not url_changed_phase2:
                                                            from backend.agents.agent_runner import await_upload_form_render_v2
                                                            dom_ready_v2_phase2 = await await_upload_form_render_v2(browser.page)
                                                            if dom_ready_v2_phase2:
                                                                logger.info("[DEBUG_AGENT] Upload v2 DOM ready without navigation (Phase 2->3) -> generating Phase 3 actions")
                                                                print("[DEBUG_AGENT] Upload v2 DOM ready without navigation (Phase 2->3) -> generating Phase 3 actions")
                                                        
                                                        if url_changed_phase2 or dom_ready_v2_phase2:
                                                            logger.info(f"[agent_answer_endpoint] URL cambió a upload.html ({current_url_phase2}) o DOM v2 ready, generando acciones de fase 3...")
                                                            print(f"[DEBUG_AGENT] URL cambió a upload.html ({current_url_phase2}) o DOM v2 ready, generando acciones de fase 3...")
                                                        
                                                        try:
                                                            # Generar acciones de tercera fase
                                                            phase3_actions = await generate_executable_actions_from_dom(
                                                                goal=payload.goal,
                                                                browser=browser,
                                                                llm_client=llm_client,
                                                                phase=3,
                                                                previous_url=current_url,
                                                                memory_store=memory_store,
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
                                                                        # Usar execution_context_base que ya tiene policy_state
                                                                        exec_ctx_phase3 = execution_context_base.copy()
                                                                        
                                                                        action_result = await execute_step_with_playwright(
                                                                            step=step,
                                                                            step_index=step_index,
                                                                            browser=browser,
                                                                            execution_context=exec_ctx_phase3,
                                                                        )
                                                                        
                                                                        # Verificar si debemos detener la ejecución (corte por éxito)
                                                                        if policy_state.should_stop():
                                                                            if policy_state.log_stop_once():
                                                                                logger.info("[POLICY] Stop execution early due to SUCCESS result.")
                                                                                print("[POLICY] Stop execution early due to SUCCESS result.")
                                                                            # Romper el bucle de acciones (última fase, no hay más fases)
                                                                            break  # Salir del bucle de acciones
                                                                        
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
    
    # v4.8+: Verificar si hubo policy_stop (SUCCESS detectado)
    policy_stop_detected = False
    try:
        # policy_state debería estar definido si se ejecutaron acciones
        if 'policy_state' in locals() and policy_state and policy_state.should_stop():
            policy_stop_detected = True
            logger.info("[agent_answer_endpoint] Policy stop detectado (SUCCESS), saltando run_llm_task_with_answer")
            print("[DEBUG_AGENT] Policy stop detectado (SUCCESS), saltando run_llm_task_with_answer")
    except NameError:
        # policy_state no está definido (no se ejecutaron acciones), continuar normal
        pass
    
    # v2.9.0: Pasar disabled_sub_goal_indices
    # v4.3.0: Pasar execution_mode
    # v4.8+: Saltar run_llm_task_with_answer si hubo policy_stop
    if not policy_stop_detected:
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
    else:
        # Construir respuesta final simple cuando hay policy_stop
        steps = []
        final_answer = "Ejecución completada: subida correcta (SUCCESS)."
        source_url = None
        source_title = None
        sources = []
        logger.info("[agent_answer_endpoint] Ejecución completada con policy_stop: %s", final_answer)
        print(f"[DEBUG_AGENT] Ejecución completada con policy_stop: {final_answer}")
        
        # v4.9.0: Guardar en memoria cuando hay SUCCESS
        if memory_store:
            try:
                # Detectar portal desde la URL
                portal = "portal_a"
                if browser.page:
                    current_url = browser.page.url
                    if "portal_b" in current_url.lower():
                        portal = "portal_b"
                
                # Cargar o crear PlatformMemory
                platform_memory = memory_store.load_platform(portal)
                if not platform_memory:
                    from backend.shared.models import PlatformMemory
                    platform_memory = PlatformMemory(platform=portal)
                
                # Extraer valores de las acciones ejecutadas desde execution_context_base
                # Buscar en las acciones generadas y ejecutadas
                if 'execution_context_base' in locals() and execution_context_base:
                    # Intentar extraer valores de las acciones ejecutadas
                    # Estos valores deberían estar en las acciones que se ejecutaron
                    # Por ahora, actualizamos last_seen
                    from datetime import datetime
                    platform_memory.last_seen = datetime.now()
                    
                    # TODO: Extraer company_code, username, password, worker_id, doc_type
                    # de las acciones ejecutadas cuando estén disponibles en el contexto
                    
                    # Guardar
                    memory_store.save_platform(platform_memory)
                    logger.info(f"[agent_answer_endpoint] Memoria actualizada para plataforma {portal}")
            except Exception as e:
                logger.warning(f"[agent_answer_endpoint] Error al guardar en memoria: {e}", exc_info=True)
    
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
