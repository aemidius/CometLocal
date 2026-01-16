"""
HeadfulRunManager: Gestiona runs headful persistentes en memoria.

Mantiene navegadores Playwright abiertos asociados a run_id para
permitir ejecución secuencial de acciones con supervisión humana.
"""

from __future__ import annotations

import os
import time
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from playwright.sync_api import Browser, BrowserContext, Page
from backend.runs.run_timeline import RunTimeline, EventType


@dataclass
class HeadfulRun:
    """Representa un run headful activo."""
    run_id: str
    browser: Browser
    context: BrowserContext
    page: Page
    started_at: float
    storage_state_path: str
    timeline: RunTimeline = field(default=None)
    
    def __post_init__(self):
        """Inicializa timeline si no existe."""
        if self.timeline is None:
            self.timeline = RunTimeline(self.run_id)
            self.timeline.add_event(EventType.INFO, f"Run headful iniciado (ID: {self.run_id})")


class HeadfulRunManager:
    """
    Manager singleton para runs headful persistentes.
    
    Solo permite runs en ENVIRONMENT=dev.
    Si se intenta abrir un run ya activo, devuelve el existente.
    """
    
    _instance: Optional[HeadfulRunManager] = None
    _runs: Dict[str, HeadfulRun]
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._runs = {}
        return cls._instance
    
    def start_run(
        self,
        run_id: str,
        storage_state_path: str,
        browser: Browser,
        context: BrowserContext,
        page: Page,
    ) -> HeadfulRun:
        """
        Inicia o recupera un run headful.
        
        Si el run ya existe, devuelve el existente.
        Si no, crea uno nuevo.
        """
        # Validar ENVIRONMENT
        if os.getenv("ENVIRONMENT", "").lower() != "dev":
            raise RuntimeError("HeadfulRunManager solo está disponible en ENVIRONMENT=dev")
        
        # Si ya existe, devolver el existente
        if run_id in self._runs:
            return self._runs[run_id]
        
        # Crear nuevo run
        run = HeadfulRun(
            run_id=run_id,
            browser=browser,
            context=context,
            page=page,
            started_at=time.time(),
            storage_state_path=storage_state_path,
        )
        self._runs[run_id] = run
        return run
    
    def get_run(self, run_id: str) -> Optional[HeadfulRun]:
        """Recupera un run activo por run_id."""
        return self._runs.get(run_id)
    
    def close_run(self, run_id: str) -> bool:
        """
        Cierra un run y elimina del manager.
        
        Retorna True si el run existía y se cerró, False si no existía.
        """
        run = self._runs.pop(run_id, None)
        if run is None:
            return False
        
        try:
            run.browser.close()
        except Exception:
            pass  # Ignorar errores al cerrar
        
        return True
    
    def list_runs(self) -> Dict[str, Dict[str, Any]]:
        """Lista todos los runs activos (sin exponer objetos internos)."""
        return {
            run_id: {
                "run_id": run.run_id,
                "started_at": run.started_at,
                "storage_state_path": run.storage_state_path,
            }
            for run_id, run in self._runs.items()
        }
    
    def has_run(self, run_id: str) -> bool:
        """Verifica si un run está activo."""
        return run_id in self._runs
