"""
Clasificador de errores para hardening y resiliencia.

SPRINT C2.16: Clasifica errores en transitorios vs definitivos,
y asigna error_code estable para retry policy y métricas.
"""
from __future__ import annotations

from typing import Dict, Any, Optional, List
from enum import Enum
import traceback
import re


class ErrorCode(str, Enum):
    """Códigos de error estables para taxonomía."""
    # Timeouts
    TIMEOUT_LOGIN = "timeout_login"
    TIMEOUT_NAVIGATION = "timeout_navigation"
    TIMEOUT_GRID_LOAD = "timeout_grid_load"
    TIMEOUT_UPLOAD = "timeout_upload"
    TIMEOUT_VERIFICATION = "timeout_verification"
    
    # Grid/Scraping
    GRID_PARSE_MISMATCH = "grid_parse_mismatch"
    BUSCAR_NOT_CLICKABLE = "buscar_not_clickable"
    OVERLAY_BLOCKING = "overlay_blocking"
    PAGINATION_FAILED = "pagination_failed"
    
    # Upload
    ITEM_NOT_FOUND_BEFORE_UPLOAD = "item_not_found_before_upload"
    UPLOAD_FAILED = "upload_failed"
    UPLOAD_CLICK_INTERCEPTED = "upload_click_intercepted"
    UPLOAD_CONFIRMATION_FAILED = "upload_confirmation_failed"
    
    # Verification
    VERIFICATION_FAILED = "verification_failed"
    ITEM_STILL_PRESENT_AFTER_UPLOAD = "item_still_present_after_upload"
    
    # Network/Portal
    NETWORK_TRANSIENT = "network_transient"
    PORTAL_TRANSIENT = "portal_transient"
    PORTAL_ERROR = "portal_error"
    
    # Unexpected
    UNEXPECTED_EXCEPTION = "unexpected_exception"
    POLICY_REJECTED = "policy_rejected"
    MISSING_CREDENTIALS = "missing_credentials"
    MISSING_STORAGE_STATE = "missing_storage_state"


