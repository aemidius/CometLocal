from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


class BrowserAction(BaseModel):
    """
    Represents an action that can be performed by the browser controller.
    This is the contract between the planner and the browser motor.
    """
    type: Literal[
        "open_url",
        "click_text",
        "fill_input",
        "press_key",
        "accept_cookies",
        "wait",
        "noop",
        "stop",
        "upload_file"  # v2.3.0: Upload de archivos en inputs type="file"
    ]
    args: Dict[str, Any] = Field(default_factory=dict)


class BrowserObservation(BaseModel):
    """
    Structured observation of the current page state, designed to be consumed
    by a planner (human or LLM). Contains only essential information for decision-making.
    """
    url: str
    title: str
    visible_text_excerpt: str
    clickable_texts: List[str]
    input_hints: List[str]


class StepResult(BaseModel):
    """
    Result of a browser step execution, containing the observation,
    the last action performed, any errors, and additional info.
    """
    observation: BrowserObservation
    last_action: Optional[BrowserAction] = None
    error: Optional[str] = None
    info: Dict[str, Any] = Field(default_factory=dict)


class AgentAnswerRequest(BaseModel):
    goal: str
    max_steps: int = 8
    # v2.1.0: Selección opcional de estrategias de contexto por petición
    context_strategies: Optional[List[str]] = None
    # v2.7.0: Selección explícita del perfil de ejecución
    execution_profile_name: Optional[str] = None  # "fast", "balanced", "thorough"
    # v2.8.0: Control de planificación y ejecución
    plan_only: Optional[bool] = False
    execution_confirmed: Optional[bool] = None
    # v2.9.0: Sub-objetivos deshabilitados en el plan
    disabled_sub_goal_indices: Optional[List[int]] = None


class SourceInfo(BaseModel):
    url: str
    title: Optional[str] = None


class FileUploadInstructionDTO(BaseModel):
    """
    DTO para instrucción de subida de archivo (versión serializable).
    v2.2.0: Versión serializable de FileUploadInstruction para la respuesta.
    """
    path: str
    description: str
    company: Optional[str] = None
    worker: Optional[str] = None
    doc_type: Optional[str] = None


class AgentAnswerResponse(BaseModel):
    goal: str
    final_answer: str
    steps: List[StepResult]
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    sources: List[SourceInfo] = []
    # v1.6.0: Campos opcionales para respuesta estructurada
    sections: Optional[List[Dict[str, Any]]] = None
    structured_sources: Optional[List[Dict[str, Any]]] = None
    metrics_summary: Optional[Dict[str, Any]] = None
    # v2.2.0: Instrucciones de subida de archivos
    file_upload_instructions: Optional[List[FileUploadInstructionDTO]] = None
    # v2.8.0: Plan de ejecución y estado de cancelación
    execution_plan: Optional[Dict[str, Any]] = None
    execution_cancelled: Optional[bool] = None


# v3.0.0: Modelos para ejecución batch autónoma
class BatchAgentGoal(BaseModel):
    """
    Un objetivo individual dentro de un batch.
    
    v3.0.0: Permite especificar configuración por objetivo o usar defaults del batch.
    """
    id: str  # identificador lógico (ej. "worker_123", "goal_1")
    goal: str  # texto completo del objetivo
    execution_profile_name: Optional[str] = None
    context_strategies: Optional[List[str]] = None


class BatchAgentRequest(BaseModel):
    """
    Petición para ejecutar un batch de objetivos.
    
    v3.0.0: Permite ejecutar múltiples objetivos de forma autónoma.
    """
    goals: List[BatchAgentGoal]
    # configuración global opcional:
    default_execution_profile_name: Optional[str] = None
    default_context_strategies: Optional[List[str]] = None
    max_consecutive_failures: Optional[int] = 5  # para abortar si todo va muy mal


