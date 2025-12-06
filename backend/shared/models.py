from typing import Any, Dict, List, Optional, Literal
from datetime import datetime, date
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
    
    v3.3.0: Añade campos OCR para texto extraído de capturas de pantalla.
    """
    url: str
    title: str
    visible_text_excerpt: str
    clickable_texts: List[str]
    input_hints: List[str]
    screenshot_path: Optional[str] = None  # v3.3.0: Ruta a captura de pantalla si está disponible
    ocr_text: Optional[str] = None  # v3.3.0: Texto extraído por OCR
    ocr_blocks: Optional[List[Dict[str, Any]]] = None  # v3.3.0: Bloques de texto OCR (serializable)


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
    # v4.3.0: Modo de ejecución (live por defecto, dry_run para simulación segura)
    execution_mode: Optional[str] = Field(
        default=None,
        description="Modo de ejecución: 'live' (por defecto) o 'dry_run' (simulación segura)",
    )


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


# v4.4.0: Modelos para análisis de documentos CAE
class DocumentAnalysisResult(BaseModel):
    """
    Resultado del análisis de un documento PDF para CAE.
    
    v4.4.0: Fase 1 - Extracción básica de fechas y trabajador.
    """
    doc_type: Optional[str] = None  # ej: "reconocimiento_medico", "formacion_prl"
    worker_name: Optional[str] = None
    company_name: Optional[str] = None
    
    issue_date: Optional[date] = None  # Fecha de emisión/realización
    expiry_date: Optional[date] = None  # Fecha de caducidad
    
    raw_dates: List[str] = Field(default_factory=list)  # Fechas encontradas en texto
    warnings: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)  # 0.0–1.0
    
    source_path: Optional[str] = None


# v4.5.0: Modelos para rellenado automático de formularios CAE
class FormFieldValue(BaseModel):
    """
    Valor a rellenar en un campo de formulario.
    
    v4.5.0: Representa un valor semántico (ej. issue_date) con su valor formateado.
    v4.6.0: Añade possible_labels para rellenado por etiquetas.
    """
    semantic_field: str  # "issue_date", "expiry_date", "worker_name", etc.
    value: str  # Ya formateado para meter en el input (ej. "2025-03-01")
    source: Optional[str] = None  # "document_analysis", "fallback", etc.
    confidence: Optional[float] = None  # Confianza en este valor específico
    possible_labels: List[str] = Field(default_factory=list)  # v4.6.0: Posibles textos de etiqueta


class DocumentFormFillPlan(BaseModel):
    """
    Plan de rellenado de formulario basado en análisis de documento.
    
    v4.5.0: Define qué campos semánticos se van a rellenar y con qué valores.
    """
    doc_type: Optional[str] = None
    worker_name: Optional[str] = None
    
    fields: List[FormFieldValue] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)  # Confianza global del plan


class FormFillInstruction(BaseModel):
    """
    Instrucción ejecutable para rellenar un formulario.
    
    v4.5.0: Mapea campos semánticos a selectores CSS del formulario actual.
    v4.6.0: Añade label_hints para rellenado por etiquetas.
    """
    # Mapeo de semantic_field -> selector CSS del formulario actual
    # Ejemplo: {"issue_date": "#issue_date", "expiry_date": "#expiry_date", "worker_name": "#worker_name"}
    field_selectors: Dict[str, str] = Field(default_factory=dict)
    
    # Plan de valores a rellenar
    plan: DocumentFormFillPlan
    
    # Contexto opcional (para debug / auditoría)
    form_context: Optional[str] = None  # ej: "cae_upload_form_v1"
    
    # v4.6.0: Mapeo semántico -> lista de posibles labels para rellenado por etiquetas
    label_hints: Dict[str, List[str]] = Field(default_factory=dict)


# v3.8.0: Modelos para Reasoning Spotlight
class ReasoningInterpretation(BaseModel):
    """
    Una interpretación alternativa del objetivo del usuario.
    
    v3.8.0: Representa una posible forma de entender el objetivo, con un nivel de confianza.
    """
    interpretation: str  # Descripción de cómo se interpreta el objetivo
    confidence: float  # Confianza en esta interpretación (0.0 - 1.0)


class ReasoningAmbiguity(BaseModel):
    """
    Una ambigüedad detectada en el objetivo del usuario.
    
    v3.8.0: Identifica áreas donde el objetivo puede ser ambiguo o poco claro.
    """
    description: str  # Descripción de la ambigüedad
    severity: str  # "low" | "medium" | "high"


class ReasoningQuestion(BaseModel):
    """
    Una pregunta de clarificación sugerida para el usuario.
    
    v3.8.0: Preguntas que ayudarían a desambiguar el objetivo antes de ejecutarlo.
    """
    question: str  # La pregunta a hacer al usuario
    rationale: Optional[str] = None  # Por qué esta pregunta es útil


class ReasoningSpotlight(BaseModel):
    """
    Análisis previo del objetivo del usuario antes de planificar o ejecutar.
    
    v3.8.0: Contiene interpretaciones alternativas, ambigüedades detectadas,
    preguntas de clarificación sugeridas, riesgos percibidos y notas del LLM.
    Este spotlight se genera ANTES de la planificación o ejecución.
    """
    raw_goal: str  # El objetivo original del usuario
    interpretations: List[ReasoningInterpretation] = Field(default_factory=list)  # Al menos 2 interpretaciones
    ambiguities: List[ReasoningAmbiguity] = Field(default_factory=list)  # Ambigüedades detectadas
    recommended_questions: List[ReasoningQuestion] = Field(default_factory=list)  # Preguntas de clarificación (0-3)
    perceived_risks: List[str] = Field(default_factory=list)  # Riesgos percibidos
    llm_notes: Optional[str] = None  # Notas breves del LLM (2-3 líneas)


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
    # v3.8.0: Reasoning Spotlight (análisis previo del objetivo)
    reasoning_spotlight: Optional[ReasoningSpotlight] = None
    # v4.0.0: Planner Hints (recomendaciones del LLM sobre el plan)
    planner_hints: Optional["PlannerHints"] = None
    # v4.1.0: Outcome Judge (auto-evaluación post-ejecución)
    outcome_judge: Optional["OutcomeJudgeReport"] = None
    # v4.3.0: Modo de ejecución usado
    execution_mode: Optional[str] = None  # "live" o "dry_run"


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
    # v4.3.0: Modo de ejecución específico para este goal (opcional)
    execution_mode: Optional[str] = None  # "live" o "dry_run"


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
    # v4.3.0: Modo de ejecución por defecto para todo el batch
    default_execution_mode: Optional[str] = None  # "live" o "dry_run"


class BatchAgentGoalResult(BaseModel):
    """
    Resultado de ejecutar un objetivo individual del batch.
    
    v3.0.0: Contiene toda la información de ejecución de un objetivo.
    v4.1.0: Añade outcome_judge para auto-evaluación post-ejecución.
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
    outcome_judge: Optional["OutcomeJudgeReport"] = None  # v4.1.0: Auto-evaluación post-ejecución


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
    # v4.3.0: Modo de ejecución por defecto para todo el batch CAE
    execution_mode: Optional[str] = None  # "live" o "dry_run"


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


