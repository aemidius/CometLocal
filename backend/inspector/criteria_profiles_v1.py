"""
H7.6 — Criteria Profiles v1 (declarativos, deterministas)

Cada criterio:
- id (estable)
- descripción
- check(text, extracted, metadata) -> (ok, details)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _parse_iso_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


@dataclass(frozen=True)
class CriterionResultV1:
    id: str
    status: str  # ok | failed
    details: str


CriterionFnV1 = Callable[[str, Dict[str, Any], Dict[str, Any]], Tuple[bool, str]]


@dataclass(frozen=True)
class CriterionV1:
    id: str
    description: str
    fn: CriterionFnV1


def issue_date_present() -> CriterionV1:
    def _fn(_text: str, extracted: Dict[str, Any], _meta: Dict[str, Any]) -> Tuple[bool, str]:
        v = extracted.get("issue_date")
        return (v is not None, f"issue_date={v!r}")

    return CriterionV1(id="issue_date_present", description="Debe existir fecha de emisión/expedición", fn=_fn)


def valid_until_present() -> CriterionV1:
    def _fn(_text: str, extracted: Dict[str, Any], _meta: Dict[str, Any]) -> Tuple[bool, str]:
        v = extracted.get("valid_until")
        return (v is not None, f"valid_until={v!r}")

    return CriterionV1(id="valid_until_present", description="Debe existir fecha de validez/caducidad", fn=_fn)


def valid_until_in_future() -> CriterionV1:
    def _fn(_text: str, extracted: Dict[str, Any], _meta: Dict[str, Any]) -> Tuple[bool, str]:
        d = _parse_iso_date(extracted.get("valid_until"))
        if d is None:
            return False, "valid_until missing/invalid"
        ok = d >= _today_utc()
        return ok, f"valid_until={d.isoformat()} today={_today_utc().isoformat()}"

    return CriterionV1(id="valid_until_in_future", description="La validez no debe estar caducada", fn=_fn)


def issue_date_not_older_than(months: int) -> CriterionV1:
    # aproximación determinista (30 días/mes)
    max_age_days = int(months) * 30

    def _fn(_text: str, extracted: Dict[str, Any], _meta: Dict[str, Any]) -> Tuple[bool, str]:
        d = _parse_iso_date(extracted.get("issue_date"))
        if d is None:
            return False, "issue_date missing/invalid"
        age = (_today_utc() - d).days
        ok = age <= max_age_days
        return ok, f"issue_date={d.isoformat()} age_days={age} max_days={max_age_days}"

    return CriterionV1(
        id=f"issue_date_not_older_than_{months}m",
        description=f"La emisión no debe ser anterior a {months} meses",
        fn=_fn,
    )


def contains_company_nif() -> CriterionV1:
    def _fn(text: str, _extracted: Dict[str, Any], meta: Dict[str, Any]) -> Tuple[bool, str]:
        nif = (meta.get("company_nif") or meta.get("company_tax_id") or "").strip()
        if not nif:
            return False, "company_nif missing in metadata"
        ok = nif.lower() in text.lower()
        return ok, f"company_nif={nif!r} present={ok}"

    return CriterionV1(id="contains_company_nif", description="El texto debe contener el NIF/CIF de la empresa", fn=_fn)


def contains_worker_dni() -> CriterionV1:
    def _fn(text: str, _extracted: Dict[str, Any], meta: Dict[str, Any]) -> Tuple[bool, str]:
        dni = (meta.get("worker_dni") or "").strip()
        if not dni:
            return False, "worker_dni missing in metadata"
        ok = dni.lower() in text.lower()
        return ok, f"worker_dni={dni!r} present={ok}"

    return CriterionV1(id="contains_worker_dni", description="El texto debe contener el DNI del trabajador", fn=_fn)


CRITERIA_PROFILES_V1: Dict[str, List[CriterionV1]] = {
    # Ejemplos conservadores: sin heurísticas creativas.
    "prl_training_v1": [
        issue_date_present(),
        issue_date_not_older_than(12),
    ],
    "cae_insurance_v1": [
        valid_until_present(),
        valid_until_in_future(),
    ],
    "medical_fit_v1": [
        issue_date_present(),
        valid_until_present(),
        valid_until_in_future(),
    ],
}


def get_profile(profile_id: Optional[str]) -> List[CriterionV1]:
    if not profile_id:
        return []
    return list(CRITERIA_PROFILES_V1.get(profile_id, []))


