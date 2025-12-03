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
from backend.shared.models import StepResult, AgentAnswerRequest, AgentAnswerResponse, SourceInfo
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
    steps, final_answer, source_url, source_title, sources = await run_llm_task_with_answer(
        goal=payload.goal,
        browser=browser,
        max_steps=payload.max_steps,
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
    )
