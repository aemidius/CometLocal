"""
Conector para e-gestiona.

Sprint C2.12.1: Esqueleto funcional con stubs.
Sprint C2.12.2: Implementación end-to-end real.
"""

from backend.connectors.egestiona.connector import EgestionaConnector
from backend.connectors.registry import register_connector

# Registrar el conector automáticamente al importar
register_connector(EgestionaConnector)

__all__ = ["EgestionaConnector"]
