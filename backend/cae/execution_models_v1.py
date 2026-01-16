"""
Modelos para la ejecución de planes CAE v1.2.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel


class ChallengeRequestV1(BaseModel):
    """Request para obtener un challenge de ejecución."""
    pass


class ChallengeResponseV1(BaseModel):
    """Respuesta con challenge para confirmar ejecución."""
    plan_id: str
    challenge_token: str
    prompt: str  # "Escribe EXACTAMENTE: EJECUTAR <plan_id>"


class ExecuteRequestV1(BaseModel):
    """Request para ejecutar un plan."""
    challenge_token: str
    challenge_response: str
    dry_run: bool = False


class RunResultV1(BaseModel):
    """Resultado de la ejecución de un plan."""
    run_id: str
    status: Literal["SUCCESS", "FAILED", "BLOCKED", "PARTIAL_SUCCESS", "CANCELED"]  # v1.9: Añadido CANCELED
    evidence_path: str
    summary: dict
    error: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None



