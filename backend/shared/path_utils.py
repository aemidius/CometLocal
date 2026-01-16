"""
Utilidades seguras para operaciones con Path.

Evita errores de tipo "WindowsPath / NoneType" cuando se intenta hacer join con None.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union


def safe_path_join(base: Path, part: Union[str, Path, None]) -> Optional[Path]:
    """
    Une un Path base con una parte de forma segura.
    
    Args:
        base: Path base
        part: Parte a unir (str, Path o None)
    
    Returns:
        Path unido o None si part es None o vacío
    """
    if part is None:
        return None
    if isinstance(part, Path):
        return base / part
    s = str(part).strip()
    if not s:
        return None
    return base / s


def as_str(p: Union[Path, str, None]) -> Optional[str]:
    """
    Convierte un Path a string de forma segura.
    
    Args:
        p: Path, str o None
    
    Returns:
        str o None
    """
    if p is None:
        return None
    if isinstance(p, Path):
        return str(p)
    return str(p) if p else None
