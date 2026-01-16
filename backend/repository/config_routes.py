from __future__ import annotations

from fastapi import APIRouter

from backend.repository.config_store_v1 import ConfigStoreV1
from backend.shared.org_v1 import OrgV1
from backend.shared.people_v1 import PeopleV1
from backend.shared.platforms_v1 import PlatformsV1


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
async def get_people() -> PeopleV1:
    """Obtiene la lista de personas (solo lectura)."""
    store = ConfigStoreV1()
    return store.load_people()


@router.get("/platforms", response_model=PlatformsV1)
async def get_platforms() -> PlatformsV1:
    """Obtiene la lista de plataformas (solo lectura)."""
    store = ConfigStoreV1()
    return store.load_platforms()

