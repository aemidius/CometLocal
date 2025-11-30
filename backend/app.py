import sys
import asyncio
from typing import Optional

# En Windows, necesitamos un event loop que soporte subprocess (para Playwright)
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.browser.browser import BrowserController

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
    """
    Si el mensaje es del tipo:
      "abre https://www.google.com"
    el backend abrirá esa URL en el navegador controlado por Playwright.
    En cualquier otro caso, solo responde eco.
    """
    text = req.message.strip()
    opened_url: Optional[str] = None

    lower = text.lower()
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
    else:
        reply = (
            f"He recibido tu mensaje: '{text}'. "
            "En próximas versiones el agente actuará con más inteligencia."
        )

    return ChatResponse(agent_reply=reply, opened_url=opened_url)
