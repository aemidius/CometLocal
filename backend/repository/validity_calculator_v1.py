from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from backend.shared.document_repository_v1 import (
    ValidityPolicyV1,
    ExtractedMetadataV1,
    ComputedValidityV1,
)
from backend.repository.date_parser_v1 import compute_period_from_date


def compute_validity(
    policy: ValidityPolicyV1,
    extracted: ExtractedMetadataV1
) -> ComputedValidityV1:
    """
    Calcula la validez canónica de forma determinista usando la política declarativa.
    
    Retorna:
        ComputedValidityV1 con valid_from, valid_to, confidence y reasons
    """
    reasons: list[str] = []
    confidence = 0.0
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    
    # Determinar fecha base según basis
    base_date: Optional[date] = None
    if policy.basis == "issue_date":
        base_date = extracted.issue_date
        if base_date:
            reasons.append(f"using issue_date: {base_date.isoformat()}")
            confidence += 0.3
    elif policy.basis == "name_date":
        base_date = extracted.name_date
        if base_date:
            reasons.append(f"parsed name_date: {base_date.isoformat()}")
            confidence += 0.4
    elif policy.basis == "manual":
        # Manual requiere intervención, no calculamos automáticamente
        reasons.append("basis=manual requires manual input")
        return ComputedValidityV1(
            valid_from=None,
            valid_to=None,
            confidence=0.0,
            reasons=reasons
        )
    
    if not base_date:
        reasons.append("no base date available for calculation")
        return ComputedValidityV1(
            valid_from=None,
            valid_to=None,
            confidence=0.0,
            reasons=reasons
        )
    
    # Calcular según mode
    if policy.mode == "monthly":
        if not policy.monthly:
            reasons.append("monthly mode but no monthly config")
            return ComputedValidityV1(
                valid_from=None,
                valid_to=None,
                confidence=0.0,
                reasons=reasons
            )
        
        monthly_cfg = policy.monthly
        
        # Determinar fecha del mes según month_source
        month_date: Optional[date] = None
        if monthly_cfg.month_source == "issue_date":
            month_date = extracted.issue_date
            if month_date:
                reasons.append(f"month_source=issue_date: {month_date.isoformat()}")
        elif monthly_cfg.month_source == "name_date":
            month_date = extracted.name_date
            if month_date:
                reasons.append(f"month_source=name_date: {month_date.isoformat()}")
        
        if not month_date:
            reasons.append(f"month_source={monthly_cfg.month_source} but date not available")
            return ComputedValidityV1(
                valid_from=None,
                valid_to=None,
                confidence=0.0,
                reasons=reasons
            )
        
        # Calcular período mensual
        period_start, period_end = compute_period_from_date(month_date)
        extracted.period_start = period_start
        extracted.period_end = period_end
        reasons.append(f"computed period: {period_start.isoformat()} to {period_end.isoformat()}")
        confidence += 0.3
        
        # Aplicar valid_from y valid_to según config
        if monthly_cfg.valid_from == "period_start":
            valid_from = period_start
            reasons.append("valid_from=period_start")
        
        if monthly_cfg.valid_to == "period_end":
            valid_to = period_end
            if monthly_cfg.grace_days > 0:
                valid_to = valid_to + timedelta(days=monthly_cfg.grace_days)
                reasons.append(f"valid_to=period_end + {monthly_cfg.grace_days} grace_days")
            else:
                reasons.append("valid_to=period_end")
        
        confidence = min(confidence, 1.0)
    
    elif policy.mode == "annual":
        if not policy.annual:
            reasons.append("annual mode but no annual config")
            return ComputedValidityV1(
                valid_from=None,
                valid_to=None,
                confidence=0.0,
                reasons=reasons
            )
        
        annual_cfg = policy.annual
        
        if annual_cfg.valid_from == "issue_date":
            valid_from = base_date
            reasons.append(f"valid_from=issue_date: {valid_from.isoformat()}")
        
        if annual_cfg.valid_to == "issue_date_plus_months":
            # Calcular fin: base_date + months
            year = base_date.year
            month = base_date.month + annual_cfg.months
            while month > 12:
                year += 1
                month -= 12
            
            # Último día del mes resultante
            if month == 12:
                next_month = date(year + 1, 1, 1)
            else:
                next_month = date(year, month + 1, 1)
            valid_to = next_month - timedelta(days=1)
            reasons.append(f"valid_to=issue_date + {annual_cfg.months} months: {valid_to.isoformat()}")
        
        confidence = 0.8  # Alta confianza para anual
        confidence = min(confidence, 1.0)
    
    elif policy.mode == "fixed_end_date":
        if not policy.fixed_end_date:
            reasons.append("fixed_end_date mode but no fixed_end_date config")
            return ComputedValidityV1(
                valid_from=None,
                valid_to=None,
                confidence=0.0,
                reasons=reasons
            )
        
        fixed_cfg = policy.fixed_end_date
        
        if fixed_cfg.valid_from == "issue_date":
            valid_from = base_date
            reasons.append(f"valid_from=issue_date: {valid_from.isoformat()}")
        
        if fixed_cfg.valid_to == "manual_end_date":
            # Requiere fecha manual, no calculamos
            reasons.append("valid_to=manual_end_date requires manual input")
            confidence = 0.5  # Confianza parcial si tenemos valid_from
        else:
            confidence = 0.8
    
    # Validar que tenemos al menos una fecha
    if valid_from is None and valid_to is None:
        confidence = 0.0
        reasons.append("no dates computed")
    
    return ComputedValidityV1(
        valid_from=valid_from,
        valid_to=valid_to,
        confidence=confidence,
        reasons=reasons
    )