# v3.4.0: Modelo para objetivos visuales detectados
class VisualTarget(BaseModel):
    """
    Botón o elemento visual detectado en una captura de pantalla.
    
    v3.4.0: Representa un botón detectado mediante OCR o heurísticas,
    con sus coordenadas para permitir clicks por pantalla.
    """
    label: str  # "guardar", "adjuntar", "confirmar", etc.
    x: Optional[int] = None  # coordenada X del centro o del click
    y: Optional[int] = None  # coordenada Y del centro o del click
    width: Optional[int] = None
    height: Optional[int] = None
    confidence: float = 0.0  # confianza de la detección (0.0 - 1.0)
    source: Optional[str] = None  # "ocr_block", "heuristic", etc.
    text: Optional[str] = None  # texto OCR asociado (ej. "Guardar cambios")


# v3.5.0: Modelo para estado visual del flujo
class VisualFlowState(BaseModel):
    """
    Estado visual del flujo actual, especialmente útil para formularios CAE/upload.
    
    v3.5.0: Representa el estado visual del flujo de trabajo (ej. "archivo ya adjuntado",
    "pendiente de guardar", "confirmado", etc.) para orientar mejor la recuperación visual
    y el análisis de resultados.
    """
    stage: str = "unknown"  # "idle" | "select_file" | "file_selected" | "uploaded" | "saved" | "confirmed" | "error" | "unknown"
    last_action: Optional[str] = None  # ej. "click_upload_button", "click_save_button", "upload_file"
    pending_actions: List[str] = Field(default_factory=list)  # ej. ["click_save_button", "click_confirm_button"]
    notes: Optional[str] = None  # explicación humana breve
    confidence: float = 0.0  # confianza en la inferencia del estado (0.0 - 1.0)


