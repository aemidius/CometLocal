"""
Connector SDK para plataformas CAE.

Este módulo proporciona un framework mínimo para crear conectores
que automatizan la interacción con portales CAE (e-gestiona, twind, etc.).

Cada conector implementa:
- Login en el portal
- Navegación a página de pendientes
- Extracción de requisitos pendientes
- Matching con repositorio de documentos
- Subida de documentos

v1.0.0 - Sprint C2.12.1: SDK mínimo + esqueleto e-gestiona
"""

from backend.connectors.models import (
    PendingRequirement,
    UploadResult,
    RunContext,
)
from backend.connectors.base import BaseConnector
from backend.connectors.registry import get_connector, register_connector

__all__ = [
    "PendingRequirement",
    "UploadResult",
    "RunContext",
    "BaseConnector",
    "get_connector",
    "register_connector",
]
