"""
Configuración de tenants (empresas/contratas) para e-gestiona.

MVP: Estructura vacía. En C2.12.2 se añadirán perfiles por empresa.
"""

from typing import Dict

# Estructura de ejemplo (no usado aún en C2.12.1):
# TENANTS = {
#     "clienteX": {
#         "base_url": "https://egestiona.clienteX.com",
#         "selectors": {...},
#         "credentials": {...},  # No almacenar aquí, usar secrets
#     },
#     "clienteY": {...},
# }

TENANTS: Dict[str, Dict] = {}