# v3.6.0: Modelos para expectativas y contratos visuales
class VisualExpectation(BaseModel):
    """
    Expectativa visual sobre el estado que debería observarse tras una acción.
    
    v3.6.0: Define qué estado visual esperamos ver después de ejecutar una acción crítica
    (ej. upload, guardar, confirmar) para poder evaluar si el flujo está yendo como debería.
    """
    expected_stage: Optional[str] = None  # ej. "file_selected", "saved", "confirmed"
    allowed_stages: List[str] = Field(default_factory=list)  # etapas aceptables (ej. ["saved", "confirmed"])
    expected_keywords: List[str] = Field(default_factory=list)  # palabras clave que deberían aparecer en el texto
    description: Optional[str] = None  # descripción humana
    severity: str = "normal"  # "normal" | "critical"


class VisualContractResult(BaseModel):
    """
    Resultado de la evaluación de un contrato visual (expectativa vs estado observado).
    
    v3.6.0: Representa si el estado visual observado cumple con la expectativa definida
    para una acción crítica, permitiendo detectar violaciones y desajustes en el flujo.
    """
    outcome: str  # "match" | "mismatch" | "violation" | "unknown"
    expected_stage: Optional[str] = None
    actual_stage: Optional[str] = None
    description: Optional[str] = None
    severity: str = "normal"


# v3.7.0: Modelo para intenciones del agente
class AgentIntent(BaseModel):
    """
    Intención explícita del agente para una acción crítica.
    
    v3.7.0: Representa qué está intentando hacer el agente con una acción específica,
    permitiendo trazar la intención → acción → estado visual → contrato.
    """
    intent_type: str  # ej. "select_file", "upload_file", "save_changes", "confirm_submission"
    description: Optional[str] = None  # descripción humana: "Seleccionar el archivo de reconocimiento médico"
    related_stage: Optional[str] = None  # stage de VisualFlowState al que apunta: "file_selected", "uploaded", "saved", "confirmed"
    criticality: str = "normal"  # "normal" | "critical"
    tags: List[str] = Field(default_factory=list)  # tags libres: ["cae", "upload", "worker_doc"]
    sub_goal_index: Optional[int] = None


# v3.9.0: Modelos para memoria persistente
# v4.2.0: Extendido con campos de calidad histórica (OutcomeJudge)
class WorkerMemory(BaseModel):
    """
    Memoria persistente de un trabajador.
    
    v3.9.0: Almacena historial de documentación CAE por trabajador,
    incluyendo documentos exitosos, fallidos y notas.
    v4.2.0: Añade campos de calidad histórica basados en OutcomeJudge.
    """
    worker_id: str
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    successful_docs: Dict[str, int] = Field(default_factory=dict)  # doc_type -> contador de éxitos
    failed_docs: Dict[str, int] = Field(default_factory=dict)  # doc_type -> contador de fallos
    last_seen: Optional[datetime] = None
    notes: Optional[str] = None
    # v4.2.0: Campos de calidad histórica
    last_outcome_score: Optional[float] = None  # 0.0-1.0 (escala de OutcomeJudge)
    best_outcome_score: Optional[float] = None
    worst_outcome_score: Optional[float] = None
    outcome_run_count: int = 0
    last_outcome_issues: Optional[List[str]] = None
    last_outcome_timestamp: Optional[datetime] = None
    outcome_history: Optional[List[Dict[str, Any]]] = None  # Últimos 10 ejecuciones


