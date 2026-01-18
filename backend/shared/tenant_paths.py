"""
SPRINT C2.22A: Funciones para resolver paths multi-tenant con fallback legacy.

Estructura:
- data/tenants/<tenant_id>/runs/
- data/tenants/<tenant_id>/learning/
- data/tenants/<tenant_id>/presets/
- data/tenants/<tenant_id>/exports/
- data/tenants/<tenant_id>/repository/

Fallback legacy:
- Lecturas buscan primero en tenant path, luego en legacy (data/runs/, etc.)
- Escrituras siempre van a tenant path
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal


def tenants_root(base_dir: Path) -> Path:
    """
    Retorna el directorio raíz de tenants: data/tenants/
    
    Args:
        base_dir: Directorio base (ej: DATA_DIR)
    
    Returns:
        Path a data/tenants/
    """
    return base_dir / "tenants"


def tenant_root(base_dir: Path, tenant_id: str) -> Path:
    """
    Retorna el directorio raíz de un tenant: data/tenants/<tenant_id>/
    
    Args:
        base_dir: Directorio base (ej: DATA_DIR)
        tenant_id: ID del tenant
    
    Returns:
        Path a data/tenants/<tenant_id>/
    """
    return tenants_root(base_dir) / tenant_id


def tenant_runs_root(base_dir: Path, tenant_id: str) -> Path:
    """
    Retorna el directorio de runs de un tenant: data/tenants/<tenant_id>/runs/
    
    Args:
        base_dir: Directorio base (ej: DATA_DIR)
        tenant_id: ID del tenant
    
    Returns:
        Path a data/tenants/<tenant_id>/runs/
    """
    return tenant_root(base_dir, tenant_id) / "runs"


def tenant_learning_root(base_dir: Path, tenant_id: str) -> Path:
    """
    Retorna el directorio de learning de un tenant: data/tenants/<tenant_id>/learning/
    
    Args:
        base_dir: Directorio base (ej: DATA_DIR)
        tenant_id: ID del tenant
    
    Returns:
        Path a data/tenants/<tenant_id>/learning/
    """
    return tenant_root(base_dir, tenant_id) / "learning"


def tenant_presets_root(base_dir: Path, tenant_id: str) -> Path:
    """
    Retorna el directorio de presets de un tenant: data/tenants/<tenant_id>/presets/
    
    Args:
        base_dir: Directorio base (ej: DATA_DIR)
        tenant_id: ID del tenant
    
    Returns:
        Path a data/tenants/<tenant_id>/presets/
    """
    return tenant_root(base_dir, tenant_id) / "presets"


def tenant_exports_root(base_dir: Path, tenant_id: str) -> Path:
    """
    Retorna el directorio de exports de un tenant: data/tenants/<tenant_id>/exports/
    
    Args:
        base_dir: Directorio base (ej: DATA_DIR)
        tenant_id: ID del tenant
    
    Returns:
        Path a data/tenants/<tenant_id>/exports/
    """
    return tenant_root(base_dir, tenant_id) / "exports"


def tenant_repository_root(base_dir: Path, tenant_id: str) -> Path:
    """
    Retorna el directorio de repository de un tenant: data/tenants/<tenant_id>/repository/
    
    Args:
        base_dir: Directorio base (ej: DATA_DIR)
        tenant_id: ID del tenant
    
    Returns:
        Path a data/tenants/<tenant_id>/repository/
    """
    return tenant_root(base_dir, tenant_id) / "repository"


def resolve_read_path(tenant_path: Path, legacy_path: Path) -> Path:
    """
    Resuelve path de lectura con fallback legacy.
    
    Si tenant_path existe (directorio o archivo), lo retorna.
    Si no, retorna legacy_path (fallback).
    
    Args:
        tenant_path: Path en estructura tenant (data/tenants/<tenant>/...)
        legacy_path: Path legacy (data/...)
    
    Returns:
        tenant_path si existe, si no legacy_path
    """
    # Si el path es un archivo, verificar si existe
    if tenant_path.exists():
        return tenant_path
    
    # Si el path es un directorio, verificar si existe
    if tenant_path.is_dir() or tenant_path.parent.exists():
        # Si el directorio padre existe, usar tenant_path
        return tenant_path
    
    # Fallback a legacy
    return legacy_path


def ensure_write_dir(path: Path) -> Path:
    """
    Asegura que el directorio existe (mkdir parents=True, exist_ok=True).
    
    Args:
        path: Path al directorio a crear
    
    Returns:
        Path (el mismo, para chaining)
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_runs_root(base_dir: Path, tenant_id: str, mode: Literal["read", "write"]) -> Path:
    """
    Helper central para obtener runs root con fallback legacy.
    
    Args:
        base_dir: Directorio base (ej: DATA_DIR)
        tenant_id: ID del tenant
        mode: "read" (con fallback legacy) o "write" (solo tenant)
    
    Returns:
        Path a runs root según el modo
    """
    tenant_runs = tenant_runs_root(base_dir, tenant_id)
    legacy_runs = base_dir / "runs"
    
    if mode == "write":
        # Escritura: siempre en tenant path
        return ensure_write_dir(tenant_runs)
    else:
        # Lectura: tenant con fallback legacy
        return resolve_read_path(tenant_runs, legacy_runs)