def classify_exception(
    exc: Exception,
    phase: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Clasifica una excepción y determina si es transitoria.
    
    Args:
        exc: Excepción capturada
        phase: Fase donde ocurrió ("login", "navigation", "grid_load", "upload", "verification")
        context: Contexto adicional (selector intentado, URL, etc.)
    
    Returns:
        {
            "error_code": ErrorCode,
            "is_transient": bool,
            "retry_after_ms": Optional[int],
            "details": Dict[str, Any],
            "message": str,
        }
    """
    context = context or {}
    exc_type = type(exc).__name__
    exc_message = str(exc)
    exc_traceback = traceback.format_exc()
    
    # Patrones para detectar tipos de error
    is_timeout = (
        "timeout" in exc_message.lower() or
        "TimeoutError" in exc_type or
        "PhaseTimeoutError" in exc_type or
        "waiting for" in exc_message.lower() or
        "exceeded" in exc_message.lower()
    )
    
    is_network = (
        "network" in exc_message.lower() or
        "connection" in exc_message.lower() or
        "ECONNREFUSED" in exc_message or
        "ETIMEDOUT" in exc_message or
        "NetworkError" in exc_type
    )
    
    is_navigation = (
        "navigation" in exc_message.lower() or
        "NavigationError" in exc_type or
        "page.goto" in exc_traceback or
        "frame.goto" in exc_traceback
    )
    
    is_click_intercepted = (
        "click" in exc_message.lower() and
        ("intercepted" in exc_message.lower() or "overlay" in exc_message.lower() or "blocked" in exc_message.lower())
    )
    
    is_overlay = (
        "overlay" in exc_message.lower() or
        "blocking" in exc_message.lower() or
        "modal" in exc_message.lower() or
        "dialog" in exc_message.lower()
    )
    
    # Clasificación por fase
    if phase == "login":
        if is_timeout:
            return {
                "error_code": ErrorCode.TIMEOUT_LOGIN,
                "is_transient": True,
                "retry_after_ms": 2000,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                },
                "message": f"Login timeout: {exc_message}",
            }
        elif is_network:
            return {
                "error_code": ErrorCode.NETWORK_TRANSIENT,
                "is_transient": True,
                "retry_after_ms": 3000,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                },
                "message": f"Network error during login: {exc_message}",
            }
        else:
            return {
                "error_code": ErrorCode.UNEXPECTED_EXCEPTION,
                "is_transient": False,
                "retry_after_ms": None,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "traceback": exc_traceback,
                    "context": context,
                },
                "message": f"Unexpected error during login: {exc_message}",
            }
    
    elif phase == "navigation":
        if is_timeout:
            return {
                "error_code": ErrorCode.TIMEOUT_NAVIGATION,
                "is_transient": True,
                "retry_after_ms": 2000,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                },
                "message": f"Navigation timeout: {exc_message}",
            }
        elif is_network:
            return {
                "error_code": ErrorCode.NETWORK_TRANSIENT,
                "is_transient": True,
                "retry_after_ms": 3000,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                },
                "message": f"Network error during navigation: {exc_message}",
            }
        else:
            return {
                "error_code": ErrorCode.UNEXPECTED_EXCEPTION,
                "is_transient": False,
                "retry_after_ms": None,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "traceback": exc_traceback,
                    "context": context,
                },
                "message": f"Unexpected error during navigation: {exc_message}",
            }
    
    elif phase == "grid_load":
        if is_timeout:
            return {
                "error_code": ErrorCode.TIMEOUT_GRID_LOAD,
                "is_transient": True,
                "retry_after_ms": 2000,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                },
                "message": f"Grid load timeout: {exc_message}",
            }
        elif is_overlay:
            return {
                "error_code": ErrorCode.OVERLAY_BLOCKING,
                "is_transient": True,
                "retry_after_ms": 1500,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                },
                "message": f"Overlay blocking grid: {exc_message}",
            }
        elif "buscar" in exc_message.lower() and "click" in exc_message.lower():
            return {
                "error_code": ErrorCode.BUSCAR_NOT_CLICKABLE,
                "is_transient": True,
                "retry_after_ms": 2000,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                },
                "message": f"Buscar button not clickable: {exc_message}",
            }
        elif is_network:
            return {
                "error_code": ErrorCode.NETWORK_TRANSIENT,
                "is_transient": True,
                "retry_after_ms": 3000,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                },
                "message": f"Network error during grid load: {exc_message}",
            }
        else:
            return {
                "error_code": ErrorCode.UNEXPECTED_EXCEPTION,
                "is_transient": False,
                "retry_after_ms": None,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "traceback": exc_traceback,
                    "context": context,
                },
                "message": f"Unexpected error during grid load: {exc_message}",
            }
    
    elif phase == "upload":
        if is_timeout:
            # SPRINT C2.16.1: timeout_upload puede ser reintentable SOLO si upload_attempted=false
            upload_attempted = context.get("upload_attempted", False) if context else False
            is_transient = not upload_attempted  # Solo transitorio si NO se intentó upload aún
            
            return {
                "error_code": ErrorCode.TIMEOUT_UPLOAD,
                "is_transient": is_transient,
                "retry_after_ms": 2000 if is_transient else None,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                    "upload_attempted": upload_attempted,  # SPRINT C2.16.1: Flag para decisión de retry
                },
                "message": f"Upload timeout: {exc_message}",
            }
        elif is_click_intercepted:
            return {
                "error_code": ErrorCode.UPLOAD_CLICK_INTERCEPTED,
                "is_transient": True,  # Click interceptado puede ser overlay temporal
                "retry_after_ms": 1500,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                },
                "message": f"Upload click intercepted: {exc_message}",
            }
        elif "item_not_found" in exc_message.lower() or "item_not_found_before_upload" in exc_message.lower():
            return {
                "error_code": ErrorCode.ITEM_NOT_FOUND_BEFORE_UPLOAD,
                "is_transient": True,  # SPRINT C2.16.1: Puede ser que el item se movió de página, 1 retry con refresh
                "retry_after_ms": 2000,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                    "retry_action": "refresh_listing_and_go_to_first_page",  # SPRINT C2.16.1: Acción específica para retry
                },
                "message": f"Item not found before upload: {exc_message}",
            }
        elif is_network:
            return {
                "error_code": ErrorCode.NETWORK_TRANSIENT,
                "is_transient": False,  # Network error durante upload es crítico
                "retry_after_ms": None,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                },
                "message": f"Network error during upload: {exc_message}",
            }
        else:
            return {
                "error_code": ErrorCode.UPLOAD_FAILED,
                "is_transient": False,
                "retry_after_ms": None,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "traceback": exc_traceback,
                    "context": context,
                },
                "message": f"Upload failed: {exc_message}",
            }
    
    elif phase == "verification":
        if is_timeout:
            return {
                "error_code": ErrorCode.TIMEOUT_VERIFICATION,
                "is_transient": True,  # Verification timeout puede ser que el portal tarda en actualizar
                "retry_after_ms": 3000,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                },
                "message": f"Verification timeout: {exc_message}",
            }
        elif "item_still_present" in exc_message.lower():
            return {
                "error_code": ErrorCode.ITEM_STILL_PRESENT_AFTER_UPLOAD,
                "is_transient": False,  # Si el item sigue presente, no es transitorio
                "retry_after_ms": None,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                },
                "message": f"Item still present after upload: {exc_message}",
            }
        else:
            return {
                "error_code": ErrorCode.VERIFICATION_FAILED,
                "is_transient": True,  # Verification failed puede ser refresh tardío, 1 retry
                "retry_after_ms": 3000,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                },
                "message": f"Verification failed: {exc_message}",
            }
    
    else:
        # Fase desconocida o genérica
        if is_timeout:
            return {
                "error_code": ErrorCode.UNEXPECTED_EXCEPTION,
                "is_transient": True,
                "retry_after_ms": 2000,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                },
                "message": f"Timeout in {phase}: {exc_message}",
            }
        elif is_network:
            return {
                "error_code": ErrorCode.NETWORK_TRANSIENT,
                "is_transient": True,
                "retry_after_ms": 3000,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "context": context,
                },
                "message": f"Network error in {phase}: {exc_message}",
            }
        else:
            return {
                "error_code": ErrorCode.UNEXPECTED_EXCEPTION,
                "is_transient": False,
                "retry_after_ms": None,
                "details": {
                    "phase": phase,
                    "exception_type": exc_type,
                    "message": exc_message,
                    "traceback": exc_traceback,
                    "context": context,
                },
                "message": f"Unexpected error in {phase}: {exc_message}",
            }


def classify_error_code(
    error_code: str,
    phase: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Clasifica un error_code conocido (no excepción).
    
    Útil cuando ya tenemos un error_code del código existente.
    """
    context = context or {}
    
    # Mapeo de error_codes a clasificación
    error_classifications = {
        ErrorCode.TIMEOUT_LOGIN: {"is_transient": True, "retry_after_ms": 2000},
        ErrorCode.TIMEOUT_NAVIGATION: {"is_transient": True, "retry_after_ms": 2000},
        ErrorCode.TIMEOUT_GRID_LOAD: {"is_transient": True, "retry_after_ms": 2000},
        ErrorCode.TIMEOUT_UPLOAD: {"is_transient": None, "retry_after_ms": None},  # SPRINT C2.16.1: Depende de upload_attempted
        ErrorCode.TIMEOUT_VERIFICATION: {"is_transient": True, "retry_after_ms": 3000},
        
        ErrorCode.GRID_PARSE_MISMATCH: {"is_transient": False, "retry_after_ms": None},
        ErrorCode.BUSCAR_NOT_CLICKABLE: {"is_transient": True, "retry_after_ms": 2000},
        ErrorCode.OVERLAY_BLOCKING: {"is_transient": True, "retry_after_ms": 1500},
        ErrorCode.PAGINATION_FAILED: {"is_transient": True, "retry_after_ms": 2000},
        
        ErrorCode.ITEM_NOT_FOUND_BEFORE_UPLOAD: {"is_transient": True, "retry_after_ms": 2000},  # SPRINT C2.16.1: Solo 1 retry con refresh
        ErrorCode.UPLOAD_FAILED: {"is_transient": False, "retry_after_ms": None},
        ErrorCode.UPLOAD_CLICK_INTERCEPTED: {"is_transient": True, "retry_after_ms": 1500},
        ErrorCode.UPLOAD_CONFIRMATION_FAILED: {"is_transient": False, "retry_after_ms": None},
        
        ErrorCode.VERIFICATION_FAILED: {"is_transient": True, "retry_after_ms": 3000},
        ErrorCode.ITEM_STILL_PRESENT_AFTER_UPLOAD: {"is_transient": False, "retry_after_ms": None},
        
        ErrorCode.NETWORK_TRANSIENT: {"is_transient": True, "retry_after_ms": 3000},
        ErrorCode.PORTAL_TRANSIENT: {"is_transient": True, "retry_after_ms": 3000},
        ErrorCode.PORTAL_ERROR: {"is_transient": False, "retry_after_ms": None},
        
        ErrorCode.UNEXPECTED_EXCEPTION: {"is_transient": False, "retry_after_ms": None},
        ErrorCode.POLICY_REJECTED: {"is_transient": False, "retry_after_ms": None},
        ErrorCode.MISSING_CREDENTIALS: {"is_transient": False, "retry_after_ms": None},
        ErrorCode.MISSING_STORAGE_STATE: {"is_transient": False, "retry_after_ms": None},
    }
    
    classification = error_classifications.get(error_code, {
        "is_transient": False,
        "retry_after_ms": None,
    })
    
    # SPRINT C2.16.1: timeout_upload depende de upload_attempted
    is_transient = classification["is_transient"]
    if error_code == ErrorCode.TIMEOUT_UPLOAD:
        upload_attempted = context.get("upload_attempted", False) if context else False
        is_transient = not upload_attempted  # Solo transitorio si NO se intentó upload aún
    
    return {
        "error_code": error_code,
        "is_transient": is_transient,
        "retry_after_ms": classification.get("retry_after_ms") if is_transient else None,
        "details": {
            "phase": phase,
            "context": context,
        },
        "message": f"Error {error_code} in {phase}",
    }