class BatchAgentGoalResult(BaseModel):
    """
    Resultado de ejecutar un objetivo individual del batch.
    
    v3.0.0: Contiene toda la información de ejecución de un objetivo.
    """
    id: str
    goal: str
    success: bool
    error_message: Optional[str] = None
    final_answer: Optional[str] = None
    metrics_summary: Optional[Dict[str, Any]] = None  # resumen por objetivo
    sections: Optional[List[Dict[str, Any]]] = None  # secciones estructuradas si existen
    structured_sources: Optional[List[Dict[str, Any]]] = None
    file_upload_instructions: Optional[List[Dict[str, Any]]] = None


class BatchAgentResponse(BaseModel):
    """
    Respuesta completa de un batch de ejecución.
    
    v3.0.0: Contiene resultados por objetivo y resumen agregado.
    """
    goals: List[BatchAgentGoalResult]
    summary: Dict[str, Any]  # agregados globales (contadores, ratios, tiempo total, etc.)


# v3.1.0: Modelos específicos para batch CAE
class CAEWorker(BaseModel):
    """
    Trabajador para procesamiento batch CAE.
    
    v3.1.0: Representa un trabajador con su información y documentos requeridos.
    """
    id: str  # identificador interno (ej. DNI, código, etc.)
    full_name: str  # nombre completo
    company: Optional[str] = None
    required_docs: Optional[List[str]] = None  # ej. ["reconocimiento_medico", "formacion_prl"]


class CAEBatchRequest(BaseModel):
    """
    Petición batch específica para CAE.
    
    v3.1.0: Permite procesar múltiples trabajadores en una plataforma CAE.
    """
    platform: str  # nombre simbólico de la plataforma CAE (para log / futuro uso)
    company_name: str  # nombre de la empresa cliente
    workers: List[CAEWorker]
    execution_profile_name: Optional[str] = "balanced"
    context_strategies: Optional[List[str]] = None  # Por defecto ["cae"]
    # opcional: límite de fallos igual que en batch genérico
    max_consecutive_failures: Optional[int] = 5


# v3.2.0: Modelo para confirmación visual de acciones
class VisualActionResult(BaseModel):
    """
    Resultado de verificación visual de una acción crítica.
    
    v3.2.0: Permite confirmar que acciones como uploads o clicks en botones críticos
    han tenido el efecto esperado en la página.
    """
    action_type: str  # "click", "upload_file", "navigation"
    expected_effect: str  # descripción humana del efecto esperado
    confirmed: bool
    confidence: float  # 0.0 – 1.0
    evidence: Optional[str] = None  # texto visible encontrado que confirma o niega


class CAEWorkerDocStatus(BaseModel):
    """
    Estado de documentación de un trabajador tras procesamiento CAE.
    
    v3.1.0: Contiene información detallada sobre documentos subidos, faltantes y errores.
    v3.2.0: Añade visual_actions para auditoría de acciones visuales.
    """
    worker_id: str
    full_name: str
    success: bool
    missing_docs: List[str]
    uploaded_docs: List[str]
    upload_errors: List[str]
    notes: Optional[str] = None
    raw_answer: Optional[str] = None  # final_answer del agente para ese worker
    metrics_summary: Optional[Dict[str, Any]] = None
    visual_actions: Optional[List[VisualActionResult]] = None  # v3.2.0: Acciones visuales verificadas


class CAEBatchResponse(BaseModel):
    """
    Respuesta completa de un batch CAE.
    
    v3.1.0: Contiene estado de documentación por trabajador y resumen agregado.
    """
    platform: str
    company_name: str
    workers: List[CAEWorkerDocStatus]
    summary: Dict[str, Any]


# v2.2.0: Modelos para gestión de documentos
class DocumentRequest(BaseModel):
    """
    Petición lógica de documento por empresa/trabajador/tipo.
    """
    company: str
    worker: Optional[str] = None
    doc_type: Optional[str] = None  # "dni", "contrato", "formacion", "prl", "reconocimiento_medico", "otro"


class UploadInstruction(BaseModel):
    """
    Instrucción para subir un documento en un formulario web.
    """
    document: DocumentRequest
    target: str  # Descripción del destino, ej. "input_subir_documento" o "zona subir CAE"
    resolved_path: Optional[str] = None  # Ruta resuelta del documento (solo para debug interno)

