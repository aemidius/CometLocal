"""
H6 — RedactionPolicyV1 operativa (sin LLM)

Redacta PII/credenciales/tokens en:
- dom_snapshot_partial (estructuras)
- html_full (string)
- trace payloads (dict/list JSON-serializable)

Mantiene un redaction_report (contadores por tipo).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_SENSITIVE_KEYWORDS = (
    "pass",
    "password",
    "pwd",
    "token",
    "auth",
    "bearer",
    "session",
    "mail",
    "email",
    "phone",
    "tel",
    "dni",
    "nie",
    "nif",
)


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+?\d[\d\s\-]{7,}\d)\b")
NIF_RE = re.compile(r"\b\d{8}[A-Z]\b", re.IGNORECASE)
NIE_RE = re.compile(r"\b[XYZ]\d{7}[A-Z]\b", re.IGNORECASE)
# Token "largo" v1: >=20 chars alfanum/_/-, y debe contener al menos un dígito **o** una mayúscula.
# Evita falsos positivos sobre valores de schema tipo "observation_captured" (minúsculas + _).
TOKEN_RE = re.compile(r"\b(?=[A-Za-z0-9_\-]{20,}\b)(?=.*(\d|[A-Z]))[A-Za-z0-9_\-]{20,}\b")


def _key_is_sensitive(key: str) -> bool:
    k = (key or "").lower()
    return any(s in k for s in DEFAULT_SENSITIVE_KEYWORDS)


@dataclass
class RedactionReport:
    counts: Dict[str, int] = field(default_factory=dict)

    def inc(self, kind: str, n: int = 1) -> None:
        self.counts[kind] = int(self.counts.get(kind, 0)) + int(n)


class RedactorV1:
    def __init__(self, *, enabled: bool, strict: bool = True):
        self.enabled = enabled
        self.strict = strict
        self.report = RedactionReport()

    def redact_text(self, s: str) -> str:
        if not self.enabled or not s:
            return s

        original = s

        def sub_and_count(rx: re.Pattern, kind: str, txt: str) -> str:
            matches = list(rx.finditer(txt))
            if matches:
                self.report.inc(kind, len(matches))
                txt = rx.sub("***", txt)
            return txt

        s = sub_and_count(EMAIL_RE, "email", s)
        s = sub_and_count(PHONE_RE, "phone", s)
        s = sub_and_count(NIF_RE, "dni_nif", s)
        s = sub_and_count(NIE_RE, "dni_nie", s)
        s = sub_and_count(TOKEN_RE, "token", s)

        if s != original:
            self.report.inc("text_redactions", 1)
        return s

    def redact_html(self, html: str) -> str:
        if not self.enabled or not html:
            return html
        # Redacción general por regex + value/password patterns
        red = self.redact_text(html)

        # Redactar value="..." de inputs password y campos con nombres sensibles (regex conservador)
        # type=password
        pw_rx = re.compile(r'(<input[^>]*type=["\']password["\'][^>]*value=["\'])([^"\']*)(["\'])', re.IGNORECASE)
        m = list(pw_rx.finditer(red))
        if m:
            self.report.inc("password_value", len(m))
            red = pw_rx.sub(r"\1***\3", red)

        # name/id sensibles
        named_rx = re.compile(r'(<input[^>]*(?:name|id)=["\']([^"\']+)["\'][^>]*value=["\'])([^"\']*)(["\'])', re.IGNORECASE)
        out = red
        for mm in list(named_rx.finditer(out)):
            key = mm.group(2) or ""
            if _key_is_sensitive(key):
                self.report.inc("sensitive_input_value", 1)
                out = out.replace(mm.group(0), mm.group(1) + "***" + mm.group(4))
        return out

    def redact_jsonable(self, obj: Any, *, parent_key: Optional[str] = None) -> Any:
        """
        Recorre dict/list y redacta strings. Si la clave es sensible, redacta el valor completo.
        """
        if not self.enabled:
            return obj

        if isinstance(obj, str):
            return self.redact_text(obj)

        if isinstance(obj, dict):
            out: Dict[str, Any] = {}
            for k, v in obj.items():
                k_str = str(k)
                if _key_is_sensitive(k_str):
                    # redacción fuerte del valor
                    if isinstance(v, str) and v:
                        self.report.inc("sensitive_key", 1)
                        out[k_str] = "***"
                    else:
                        out[k_str] = self.redact_jsonable(v, parent_key=k_str)
                else:
                    out[k_str] = self.redact_jsonable(v, parent_key=k_str)
            return out

        if isinstance(obj, list):
            return [self.redact_jsonable(x, parent_key=parent_key) for x in obj]

        return obj


