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
        "stop"
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


class SourceInfo(BaseModel):
    url: str
    title: Optional[str] = None


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

