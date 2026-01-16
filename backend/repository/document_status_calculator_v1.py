from __future__ import annotations

from datetime import date, timedelta
from typing import Optional, Tuple
from calendar import monthrange

from backend.shared.document_repository_v1 import DocumentInstanceV1, ComputedValidityV1, DocumentTypeV1


class DocumentValidityStatus(str):
    """Estado de validez del documento."""
    VALID = "VALID"
    EXPIRING_SOON = "EXPIRING_SOON"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


def parse_period_key(period_key: str) -> Optional[date]:
    """Parsea period_key (YYYY-MM, YYYY, YYYY-Qn) a fecha (primer día)."""
    if not period_key:
        return None
    
    try:
        if len(period_key) == 7 and period_key[4] == '-':  # YYYY-MM
            year, month = period_key.split('-')
            return date(int(year), int(month), 1)
        elif len(period_key) == 4:  # YYYY
            return date(int(period_key), 1, 1)
        elif period_key.startswith('Q'):  # Q1, Q2, etc. (no soportado aún)
            return None
    except (ValueError, IndexError):
        pass
    
    return None


def add_months(base_date: date, months: int) -> date:
    """Añade N meses a una fecha."""
    year = base_date.year
    month = base_date.month + months
    while month > 12:
        year += 1
        month -= 12
    while month < 1:
        year -= 1
        month += 12
    
    # Ajustar día si el mes resultante tiene menos días
    last_day = monthrange(year, month)[1]
    day = min(base_date.day, last_day)
    
    return date(year, month, day)


