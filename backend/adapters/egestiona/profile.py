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
    # H8.D: Selector post-login definitivo (nav lateral con "Inicio")
    POST_LOGIN_SELECTOR: str = "nav a[href*='Inicio']"



