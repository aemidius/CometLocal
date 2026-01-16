"""
Registry de conectores.

Permite registrar y obtener conectores por platform_id.
"""

from typing import Dict, Type, Optional, List
from backend.connectors.base import BaseConnector
from backend.connectors.models import RunContext

# Registry global de conectores
_connector_classes: Dict[str, Type[BaseConnector]] = {}


def register_connector(connector_class: Type[BaseConnector]) -> None:
    """
    Registra una clase de conector.
    
    Args:
        connector_class: Clase que implementa BaseConnector
    
    Raises:
        ValueError: Si la clase no tiene platform_id o ya está registrada
    """
    if not hasattr(connector_class, 'platform_id') or not connector_class.platform_id:
        raise ValueError(f"Connector class {connector_class.__name__} must define platform_id")
    
    platform_id = connector_class.platform_id
    if platform_id in _connector_classes:
        raise ValueError(f"Connector for platform '{platform_id}' already registered")
    
    _connector_classes[platform_id] = connector_class


def get_connector(platform_id: str, ctx: RunContext) -> Optional[BaseConnector]:
    """
    Obtiene una instancia de conector para una plataforma.
    
    Args:
        platform_id: ID de la plataforma (ej "egestiona")
        ctx: Contexto de ejecución
    
    Returns:
        Instancia del conector o None si no está registrado
    """
    connector_class = _connector_classes.get(platform_id)
    if not connector_class:
        return None
    
    return connector_class(ctx)


def list_platforms() -> List[str]:
    """
    Lista todas las plataformas registradas.
    
    Returns:
        Lista de platform_ids
    """
    return list(_connector_classes.keys())
