from __future__ import annotations

import os
import logging
from typing import Optional

from fastapi import APIRouter, Query

from backend.repository.config_store_v1 import ConfigStoreV1
from backend.shared.org_v1 import OrgV1
from backend.shared.people_v1 import PeopleV1, PersonV1
from backend.shared.platforms_v1 import PlatformsV1

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/config",
    tags=["config"],
)


@router.get("/org", response_model=OrgV1)
async def get_org() -> OrgV1:
    """Obtiene la configuración de organización (solo lectura)."""
    store = ConfigStoreV1()
    return store.load_org()


@router.get("/people", response_model=PeopleV1)
async def get_people(own_company_key: Optional[str] = Query(None, description="Filtrar por empresa propia")) -> PeopleV1:
    """
    Obtiene la lista de personas (solo lectura).
    
    Args:
        own_company_key: Si se proporciona, filtra personas por empresa propia.
                        Si es None, devuelve todas (legacy mode).
    
    Returns:
        PeopleV1 con personas filtradas (o todas si no se especifica filtro)
    """
    store = ConfigStoreV1()
    people = store.load_people()
    
    # Si no se especifica filtro, devolver todo pero loggear warning en dev
    if own_company_key is None:
        env = os.getenv("ENVIRONMENT", "").lower()
        if env in ("dev", "development"):
            logger.warning(
                "[config/people] Llamada sin own_company_key - devolviendo todas las personas. "
                "Considera filtrar por empresa propia para mejor rendimiento."
            )
        return people
    
    # Filtrar por own_company_key
    filtered_people = [
        p for p in people.people
        if p.own_company_key == own_company_key
    ]
    
    return PeopleV1(people=filtered_people)


def get_people_for_own_company(own_company_key: str, base_dir: Optional[str] = None) -> list[PersonV1]:
    """
    Helper: Obtiene personas filtradas por empresa propia.
    
    Args:
        own_company_key: Clave de empresa propia
        base_dir: Directorio base (opcional, usa DATA_DIR por defecto)
    
    Returns:
        Lista de PersonV1 asociadas a la empresa propia
    """
    if base_dir:
        from pathlib import Path
        store = ConfigStoreV1(base_dir=Path(base_dir))
    else:
        store = ConfigStoreV1()
    
    people = store.load_people()
    return [p for p in people.people if p.own_company_key == own_company_key]


@router.get("/platforms", response_model=PlatformsV1)
async def get_platforms() -> PlatformsV1:
    """Obtiene la lista de plataformas (solo lectura)."""
    store = ConfigStoreV1()
    return store.load_platforms()

