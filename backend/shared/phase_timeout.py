"""
Watchdogs y timeouts por fase.

SPRINT C2.16: Timeouts adaptativos por fase con evidencias automáticas.
"""
from __future__ import annotations

from typing import Callable, Any, Dict, Optional
import time
import signal
from pathlib import Path
import os
from backend.shared.evidence_helper import generate_timeout_evidence


# Timeouts por defecto (segundos)
DEFAULT_TIMEOUTS = {
    "login": 60,
    "navigation": 60,
    "grid_load": 60,
    "upload": 90,
    "verification": 60,
    "pagination": 60,
}


class PhaseTimeoutError(Exception):
    """Excepción lanzada cuando se excede el timeout de una fase."""
    def __init__(self, phase: str, timeout_s: float, message: str = ""):
        self.phase = phase
        self.timeout_s = timeout_s
        self.message = message or f"Timeout in phase '{phase}' after {timeout_s}s"
        super().__init__(self.message)


def run_with_phase_timeout(
    phase: str,
    fn: Callable[[], Any],
    timeout_s: Optional[float] = None,
    on_timeout_evidence: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Any:
    """
    Ejecuta una función con timeout por fase.
    
    Args:
        phase: Fase ("login", "navigation", "grid_load", "upload", "verification", "pagination")
        fn: Función a ejecutar (sin parámetros)
        timeout_s: Timeout en segundos (si None, usa DEFAULT_TIMEOUTS[phase])
        on_timeout_evidence: Callback para generar evidencia en timeout (debe retornar dict con paths)
    
    Returns:
        Resultado de fn() si se completa a tiempo
    
    Raises:
        TimeoutError si se excede el timeout
    """
    if timeout_s is None:
        timeout_s = DEFAULT_TIMEOUTS.get(phase, 60)
    
    start_time = time.time()
    
    # En Windows, signal.alarm no está disponible, usar threading.Timer
    import threading
    
    timeout_occurred = threading.Event()
    timeout_info = {"occurred": False}
    
    def timeout_handler():
        timeout_occurred.set()
        timeout_info["occurred"] = True
    
    timer = threading.Timer(timeout_s, timeout_handler)
    timer.start()
    
    try:
        result = fn()
        elapsed = time.time() - start_time
        
        # Si el timer aún está activo, cancelarlo
        if timer.is_alive():
            timer.cancel()
        
        # Si timeout ocurrió pero la función terminó justo antes, verificar
        if timeout_info["occurred"]:
            raise PhaseTimeoutError(phase, timeout_s, f"Function completed but timeout was triggered")
        
        if elapsed > timeout_s * 0.9:  # Warning si está cerca del timeout
            print(f"[TIMEOUT][{phase}] ⚠️ Función completada en {elapsed:.2f}s (cerca del timeout de {timeout_s}s)")
        
        return result
    
    except PhaseTimeoutError:
        raise
    except Exception as e:
        # Si es otra excepción, cancelar timer y re-lanzar
        if timer.is_alive():
            timer.cancel()
        raise e
    finally:
        if timer.is_alive():
            timer.cancel()
    
    # Si llegamos aquí, timeout ocurrió
    elapsed = time.time() - start_time
    
    # Generar evidencia si hay callback
    evidence = {}
    if on_timeout_evidence:
        try:
            evidence = on_timeout_evidence()
        except Exception as ev_error:
            print(f"[TIMEOUT][{phase}] ⚠️ Error generando evidencia: {ev_error}")
    
    raise TimeoutError(
        phase,
        timeout_s,
        f"Timeout after {elapsed:.2f}s. Evidence: {evidence}",
    )


async def run_with_phase_timeout_async(
    phase: str,
    fn: Callable[[], Any],
    timeout_s: Optional[float] = None,
    on_timeout_evidence: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Any:
    """
    Versión async de run_with_phase_timeout.
    
    Args:
        phase: Fase ("login", "navigation", "grid_load", "upload", "verification", "pagination")
        fn: Función async a ejecutar (sin parámetros)
        timeout_s: Timeout en segundos (si None, usa DEFAULT_TIMEOUTS[phase])
        on_timeout_evidence: Callback para generar evidencia en timeout (debe retornar dict con paths)
    
    Returns:
        Resultado de fn() si se completa a tiempo
    
    Raises:
        TimeoutError si se excede el timeout
    """
    import asyncio
    
    if timeout_s is None:
        timeout_s = DEFAULT_TIMEOUTS.get(phase, 60)
    
    start_time = time.time()
    
    try:
        result = await asyncio.wait_for(fn(), timeout=timeout_s)
        elapsed = time.time() - start_time
        
        if elapsed > timeout_s * 0.9:  # Warning si está cerca del timeout
            print(f"[TIMEOUT][{phase}] ⚠️ Función completada en {elapsed:.2f}s (cerca del timeout de {timeout_s}s)")
        
        return result
    
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        
        # Generar evidencia si hay callback
        evidence = {}
        if on_timeout_evidence:
            try:
                evidence = on_timeout_evidence()
            except Exception as ev_error:
                print(f"[TIMEOUT][{phase}] ⚠️ Error generando evidencia: {ev_error}")
        
        raise PhaseTimeoutError(
            phase,
            timeout_s,
            f"Timeout after {elapsed:.2f}s. Evidence: {evidence}",
        )
