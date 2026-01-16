"""
Modelos para cola de ejecuciones CAE v1.8.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


CAEJobStatus = Literal[
    "QUEUED",
    "RUNNING",
    "SUCCESS",
    "PARTIAL_SUCCESS",
    "FAILED",
    "BLOCKED",
    "CANCELED",
]


class CAEJobProgressV1(BaseModel):
    """Progreso de ejecución de un job."""
    total_items: int = 0
    current_index: int = 0  # Índice del item actual (0-based)
    items_success: int = 0
    items_failed: int = 0
    items_blocked: int = 0
    percent: int = 0  # 0-100
    message: str = "En cola..."  # Mensaje breve del estado actual


class CAEJobV1(BaseModel):
    """Job de ejecución CAE."""
    job_id: str
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    plan_id: str
    scope_summary: dict  # { platform_key, company_key, person_key, mode }
    status: CAEJobStatus = "QUEUED"
    progress: CAEJobProgressV1 = Field(default_factory=CAEJobProgressV1)
    run_id: Optional[str] = None  # Cuando arranca ejecución real
    error: Optional[str] = None
    evidence_path: Optional[str] = None
    mode: dict = Field(default_factory=lambda: {"dry_run": False, "executor_mode": "FAKE"})  # { dry_run: bool, executor_mode: "FAKE"|"REAL" }
    cancel_requested: bool = False  # v1.9: Flag para cancelación
    retry_of: Optional[str] = None  # v1.9: ID del job original si es un retry