class CompanyMemory(BaseModel):
    """
    Memoria persistente de una empresa.
    
    v3.9.0: Almacena patrones de documentación por empresa y plataforma,
    incluyendo qué documentos suelen requerirse, faltar o dar error.
    v4.2.0: Añade agregados de calidad histórica basados en OutcomeJudge.
    """
    company_name: str
    platform: Optional[str] = None
    required_docs_counts: Dict[str, int] = Field(default_factory=dict)  # doc_type -> veces requerido
    missing_docs_counts: Dict[str, int] = Field(default_factory=dict)  # doc_type -> veces que faltó
    upload_error_counts: Dict[str, int] = Field(default_factory=dict)  # doc_type -> veces con error
    last_seen: Optional[datetime] = None
    notes: Optional[str] = None
    # v4.2.0: Agregados de calidad histórica
    avg_outcome_score: Optional[float] = None  # Media de scores de todos los workers
    outcome_run_count: int = 0
    last_outcome_timestamp: Optional[datetime] = None
    common_issues: Optional[List[str]] = None  # Problemas frecuentes promocionados desde workers


class PlatformMemory(BaseModel):
    """
    Memoria persistente de una plataforma CAE.
    
    v3.9.0: Almacena patrones de comportamiento de la plataforma,
    como uso de clicks visuales, recuperación visual, errores de upload, etc.
    v4.2.0: Añade agregados globales de calidad histórica basados en OutcomeJudge.
    """
    platform: str
    visual_click_usage: int = 0
    visual_recovery_usage: int = 0
    upload_error_counts: int = 0
    ocr_usage: int = 0
    last_seen: Optional[datetime] = None
    notes: Optional[str] = None
    # v4.2.0: Agregados globales de calidad histórica
    avg_outcome_score: Optional[float] = None  # Media de scores de todas las empresas
    outcome_run_count: int = 0
    last_outcome_timestamp: Optional[datetime] = None
    common_issues: Optional[List[str]] = None  # Problemas frecuentes promocionados desde empresas


# v4.0.0: Modelos para Planner Hints (recomendaciones del LLM sobre el plan)
class PlannerHintSubGoal(BaseModel):
    """
    Sugerencia del LLM para un sub-objetivo específico.
    
    v4.0.0: Contiene recomendaciones sobre prioridad, riesgo y si ejecutar o no.
    """
    sub_goal_index: int
    sub_goal_text: str
    suggested_enabled: Optional[bool] = None  # True/False si el LLM recomienda algo
    priority: Optional[str] = None  # "low" | "medium" | "high"
    risk_level: Optional[str] = None  # "low" | "medium" | "high"
    rationale: Optional[str] = None


class PlannerHintProfileSuggestion(BaseModel):
    """
    Sugerencia del LLM para cambiar el perfil de ejecución.
    
    v4.0.0: El LLM puede recomendar cambiar de fast/balanced/thorough.
    """
    suggested_profile: Optional[str] = None  # "fast" | "balanced" | "thorough"
    rationale: Optional[str] = None


class PlannerHintGlobal(BaseModel):
    """
    Insights globales del LLM sobre el plan completo.
    
    v4.0.0: Resumen, riesgos y oportunidades detectadas por el LLM.
    """
    summary: Optional[str] = None
    risks: List[str] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)


class PlannerHints(BaseModel):
    """
    Recomendaciones del LLM sobre el plan de ejecución.
    
    v4.0.0: El LLM revisa el objetivo, ReasoningSpotlight, ExecutionPlan y memoria
    para generar sugerencias sobre qué sub-objetivos son críticos, qué riesgos ve,
    si recomienda cambiar el perfil de ejecución, etc.
    """
    goal: str
    execution_profile_name: Optional[str] = None
    context_strategies: Optional[List[str]] = None
    sub_goals: List[PlannerHintSubGoal] = Field(default_factory=list)
    profile_suggestion: Optional[PlannerHintProfileSuggestion] = None
    global_insights: Optional[PlannerHintGlobal] = None
    llm_raw_notes: Optional[str] = None  # dump del razonamiento que queramos conservar


