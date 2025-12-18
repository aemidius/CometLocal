from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import logging

from backend.browser.browser import BrowserController
from backend.agents.agent_runner import run_training_scenario_agent

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/training",
    tags=["training"],
)


# Variable global para almacenar el browser (se establece desde app.py)
_training_browser: Optional[BrowserController] = None


def set_training_browser(browser_instance: BrowserController):
    """
    Establece la instancia del browser para usar en training.
    Se llama desde app.py durante la inicialización.
    """
    global _training_browser
    _training_browser = browser_instance


async def get_browser() -> BrowserController:
    """
    Obtiene la instancia del browser.
    """
    if _training_browser is None:
        raise HTTPException(
            status_code=500,
            detail="Browser no está disponible. Asegúrate de que el backend se ha iniciado correctamente."
        )
    return _training_browser


def _shorten_text(text: str, max_length: int = 400) -> str:
    """
    Acorta un texto largo para mostrar en la UI.

    - Si el texto es más corto que max_length, se devuelve tal cual.
    - Si es más largo, se trunca y se añade "..." al final.
    """
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


class TrainingRunRequest(BaseModel):
    """
    Petición para ejecutar un escenario de entrenamiento.
    De momento se usa sólo como stub: todavía no llamamos al agente real.
    """
    scenario_id: str
    execution_mode: Optional[str] = "dry_run"


class TrainingRunResponse(BaseModel):
    """
    Respuesta simplificada de la ejecución de entrenamiento.

    Más adelante se ampliará para incluir:
    - resumen del agente
    - OutcomeJudge
    - métricas
    """
    scenario_id: str
    execution_mode: str
    status: str
    message: str


@router.post("/run-scenario", response_model=TrainingRunResponse)
async def run_training_scenario(
    payload: TrainingRunRequest,
    browser: BrowserController = Depends(get_browser),
) -> TrainingRunResponse:
    """
    Ejecuta el agente en modo dry_run sobre un escenario de simulación.

    - Siempre fuerza execution_mode="dry_run", aunque el cliente envíe otro.
    - Usa la lógica normal del agente (no un stub).
    - Resume el resultado para la Training UI.
    """
    scenario_id = (payload.scenario_id or "").strip()
    if not scenario_id:
        raise HTTPException(status_code=400, detail="scenario_id vacío o inválido")

    execution_mode = "dry_run"  # Siempre forzar dry_run para training

    try:
        steps, final_answer, source_url, source_title, sources = await run_training_scenario_agent(
            scenario_id=scenario_id,
            browser=browser,
            max_steps=10,
        )
    except ValueError as e:
        # Escenario no encontrado u otro problema de validación
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        # Cualquier error inesperado del agente NO debe tirar abajo el backend
        logger.exception("Error ejecutando escenario de training: %s", e)
        return TrainingRunResponse(
            scenario_id=scenario_id,
            execution_mode=execution_mode,
            status="error",
            message="Error interno al ejecutar el agente en modo training. Revisa los logs del backend.",
        )

    # Opcional: loggear un resumen más detallado para desarrolladores
    try:
        logger.debug(
            "Training scenario '%s' completed: steps=%d, final_answer=%r, source_url=%r",
            scenario_id,
            len(steps) if steps else 0,
            final_answer[:100] if final_answer else None,
            source_url,
        )
    except Exception:
        # Si por lo que sea fallara la serialización, no queremos romper la ejecución
        logger.debug("Training scenario '%s' completed (no se pudo serializar para log).", scenario_id)

    # Construir el mensaje de resumen para la Training UI
    # 1) Resumen principal corto
    main_summary = None

    if final_answer:
        main_summary = final_answer
    else:
        main_summary = "Ejecución de training completada. Revisa la UI principal o los logs para más detalle."

    main_summary = _shorten_text(main_summary, max_length=400)

    # 2) Información breve del OutcomeJudge (si existe)
    details = []

    # Intentar extraer outcome_judge de las métricas del último step
    if steps:
        last_step = steps[-1]
        if last_step.info and "metrics" in last_step.info:
            metrics = last_step.info["metrics"]
            if isinstance(metrics, dict) and "summary" in metrics:
                summary = metrics["summary"]
                # Intentar extraer información útil del outcome_judge
                if "outcome_judge_info" in summary:
                    oj_info = summary["outcome_judge_info"]
                    if isinstance(oj_info, dict):
                        # Extraer score global (outcome_global_score en el formato de métricas)
                        global_score = oj_info.get("outcome_global_score")
                        if global_score is not None:
                            # Formatear score como porcentaje (0.0-1.0 -> 0-100%)
                            if isinstance(global_score, (int, float)):
                                if 0.0 <= global_score <= 1.0:
                                    score_str = f"{int(global_score * 100)}%"
                                else:
                                    score_str = f"{int(global_score)}"
                            else:
                                score_str = str(global_score)
                            details.append(f"Score: {score_str}")

                            # Determinar veredicto basado en el score
                            if isinstance(global_score, (int, float)):
                                if global_score >= 0.7:
                                    verdict_str = "OK"
                                elif global_score >= 0.5:
                                    verdict_str = "Parcial"
                                else:
                                    verdict_str = "Fallo"
                                details.append(f"Veredicto: {verdict_str}")

    # 3) Mensaje final
    if details:
        message = f"{main_summary} | " + " ".join(details)
    else:
        message = main_summary

    return TrainingRunResponse(
        scenario_id=scenario_id,
        execution_mode=execution_mode,
        status="ok",
        message=message,
    )

