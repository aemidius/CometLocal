"""
SPRINT C2.27: Guardrails de contexto para operaciones WRITE.

Impedir operaciones WRITE si no hay contexto humano válido (own/platform/coordinated),
salvo legacy explícito en entornos controlados (dev/test).

SPRINT C2.28: Añadidos logs estructurados para señales operativas.
"""
from __future__ import annotations

import os
import json
from datetime import datetime
from fastapi import Request, HTTPException
from backend.shared.tenant_context import get_tenant_from_request


def is_write_request(request: Request) -> bool:
    """
    Detecta si una request es de tipo WRITE (POST, PUT, DELETE).
    
    Args:
        request: Request de FastAPI
    
    Returns:
        True si es WRITE, False si es READ (GET, HEAD, OPTIONS)
    """
    method = request.method.upper()
    return method in ("POST", "PUT", "DELETE", "PATCH")


def has_human_coordination_context(request: Request) -> bool:
    """
    Verifica si la request tiene contexto humano completo de coordinación.
    
    Args:
        request: Request de FastAPI
    
    Returns:
        True si tiene los 3 headers humanos, False en caso contrario
    """
    own_company = request.headers.get("X-Coordination-Own-Company")
    platform = request.headers.get("X-Coordination-Platform")
    coordinated_company = request.headers.get("X-Coordination-Coordinated-Company")
    
    return bool(own_company and platform and coordinated_company)


def has_legacy_tenant_header(request: Request) -> bool:
    """
    Verifica si la request tiene header legacy X-Tenant-ID.
    
    Args:
        request: Request de FastAPI
    
    Returns:
        True si tiene X-Tenant-ID, False en caso contrario
    """
    return bool(request.headers.get("X-Tenant-ID"))


def is_dev_or_test_environment() -> bool:
    """
    Verifica si estamos en entorno dev o test.
    
    Returns:
        True si ENVIRONMENT está en ("dev", "test"), False en caso contrario
    """
    env = os.getenv("ENVIRONMENT", "").lower()
    return env in ("dev", "test")


def validate_write_request_context(request: Request) -> None:
    """
    SPRINT C2.27: Valida que las operaciones WRITE tengan contexto válido.
    
    Reglas:
    - Si es WRITE y NO tiene contexto humano completo:
      - Permitir SOLO si:
        - se está usando legacy explícito (X-Tenant-ID presente) Y
        - ENVIRONMENT in ("dev","test")
      - En caso contrario:
        - lanzar HTTPException 400 con payload estable
    
    HOTFIX: Rutas /config/* requieren contexto humano (no son legacy).
    
    Args:
        request: Request de FastAPI
    
    Raises:
        HTTPException: 400 si es WRITE sin contexto válido
    """
    # Solo validar operaciones WRITE
    if not is_write_request(request):
        return
    
    # Si tiene contexto humano completo, permitir
    if has_human_coordination_context(request):
        return
    
    # Si no tiene contexto humano, verificar legacy + entorno
    if has_legacy_tenant_header(request) and is_dev_or_test_environment():
        # Legacy explícito en dev/test: permitir
        return
    
    # SPRINT C2.28: Log estructurado antes de rechazar
    _log_guardrail_block(request)
    
    # HOTFIX: Asegurar que HTTPException se lanza correctamente con status_code 400
    # WRITE sin contexto válido: rechazar
    raise HTTPException(
        status_code=400,
        detail={
            "error": "missing_coordination_context",
            "message": "Selecciona Empresa propia, Plataforma y Empresa coordinada"
        }
    )


def _log_guardrail_block(request: Request) -> None:
    """
    SPRINT C2.28: Log estructurado cuando se bloquea una operación WRITE por falta de contexto.
    
    Log JSON con:
    - event: "context_guardrail_block"
    - reason: motivo del bloqueo
    - route: ruta de la request
    - headers humanos presentes (keys, no valores sensibles)
    - timestamp
    
    NO incluye:
    - palabra "tenant"
    - rutas internas sensibles
    """
    # Detectar qué headers humanos están presentes (solo keys)
    human_headers_present = []
    if request.headers.get("X-Coordination-Own-Company"):
        human_headers_present.append("X-Coordination-Own-Company")
    if request.headers.get("X-Coordination-Platform"):
        human_headers_present.append("X-Coordination-Platform")
    if request.headers.get("X-Coordination-Coordinated-Company"):
        human_headers_present.append("X-Coordination-Coordinated-Company")
    
    # Determinar razón del bloqueo
    has_legacy = bool(request.headers.get("X-Tenant-ID"))
    is_dev_test = is_dev_or_test_environment()
    
    if has_legacy and not is_dev_test:
        reason = "legacy_header_in_prod"
    elif not human_headers_present:
        reason = "no_human_context_headers"
    elif len(human_headers_present) < 3:
        reason = "incomplete_human_context"
    else:
        reason = "unknown"
    
    # Construir log estructurado
    log_data = {
        "event": "context_guardrail_block",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "reason": reason,
        "route": str(request.url.path),
        "method": request.method,
        "human_headers_present": human_headers_present,
        "has_legacy_header": has_legacy,
        "environment": os.getenv("ENVIRONMENT", "unknown")
    }
    
    # Imprimir como JSON estructurado a stdout
    print(json.dumps(log_data, ensure_ascii=False))
