"""
Política de reintentos inteligente.

SPRINT C2.16: Retry policy con backoff, jitter y límites por fase.
"""
from __future__ import annotations

from typing import Callable, Any, Dict, Optional, List
import time
import random
import os


# Configuración por defecto
MAX_RETRIES_DEFAULT = 2
BACKOFF_BASE_MS = 500
BACKOFF_MULTIPLIER = 1.5
JITTER_MAX_MS = 250

# Overrides por fase
PHASE_MAX_RETRIES = {
    "login": 1,  # Si falla 2 veces, abort
    "navigation": 2,
    "grid_load": 2,
    "upload": 0,  # NO repetir upload por defecto (solo click intercepted)
    "verification": 1,  # 1 retry para refrescar listado
    "pagination": 2,
}

# Error codes que permiten retry en upload (excepciones)
UPLOAD_RETRYABLE_ERROR_CODES = [
    "upload_click_intercepted",
    "overlay_blocking",
    "timeout_upload",  # SPRINT C2.16.1: Solo si upload_attempted=false (se maneja en get_max_retries_for_phase)
]

# Error codes con retry limitado a 1
SINGLE_RETRY_ERROR_CODES = [
    "item_not_found_before_upload",  # SPRINT C2.16.1: Solo 1 retry con refresh
]


def calculate_backoff(attempt: int, base_ms: int = BACKOFF_BASE_MS, multiplier: float = BACKOFF_MULTIPLIER) -> int:
    """Calcula backoff exponencial suave."""
    backoff_ms = base_ms * (multiplier ** (attempt - 1))
    return int(backoff_ms)


def add_jitter(backoff_ms: int, max_jitter_ms: int = JITTER_MAX_MS) -> int:
    """Añade jitter aleatorio al backoff."""
    jitter = random.randint(0, max_jitter_ms)
    return backoff_ms + jitter