# v4.1.0: Modelos para Outcome Judge (auto-evaluación post-ejecución)
class OutcomeSubGoalReview(BaseModel):
    """
    Revisión de un sub-objetivo individual por el Outcome Judge.
    
    v4.1.0: Contiene evaluación de éxito, puntuación, problemas detectados,
    fortalezas y sugerencias de mejora para ese sub-objetivo específico.
    """
    sub_goal_index: int
    sub_goal_text: str
    success: Optional[bool] = None
    score: Optional[float] = None  # 0.0–1.0
    issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    suggested_retries: Optional[bool] = None
    suggested_profile: Optional[str] = None  # "fast" | "balanced" | "thorough" | None
    suggested_changes: Optional[str] = None  # Texto breve


class OutcomeGlobalReview(BaseModel):
    """
    Revisión global de la ejecución completa.
    
    v4.1.0: Contiene evaluación general de éxito, puntuación global,
    problemas principales, fortalezas y recomendaciones de alto nivel.
    """
    overall_success: Optional[bool] = None
    global_score: Optional[float] = None  # 0.0–1.0
    main_issues: List[str] = Field(default_factory=list)
    main_strengths: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class OutcomeJudgeReport(BaseModel):
    """
    Informe completo del Outcome Judge tras la ejecución.
    
    v4.1.0: El LLM analiza pasos, métricas, planner_hints, spotlight y memoria
    para generar un informe estructurado de calidad, problemas detectados
    y recomendaciones para futuras ejecuciones.
    """
    goal: str
    execution_profile_name: Optional[str] = None
    context_strategies: Optional[List[str]] = None
    global_review: Optional[OutcomeGlobalReview] = None
    sub_goals: List[OutcomeSubGoalReview] = Field(default_factory=list)
    # Pistas sobre qué cambiar la próxima vez (no lo aplicamos automáticamente)
    next_run_profile_suggestion: Optional[str] = None
    next_run_notes: Optional[str] = None
    llm_raw_notes: Optional[str] = None


class CAEWorkerDocStatus(BaseModel):
    """
    Estado de documentación de un trabajador tras procesamiento CAE.
    
    v3.1.0: Contiene información detallada sobre documentos subidos, faltantes y errores.
    v3.2.0: Añade visual_actions para auditoría de acciones visuales.
    v3.3.0: Añade campos para estado CAE extraído desde OCR.
    v3.9.0: Añade memory_summary con información resumida de memoria persistente.
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
    cae_status: Optional[str] = None  # v3.3.0: Estado CAE extraído (vigente/caducado/pendiente/no_apto)
    cae_status_evidence: Optional[List[str]] = None  # v3.3.0: Fragmentos de texto que justifican el estado
    cae_expiry_dates: Optional[List[str]] = None  # v3.3.0: Fechas de caducidad detectadas (YYYY-MM-DD)
    memory_summary: Optional[Dict[str, Any]] = None  # v3.9.0: Información resumida de memoria persistente
    memory_summary_outcome: Optional[Dict[str, Any]] = None  # v4.2.0: Resumen de calidad histórica (scores, issues)
    regression_flag: Optional[Dict[str, Any]] = None  # v4.2.0: Flag de regresión detectada


class CAEBatchResponse(BaseModel):
    """
    Respuesta completa de un batch CAE.
    
    v3.1.0: Contiene estado de documentación por trabajador y resumen agregado.
    v3.9.0: Añade memory_summary con visión global de memoria persistente aplicada.
    """
    platform: str
    company_name: str
    workers: List[CAEWorkerDocStatus]
    summary: Dict[str, Any]
    memory_summary: Optional[Dict[str, Any]] = None  # v3.9.0: Visión global de memoria persistente


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

