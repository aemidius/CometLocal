"""
Interfaz base para conectores de plataformas CAE.

Todos los conectores deben implementar BaseConnector.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from playwright.async_api import Page

from backend.connectors.models import (
    PendingRequirement,
    UploadResult,
    RunContext,
)


class BaseConnector(ABC):
    """
    Interfaz abstracta para conectores de plataformas CAE.
    
    Cada plataforma (e-gestiona, twind, etc.) implementa esta interfaz
    para automatizar la interacción con su portal.
    """
    
    platform_id: str  # Debe ser definido por cada implementación
    
    def __init__(self, ctx: RunContext):
        """
        Inicializa el conector con un contexto de ejecución.
        
        Args:
            ctx: Contexto de ejecución con configuración
        """
        self.ctx = ctx
        if not self.platform_id:
            raise ValueError(f"Connector {self.__class__.__name__} must define platform_id")
    
    @abstractmethod
    async def login(self, page: Page) -> None:
        """
        Realiza el login en el portal.
        
        Args:
            page: Página de Playwright para interactuar
        
        Raises:
            Exception: Si el login falla
        """
        pass
    
    @abstractmethod
    async def navigate_to_pending(self, page: Page) -> None:
        """
        Navega a la página de requisitos pendientes.
        
        Args:
            page: Página de Playwright
        
        Raises:
            Exception: Si la navegación falla
        """
        pass
    
    @abstractmethod
    async def extract_pending(self, page: Page) -> List[PendingRequirement]:
        """
        Extrae la lista de requisitos pendientes de la página actual.
        
        Args:
            page: Página de Playwright
        
        Returns:
            Lista de requisitos pendientes normalizados
        
        Raises:
            Exception: Si la extracción falla
        """
        pass
    
    @abstractmethod
    async def match_repository(
        self,
        reqs: List[PendingRequirement]
    ) -> Dict[str, Any]:
        """
        Hace matching de requisitos con documentos del repositorio.
        
        Args:
            reqs: Lista de requisitos pendientes
        
        Returns:
            Dict mapping requirement_id -> match result dict con:
            - decision: "match" | "no_match"
            - chosen_doc_id: str | None
            - matched_type_id: str | None
            - candidate_docs: List[Dict]
            - decision_reason: str
            O formato simple: requirement_id -> doc_id (backward compat)
        """
        pass
    
    @abstractmethod
    async def upload_one(
        self,
        page: Page,
        req: PendingRequirement,
        doc_id: str
    ) -> UploadResult:
        """
        Sube un documento para un requisito específico.
        
        Args:
            page: Página de Playwright
            req: Requisito pendiente
            doc_id: ID del documento del repositorio a subir
        
        Returns:
            Resultado de la subida
        
        Raises:
            Exception: Si la subida falla críticamente
        """
        pass
