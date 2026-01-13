"""
Rutas para configuración del repositorio de documentos.
Permite configurar la ruta raíz donde se almacenan los documentos.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from backend.config import DATA_DIR

router = APIRouter(
    prefix="/api/repository",
    tags=["repository-settings"],
)


def get_repository_data_dir() -> Path:
    """
    SPRINT C2.10.2: Obtiene el directorio base de datos del repositorio.
    
    Si REPOSITORY_DATA_DIR está definido, lo usa (relativo o absoluto).
    Si no, usa el comportamiento por defecto (DATA_DIR).
    
    Returns:
        Path resuelto y normalizado del directorio base.
    """
    env_dir = os.getenv("REPOSITORY_DATA_DIR")
    if env_dir:
        # Resolver path (puede ser relativo o absoluto)
        base_path = Path(env_dir)
        if not base_path.is_absolute():
            # Si es relativo, resolver desde el repo root
            _REPO_ROOT = Path(__file__).resolve().parent.parent.parent
            base_path = (_REPO_ROOT / base_path).resolve()
        else:
            base_path = base_path.resolve()
        # Asegurar que existe
        base_path.mkdir(parents=True, exist_ok=True)
        return base_path
    else:
        # Comportamiento por defecto: usar DATA_DIR
        return Path(DATA_DIR)


class RepositorySettingsV1(BaseModel):
    """Configuración del repositorio de documentos."""
    repository_root_dir: str = Field(
        description="Ruta absoluta en el servidor donde se guardan los documentos"
    )

    @field_validator('repository_root_dir')
    @classmethod
    def validate_repository_root_dir(cls, v: str) -> str:
        """Valida que la ruta sea absoluta y no contenga rutas relativas peligrosas."""
        if not v or not v.strip():
            raise ValueError("La ruta no puede estar vacía")
        
        # Normalizar separadores
        v = v.strip().replace('/', os.sep)
        
        # Convertir a Path para validar
        try:
            path = Path(v)
        except Exception as e:
            raise ValueError(f"Ruta inválida: {str(e)}")
        
        # Debe ser absoluta
        if not path.is_absolute():
            raise ValueError("La ruta debe ser absoluta (ej: D:\\Proyectos\\data o /home/user/data)")
        
        # No permitir rutas relativas peligrosas
        if '..' in str(path):
            raise ValueError("No se permiten rutas relativas con '..'")
        
        return str(path.resolve())


def get_settings_path() -> Path:
    """
    Obtiene la ruta del archivo de configuración.
    SPRINT C2.10.2: Usa get_repository_data_dir() para respetar REPOSITORY_DATA_DIR.
    """
    base_dir = get_repository_data_dir()
    return base_dir / "repository" / "settings.json"


def get_default_repository_root() -> str:
    """
    Obtiene la ruta por defecto del repositorio.
    SPRINT C2.10.2: Usa get_repository_data_dir() para respetar REPOSITORY_DATA_DIR.
    """
    base_dir = get_repository_data_dir()
    return str((base_dir / "repository").resolve())


def load_settings() -> RepositorySettingsV1:
    """Carga la configuración desde el archivo JSON."""
    settings_path = get_settings_path()
    
    if not settings_path.exists():
        # Crear configuración por defecto
        default_root = get_default_repository_root()
        settings = RepositorySettingsV1(repository_root_dir=default_root)
        save_settings(settings)
        return settings
    
    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return RepositorySettingsV1(**data)
    except Exception as e:
        # Si hay error, usar default
        default_root = get_default_repository_root()
        return RepositorySettingsV1(repository_root_dir=default_root)


def save_settings(settings: RepositorySettingsV1) -> None:
    """Guarda la configuración en el archivo JSON."""
    settings_path = get_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(settings_path, 'w', encoding='utf-8') as f:
        json.dump(settings.model_dump(), f, indent=2, ensure_ascii=False)


def validate_and_ensure_directory(path_str: str, create_if_missing: bool = True) -> Path:
    """
    Valida que el directorio sea escribible y lo crea si no existe.
    
    Raises:
        HTTPException: Si la ruta no es válida o no es escribible
    """
    try:
        path = Path(path_str)
        
        # Crear directorio si no existe
        if not path.exists():
            if create_if_missing:
                try:
                    path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"No se pudo crear el directorio: {str(e)}"
                    )
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"El directorio no existe: {path_str}"
                )
        
        # Verificar que es un directorio
        if not path.is_dir():
            raise HTTPException(
                status_code=400,
                detail=f"La ruta existe pero no es un directorio: {path_str}"
            )
        
        # Verificar permisos de escritura (crear archivo temporal)
        try:
            test_file = path / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"El directorio no es escribible: {str(e)}"
            )
        
        return path.resolve()
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error al validar la ruta: {str(e)}"
        )


@router.get("/settings", response_model=RepositorySettingsV1)
async def get_settings() -> RepositorySettingsV1:
    """Obtiene la configuración actual del repositorio."""
    return load_settings()


@router.put("/settings", response_model=RepositorySettingsV1)
async def update_settings(
    settings: RepositorySettingsV1,
    dry_run: Optional[bool] = Query(None, description="Si es True, solo valida sin guardar")
) -> RepositorySettingsV1:
    """
    Actualiza la configuración del repositorio.
    
    - dry_run: Si es True, solo valida sin guardar
    """
    # Validar y asegurar que el directorio existe y es escribible
    validated_path = validate_and_ensure_directory(
        settings.repository_root_dir,
        create_if_missing=True
    )
    
    # Actualizar con la ruta resuelta
    settings.repository_root_dir = str(validated_path)
    
    if not dry_run:
        # Guardar configuración
        save_settings(settings)
    
    return settings


@router.get("/debug/data_dir")
async def get_debug_data_dir() -> dict:
    """
    SPRINT C2.10.2: Endpoint DEV-ONLY para verificar el directorio de datos usado.
    
    Solo disponible si E2E_SEED_ENABLED=1 o ENVIRONMENT=dev.
    """
    # Verificar que estamos en modo dev/E2E
    e2e_enabled = os.getenv("E2E_SEED_ENABLED") == "1"
    env_dev = os.getenv("ENVIRONMENT") in ("dev", "development", "local")
    
    if not (e2e_enabled or env_dev):
        raise HTTPException(
            status_code=403,
            detail="Este endpoint solo está disponible en modo dev/E2E"
        )
    
    base_dir = get_repository_data_dir()
    repository_root = get_default_repository_root()
    
    return {
        "data_dir": str(base_dir.resolve()),
        "repository_root": repository_root,
        "repository_data_dir_env": os.getenv("REPOSITORY_DATA_DIR"),
        "is_e2e": "repository_e2e" in str(base_dir) or "repository_e2e" in repository_root
    }

