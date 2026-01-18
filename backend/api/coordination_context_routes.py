"""
SPRINT C2.26: Endpoint para opciones del contexto de coordinación humano.

Proporciona las opciones disponibles para los 3 selectores:
- Empresa propia (own_companies)
- Plataforma (platforms)
- Empresa coordinada (coordinated_companies_by_platform)
"""
from __future__ import annotations

from typing import Dict, List
from fastapi import APIRouter
from pydantic import BaseModel

from backend.repository.config_store_v1 import ConfigStoreV1
from backend.config import DATA_DIR


router = APIRouter(prefix="/api/coordination", tags=["coordination"])


class CompanyOptionV1(BaseModel):
    """Opción de empresa para selector."""
    key: str
    name: str
    vat_id: str | None = None


class PlatformOptionV1(BaseModel):
    """Opción de plataforma para selector."""
    key: str
    name: str


class CoordinationContextOptionsV1(BaseModel):
    """Opciones disponibles para contexto de coordinación."""
    own_companies: List[CompanyOptionV1]
    platforms: List[PlatformOptionV1]
    coordinated_companies_by_platform: Dict[str, List[CompanyOptionV1]]


@router.get("/context/options", response_model=CoordinationContextOptionsV1)
async def get_coordination_context_options():
    """
    Obtiene las opciones disponibles para el contexto de coordinación.
    
    Returns:
        CoordinationContextOptionsV1 con:
        - own_companies: Empresas propias (quien coordina)
        - platforms: Plataformas disponibles
        - coordinated_companies_by_platform: Empresas coordinadas por plataforma
    """
    store = ConfigStoreV1(base_dir=DATA_DIR)
    
    # 1) Empresas propias: desde org.json
    # Por ahora solo hay una organización, pero se puede expandir
    org = store.load_org()
    own_companies = [
        CompanyOptionV1(
            key=org.tax_id,
            name=org.legal_name,
            vat_id=org.tax_id
        )
    ]
    
    # 2) Plataformas: desde platforms.json
    platforms_data = store.load_platforms()
    platforms = [
        PlatformOptionV1(
            key=p.key,
            name=p.key.replace("_", " ").title()  # "egestiona" -> "Egestiona"
        )
        for p in platforms_data.platforms
    ]
    
    # 3) Empresas coordinadas por plataforma: desde coordinations
    coordinated_companies_by_platform: Dict[str, List[CompanyOptionV1]] = {}
    
    for platform in platforms_data.platforms:
        coordinated = []
        for coord in platform.coordinations:
            coordinated.append(
                CompanyOptionV1(
                    key=coord.client_code,
                    name=coord.label,
                    vat_id=None  # No está disponible en CoordinationV1
                )
            )
        if coordinated:
            coordinated_companies_by_platform[platform.key] = coordinated
    
    return CoordinationContextOptionsV1(
        own_companies=own_companies,
        platforms=platforms,
        coordinated_companies_by_platform=coordinated_companies_by_platform
    )
