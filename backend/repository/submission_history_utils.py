from __future__ import annotations

import hashlib
import re
from typing import Dict, Any, Optional


def normalize_text_for_fingerprint(text: str) -> str:
    """Normaliza texto para fingerprint: lowercase, trim, collapse whitespace."""
    if not text:
        return ""
    # Convertir a lowercase y normalizar espacios
    normalized = re.sub(r'\s+', ' ', text.lower().strip())
    return normalized


def compute_pending_fingerprint(
    platform_key: str,
    coord_label: Optional[str],
    pending_item_dict: Dict[str, Any],
) -> str:
    """
    Calcula fingerprint determinista para un pending item.
    
    Usa campos estables:
    - tipo_doc
    - elemento
    - empresa
    - centro_trabajo (si existe)
    - trabajador (si existe)
    
    Normaliza texto y genera SHA256 hex.
    """
    # Extraer campos estables
    tipo_doc = normalize_text_for_fingerprint(pending_item_dict.get("tipo_doc", ""))
    elemento = normalize_text_for_fingerprint(pending_item_dict.get("elemento", ""))
    empresa = normalize_text_for_fingerprint(pending_item_dict.get("empresa", ""))
    centro_trabajo = normalize_text_for_fingerprint(pending_item_dict.get("centro_trabajo", ""))
    trabajador = normalize_text_for_fingerprint(pending_item_dict.get("trabajador", ""))
    
    # Construir string canónico
    parts = [
        platform_key,
        coord_label or "",
        tipo_doc,
        elemento,
        empresa,
        centro_trabajo,
        trabajador,
    ]
    canonical = "|".join(parts)
    
    # Calcular SHA256
    sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    
    return sha256




