from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EgestionaProfileV1:
    """
    Perfil determinista para eGestiona.
    - Los selectores se leen de Config Store (platforms.json).
    - Aquí solo fijamos defaults conservadores.
    """

    platform_key: str = "egestiona"
    default_base_url: str = "https://coordinate.egestiona.es"
    default_timeout_ms: int = 15000
    # Post-login check robusto (sidebar): el texto "Desconectar" aparece solo cuando ya estás dentro.
    # Nota: Playwright soporta selector `text=...` vía page.locator().
    POST_LOGIN_SELECTOR: str = "text=Desconectar"



