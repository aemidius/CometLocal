"""
Selectores CSS/XPath para e-gestiona.

PASO 1: Selectores reales basados en la estructura de e-gestiona.
"""

from typing import Dict

# Selectores de login (se cargan desde platforms.json, pero aquí como referencia)
LOGIN_SELECTORS = {
    "client_input": 'input[name="ClientName"]',
    "username_input": 'input[name="Username"]',
    "password_input": 'input[name="Password"]',
    "submit_button": 'button[type="submit"]',
}

# Selectores post-login
POST_LOGIN_MARKER = "text=Desconectar"  # Indicador de que el login fue exitoso

# Selectores de navegación a pendientes
PENDING_NAVIGATION = {
    "frame_main": 'frame[name="nm_contenido"]',
    "tile_pending": 'a.listado_link[href="javascript:Gestion(3);"]',
    "tile_pending_text": "text=/enviar.*pendiente|documentaci[oó]n.*pendiente/i",
}

# Selectores del grid de pendientes
PENDING_GRID = {
    "frame_list": 'frame[name="f3"]',  # Frame que contiene el grid
    "grid_header": "table.hdr",
    "grid_body": "table.obj.row20px",
    "grid_row": "table.obj.row20px tbody tr",
}

# Selectores de overlays/popups
OVERLAY_SELECTORS = {
    "dhx_modal": ".dhx_modal_cover, .dhx_modal_box",
    "close_button": "button:has-text('Cerrar'), .dhx_close_button",
}

# Selectores generales
SELECTORS: Dict[str, str] = {
    **LOGIN_SELECTORS,
    **PENDING_NAVIGATION,
    **PENDING_GRID,
    **OVERLAY_SELECTORS,
}
