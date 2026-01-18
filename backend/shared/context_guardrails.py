"""
SPRINT C2.27: Guardrails de contexto para operaciones WRITE.

Impedir operaciones WRITE si no hay contexto humano válido (own/platform/coordinated),
salvo legacy explícito en entornos controlados (dev/test).
"""
from __future__ import annotations

import os
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
    
    # WRITE sin contexto válido: rechazar
    raise HTTPException(
        status_code=400,
        detail={
            "error": "missing_coordination_context",
            "message": "Selecciona Empresa propia, Plataforma y Empresa coordinada"
        }
    )
