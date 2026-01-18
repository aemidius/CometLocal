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


def get_tenant_from_request(request: Request | None) -> TenantContext:
    """
    Extrae tenant_id desde la request.
    
    Orden de prioridad:
    1. Header "X-Tenant-ID"
    2. Query param "tenant_id"
    3. Default "default"
    
    Args:
        request: Request de FastAPI (puede ser None)
    
    Returns:
        TenantContext con tenant_id sanitizado y source
    """
    if request is None:
        return TenantContext(tenant_id="default", source="default")
    
    # 1) Intentar header X-Tenant-ID
    tenant_header = request.headers.get("X-Tenant-ID")
    if tenant_header:
        sanitized = sanitize_tenant_id(tenant_header)
        return TenantContext(tenant_id=sanitized, source="header")
    
    # 2) Intentar query param tenant_id
    tenant_query = request.query_params.get("tenant_id")
    if tenant_query:
        sanitized = sanitize_tenant_id(tenant_query)
        return TenantContext(tenant_id=sanitized, source="query")
    
    # 3) Default
    return TenantContext(tenant_id="default", source="default")
