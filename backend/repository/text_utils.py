from __future__ import annotations

import re


def normalize_text(text: str) -> str:
    """Normaliza texto para matching: lowercase, elimina espacios extra."""
    if not text:
        return ""
    # Convertir a lowercase y normalizar espacios
    normalized = re.sub(r'\s+', ' ', text.lower().strip())
    return normalized


def normalize_whitespace(text: str) -> str:
    """Normaliza espacios en blanco (múltiples espacios -> uno)."""
    return re.sub(r'\s+', ' ', text.strip())




