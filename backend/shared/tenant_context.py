"""
SPRINT C2.22A: Contexto de tenant para multi-tenant plumbing.

Extrae tenant_id desde headers, query params o default.
"""
from __future__ import annotations

import re
from typing import Literal
from dataclasses import dataclass
from fastapi import Request


@dataclass
class TenantContext:
    """
    Contexto de tenant extraído de la request.
    
    Attributes:
        tenant_id: ID del tenant (sanitizado)
        source: Origen del tenant_id ("header", "query", "default")
    """
    tenant_id: str
    source: Literal["header", "query", "default"]


def sanitize_tenant_id(tenant_id: str) -> str:
    """
    Sanitiza tenant_id a caracteres seguros: [a-zA-Z0-9_-]
    
    Reemplaza cualquier carácter no permitido por "_".
    
    Args:
        tenant_id: ID del tenant a sanitizar
    
    Returns:
        tenant_id sanitizado
    """
    # Permitir solo letras, números, guiones y guiones bajos
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', tenant_id)
    # Eliminar guiones/underscores múltiples consecutivos
    sanitized = re.sub(r'[_-]+', '_', sanitized)
    # Eliminar guiones/underscores al inicio y final
    sanitized = sanitized.strip('_-')
    # Si queda vacío, usar "default"
    if not sanitized:
        return "default"
    return sanitized


def compute_tenant_from_coordination_context(
    own_company_key: str | None,
    platform_key: str | None,
    coordinated_company_key: str | None
) -> str:
    """
    SPRINT C2.26: Calcula tenant_id interno desde contexto humano de coordinación.
    
    Regla determinista:
    - Si faltan los 3 valores => "default"
    - Si están los 3: normalize(own) + "__" + normalize(platform) + "__" + normalize(coordinated)
    
    Args:
        own_company_key: Clave de empresa propia
        platform_key: Clave de plataforma
        coordinated_company_key: Clave de empresa coordinada
    
    Returns:
        tenant_id sanitizado
    """
    if not own_company_key or not platform_key or not coordinated_company_key:
        return "default"
    
    normalized_own = sanitize_tenant_id(own_company_key)
    normalized_platform = sanitize_tenant_id(platform_key)
    normalized_coordinated = sanitize_tenant_id(coordinated_company_key)
    
    if not normalized_own or not normalized_platform or not normalized_coordinated:
        return "default"
    
    return f"{normalized_own}__{normalized_platform}__{normalized_coordinated}"


def get_tenant_from_request(request: Request | None) -> TenantContext:
    """
    Extrae tenant_id desde la request.
    
    Orden de prioridad:
    1. Headers humanos de coordinación (SPRINT C2.26):
       - X-Coordination-Own-Company
       - X-Coordination-Platform
       - X-Coordination-Coordinated-Company
       => Calcula tenant_id determinista
    2. Header "X-Tenant-ID" (legacy)
    3. Query param "tenant_id" (legacy)
    4. Default "default"
    
    Args:
        request: Request de FastAPI (puede ser None)
    
    Returns:
        TenantContext con tenant_id sanitizado y source
    """
    if request is None:
        return TenantContext(tenant_id="default", source="default")
    
    # 1) SPRINT C2.26: Intentar headers humanos de coordinación
    own_company = request.headers.get("X-Coordination-Own-Company")
    platform = request.headers.get("X-Coordination-Platform")
    coordinated_company = request.headers.get("X-Coordination-Coordinated-Company")
    
    if own_company and platform and coordinated_company:
        tenant_id = compute_tenant_from_coordination_context(
            own_company_key=own_company,
            platform_key=platform,
            coordinated_company_key=coordinated_company
        )
        return TenantContext(tenant_id=tenant_id, source="header")
    
    # 2) Intentar header X-Tenant-ID (legacy)
    tenant_header = request.headers.get("X-Tenant-ID")
    if tenant_header:
        sanitized = sanitize_tenant_id(tenant_header)
        return TenantContext(tenant_id=sanitized, source="header")
    
    # 3) Intentar query param tenant_id (legacy)
    tenant_query = request.query_params.get("tenant_id")
    if tenant_query:
        sanitized = sanitize_tenant_id(tenant_query)
        return TenantContext(tenant_id=sanitized, source="query")
    
    # 4) Default
    return TenantContext(tenant_id="default", source="default")