def get_max_retries_for_phase(phase: str, error_code: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> int:
    """
    Obtiene el máximo de reintentos para una fase.
    
    Args:
        phase: Fase ("login", "navigation", "grid_load", "upload", "verification", "pagination")
        error_code: Código de error (para excepciones en upload)
        context: Contexto adicional (para verificar upload_attempted, etc.)
    
    Returns:
        Número máximo de reintentos
    """
    # SPRINT C2.16.1: Error codes con retry limitado a 1
    if error_code in SINGLE_RETRY_ERROR_CODES:
        return 1
    
    # Override especial para upload: solo retry si es error retryable
    if phase == "upload":
        # SPRINT C2.16.1: timeout_upload solo retry si upload_attempted=false
        if error_code == "timeout_upload":
            if context and context.get("upload_attempted", False):
                return 0  # Si ya se intentó upload, no retry
            return 1  # Si no se intentó, 1 retry
        
        if error_code in UPLOAD_RETRYABLE_ERROR_CODES:
            return 1  # 1 retry para click intercepted, overlay_blocking
        return 0  # No retry por defecto
    
    return PHASE_MAX_RETRIES.get(phase, MAX_RETRIES_DEFAULT)


def retry_with_policy(
    fn: Callable[[], Any],
    phase: str,
    error_code: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,  # SPRINT C2.16.1: Contexto para decisión de retry
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    on_final_failure: Optional[Callable[[Exception, List[Exception]], None]] = None,
    max_retries: Optional[int] = None,
) -> Any:
    """
    Ejecuta una función con política de reintentos.
    
    Args:
        fn: Función a ejecutar (sin parámetros)
        phase: Fase donde se ejecuta
        error_code: Código de error conocido (si ya se clasificó)
        on_retry: Callback llamado en cada retry (attempt, exception)
        on_final_failure: Callback llamado si falla después de todos los reintentos (exception, all_exceptions)
        max_retries: Override del máximo de reintentos (si None, usa get_max_retries_for_phase)
    
    Returns:
        Resultado de fn() si tiene éxito
    
    Raises:
        La última excepción si todos los reintentos fallan
    """
    if max_retries is None:
        max_retries = get_max_retries_for_phase(phase, error_code, context)
    
    all_exceptions: List[Exception] = []
    last_exception: Optional[Exception] = None
    
    for attempt in range(max_retries + 1):  # +1 porque el primer intento no es retry
        try:
            result = fn()
            # Si llegamos aquí, fue exitoso
            if attempt > 0:
                print(f"[RETRY][{phase}] ✅ Éxito en attempt {attempt + 1}")
            return result
        
        except Exception as e:
            last_exception = e
            all_exceptions.append(e)
            
            # Si es el último intento, no retry
            if attempt >= max_retries:
                print(f"[RETRY][{phase}] ❌ Falló después de {attempt + 1} intentos")
                if on_final_failure:
                    on_final_failure(e, all_exceptions)
                raise e
            
            # Calcular backoff
            backoff_ms = calculate_backoff(attempt + 1)
            backoff_ms = add_jitter(backoff_ms)
            
            print(f"[RETRY][{phase}] ⚠️ Attempt {attempt + 1} falló: {type(e).__name__}: {str(e)[:100]}")
            print(f"[RETRY][{phase}] 🔄 Retry en {backoff_ms}ms (attempt {attempt + 2}/{max_retries + 1})")
            
            if on_retry:
                on_retry(attempt + 1, e)
            
            # Esperar antes del retry
            time.sleep(backoff_ms / 1000.0)
    
    # No debería llegar aquí, pero por si acaso
    if last_exception:
        if on_final_failure:
            on_final_failure(last_exception, all_exceptions)
        raise last_exception
    
    raise RuntimeError(f"retry_with_policy: No se pudo ejecutar {phase} después de {max_retries + 1} intentos")


async def retry_with_policy_async(
    fn: Callable[[], Any],
    phase: str,
    error_code: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,  # SPRINT C2.16.1: Contexto para decisión de retry
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    on_final_failure: Optional[Callable[[Exception, List[Exception]], None]] = None,
    max_retries: Optional[int] = None,
) -> Any:
    """
    Versión async de retry_with_policy.
    
    Args:
        fn: Función async a ejecutar (sin parámetros)
        phase: Fase donde se ejecuta
        error_code: Código de error conocido (si ya se clasificó)
        on_retry: Callback llamado en cada retry (attempt, exception)
        on_final_failure: Callback llamado si falla después de todos los reintentos (exception, all_exceptions)
        max_retries: Override del máximo de reintentos (si None, usa get_max_retries_for_phase)
    
    Returns:
        Resultado de fn() si tiene éxito
    
    Raises:
        La última excepción si todos los reintentos fallan
    """
    import asyncio
    
    if max_retries is None:
        max_retries = get_max_retries_for_phase(phase, error_code, context)
    
    all_exceptions: List[Exception] = []
    last_exception: Optional[Exception] = None
    
    for attempt in range(max_retries + 1):  # +1 porque el primer intento no es retry
        try:
            result = await fn()
            # Si llegamos aquí, fue exitoso
            if attempt > 0:
                print(f"[RETRY][{phase}] ✅ Éxito en attempt {attempt + 1}")
            return result
        
        except Exception as e:
            last_exception = e
            all_exceptions.append(e)
            
            # Si es el último intento, no retry
            if attempt >= max_retries:
                print(f"[RETRY][{phase}] ❌ Falló después de {attempt + 1} intentos")
                if on_final_failure:
                    on_final_failure(e, all_exceptions)
                raise e
            
            # Calcular backoff
            backoff_ms = calculate_backoff(attempt + 1)
            backoff_ms = add_jitter(backoff_ms)
            
            print(f"[RETRY][{phase}] ⚠️ Attempt {attempt + 1} falló: {type(e).__name__}: {str(e)[:100]}")
            print(f"[RETRY][{phase}] 🔄 Retry en {backoff_ms}ms (attempt {attempt + 2}/{max_retries + 1})")
            
            if on_retry:
                on_retry(attempt + 1, e)
            
            # Esperar antes del retry (async)
            await asyncio.sleep(backoff_ms / 1000.0)
    
    # No debería llegar aquí, pero por si acaso
    if last_exception:
        if on_final_failure:
            on_final_failure(last_exception, all_exceptions)
        raise last_exception
    
    raise RuntimeError(f"retry_with_policy_async: No se pudo ejecutar {phase} después de {max_retries + 1} intentos")