def calculate_document_status(
    doc: DocumentInstanceV1,
    doc_type: Optional[DocumentTypeV1] = None,
    expiring_soon_threshold_days: int = 30
) -> Tuple[DocumentValidityStatus, Optional[date], Optional[int], Optional[str], Optional[str]]:
    """
    Calcula el estado de validez del documento usando la base_date correcta según las reglas.
    
    Args:
        doc: Instancia del documento
        doc_type: Tipo de documento (opcional, se carga si no se proporciona)
        expiring_soon_threshold_days: Días antes de expirar para considerar "EXPIRING_SOON" (default: 30)
    
    Returns:
        Tupla (status, validity_end_date, days_until_expiry, base_date, base_reason):
        - status: VALID, EXPIRING_SOON, EXPIRED, o UNKNOWN
        - validity_end_date: Fecha de caducidad (valid_to) o None
        - days_until_expiry: Días hasta la caducidad (positivo si futuro, negativo si pasado) o None
        - base_date: Fecha base usada para el cálculo (para debug)
        - base_reason: Razón de por qué se usó esa base_date (para debug)
    """
    today = date.today()
    
    # Si hay override manual, usar ese directamente
    if doc.validity_override and doc.validity_override.valid_to:
        validity_end_date = doc.validity_override.valid_to
        days_until_expiry = (validity_end_date - today).days
        
        if days_until_expiry < 0:
            status = DocumentValidityStatus.EXPIRED
        elif days_until_expiry <= expiring_soon_threshold_days:
            status = DocumentValidityStatus.EXPIRING_SOON
        else:
            status = DocumentValidityStatus.VALID
        
        return status, validity_end_date, days_until_expiry, None, "validity_override"
    
    # Cargar tipo de documento si no se proporciona
    if doc_type is None:
        try:
            from backend.repository.document_repository_store_v1 import DocumentRepositoryStoreV1
            store = DocumentRepositoryStoreV1()
            doc_type = store.get_type(doc.type_id)
        except Exception:
            doc_type = None
    
    if not doc_type:
        # Sin tipo, intentar usar computed_validity existente
        if doc.computed_validity and doc.computed_validity.valid_to:
            validity_end_date = doc.computed_validity.valid_to
            days_until_expiry = (validity_end_date - today).days
            
            if days_until_expiry < 0:
                status = DocumentValidityStatus.EXPIRED
            elif days_until_expiry <= expiring_soon_threshold_days:
                status = DocumentValidityStatus.EXPIRING_SOON
            else:
                status = DocumentValidityStatus.VALID
            
            return status, validity_end_date, days_until_expiry, None, "computed_validity_fallback"
        
        return DocumentValidityStatus.UNKNOWN, None, None, None, "no_doc_type"
    
    # Determinar base_date según las reglas
    base_date: Optional[date] = None
    base_reason: Optional[str] = None
    
    # Regla 1: Si hay validity_start_date, usarla (prioridad máxima)
    if doc.extracted and doc.extracted.validity_start_date:
        base_date = doc.extracted.validity_start_date
        base_reason = "validity_start_date"
    # Regla 2: Si validity_start_mode == "manual" pero falta validity_start_date, retornar UNKNOWN
    elif doc_type.validity_start_mode == "manual":
        return DocumentValidityStatus.UNKNOWN, None, None, None, "missing_validity_start_date_for_manual_mode"
    # Regla 3: Fallback a issue_date si existe
    elif doc.extracted and doc.extracted.issue_date:
        base_date = doc.extracted.issue_date
        base_reason = "issue_date"
    elif doc.issued_at:
        base_date = doc.issued_at
        base_reason = "issued_at"
    # Regla 4: Fallback a period_key si el tipo usa período como base
    elif doc.period_key:
        # Solo usar period_key si el tipo tiene periodicidad mensual/anual
        policy = doc_type.validity_policy
        if policy.mode in ("monthly", "annual") or (policy.n_months and policy.n_months.n > 0):
            base_date = parse_period_key(doc.period_key)
            if base_date:
                base_reason = "period_key"
    
    if not base_date:
        return DocumentValidityStatus.UNKNOWN, None, None, None, "no_base_date_available"
    
    # Calcular validity_end_date según la política del tipo
    validity_end_date: Optional[date] = None
    policy = doc_type.validity_policy
    
    # PRIORIDAD: n_months override tiene prioridad sobre mode
    if policy.n_months and policy.n_months.n > 0:
        # Cada N meses (ej: cada 12 meses)
        validity_end_date = add_months(base_date, policy.n_months.n)
    elif policy.mode == "annual":
        if policy.annual:
            months = policy.annual.months
            validity_end_date = add_months(base_date, months)
    elif policy.mode == "monthly":
        if policy.monthly:
            # Para monthly, el período es 1 mes desde el mes del base_date
            validity_end_date = add_months(base_date, 1)
            # Ajustar al último día del mes
            if validity_end_date.month == 12:
                validity_end_date = date(validity_end_date.year, 12, 31)
            else:
                validity_end_date = date(validity_end_date.year, validity_end_date.month + 1, 1) - timedelta(days=1)
            # Añadir grace_days si hay
            if policy.monthly.grace_days > 0:
                validity_end_date = validity_end_date + timedelta(days=policy.monthly.grace_days)
    elif policy.mode == "fixed_end_date":
        # Para fixed_end_date, requiere override manual o no se calcula
        if doc.validity_override and doc.validity_override.valid_to:
            validity_end_date = doc.validity_override.valid_to
        else:
            return DocumentValidityStatus.UNKNOWN, None, None, base_date, "fixed_end_date_requires_manual_input"
    
    if not validity_end_date:
        return DocumentValidityStatus.UNKNOWN, None, None, base_date, "could_not_calculate_end_date"
    
    # Calcular días hasta la caducidad
    days_until_expiry = (validity_end_date - today).days
    
    # Determinar estado
    # Si validity_start_date es futura y aún no ha empezado, considerar válido
    if base_date and base_date > today:
        # Aún no ha empezado la vigencia, pero lo consideramos válido
        status = DocumentValidityStatus.VALID
    elif days_until_expiry < 0:
        # Ya expirado
        status = DocumentValidityStatus.EXPIRED
    elif days_until_expiry <= expiring_soon_threshold_days:
        # Expira pronto
        status = DocumentValidityStatus.EXPIRING_SOON
    else:
        # Válido
        status = DocumentValidityStatus.VALID
    
    return status, validity_end_date, days_until_expiry, base_date, base_reason


