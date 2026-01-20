"""
SPRINT C2.34: Taxonomía cerrada de códigos de razón para matching_debug_report.

Códigos de razón que explican por qué un pending requirement termina en NO_MATCH
o REVIEW_REQUIRED, sin cambiar la lógica de matching.
"""

from typing import Dict, Any, Optional


# Códigos de razón (taxonomía cerrada)
NO_LOCAL_DOCS = "NO_LOCAL_DOCS"
TYPE_NOT_FOUND = "TYPE_NOT_FOUND"
TYPE_INACTIVE = "TYPE_INACTIVE"
ALIAS_NOT_MATCHING = "ALIAS_NOT_MATCHING"
SCOPE_MISMATCH = "SCOPE_MISMATCH"
PERIOD_MISMATCH = "PERIOD_MISMATCH"
COMPANY_MISMATCH = "COMPANY_MISMATCH"
PERSON_MISMATCH = "PERSON_MISMATCH"
VALIDITY_MISMATCH = "VALIDITY_MISMATCH"


def make_reason(
    code: str,
    message: str,
    hint: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Helper para crear un reason dict serializable.
    
    Args:
        code: Código de razón (de la taxonomía cerrada)
        message: Mensaje descriptivo
        hint: Hint accionable para el usuario (opcional)
        meta: Metadata adicional (opcional)
    
    Returns:
        Dict serializable con keys: code, message, hint (si existe), meta (si existe)
    """
    reason = {
        "code": code,
        "message": message,
    }
    if hint is not None:
        reason["hint"] = hint
    if meta is not None:
        reason["meta"] = meta
    return reason
