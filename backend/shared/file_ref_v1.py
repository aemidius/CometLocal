"""
H7.5 — file_ref contract v1 (estable)

Formato canónico:
  doc:company:<company_id>:worker:<worker_id>:<namespace>:<name>
  doc:company:<company_id>:company_docs:<namespace>:<name>
  doc:shared:<namespace>:<name>

Reglas:
- El executor NO usa paths directos: todo pasa por file_ref.
- La resolución a Path real se hace SOLO en DocumentRepositoryV1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


_TOKEN_RE = r"[A-Za-z0-9][A-Za-z0-9_\-\.]{0,63}"

_WORKER_RE = re.compile(
    rf"^doc:company:(?P<company_id>{_TOKEN_RE}):worker:(?P<worker_id>{_TOKEN_RE}):(?P<namespace>{_TOKEN_RE}):(?P<name>{_TOKEN_RE})$"
)
_COMPANY_DOC_RE = re.compile(
    rf"^doc:company:(?P<company_id>{_TOKEN_RE}):company_docs:(?P<namespace>{_TOKEN_RE}):(?P<name>{_TOKEN_RE})$"
)
_SHARED_RE = re.compile(rf"^doc:shared:(?P<namespace>{_TOKEN_RE}):(?P<name>{_TOKEN_RE})$")


class FileRefV1(BaseModel):
    """
    Representación parseada del file_ref.
    """

    raw: str = Field(..., description="file_ref canónico")
    scope: Literal["worker", "company_docs", "shared"]

    company_id: Optional[str] = None
    worker_id: Optional[str] = None
    namespace: str
    name: str

    @field_validator("raw")
    @classmethod
    def _validate_syntax(cls, v: str) -> str:
        if not validate_syntax(v):
            raise ValueError("Invalid file_ref syntax")
        return v

    @model_validator(mode="after")
    def _validate_shape(self) -> "FileRefV1":
        if self.scope == "worker":
            if not self.company_id or not self.worker_id:
                raise ValueError("worker scope requires company_id and worker_id")
        if self.scope == "company_docs":
            if not self.company_id or self.worker_id:
                raise ValueError("company_docs scope requires company_id and no worker_id")
        if self.scope == "shared":
            if self.company_id or self.worker_id:
                raise ValueError("shared scope does not allow company_id/worker_id")
        return self

    def canonical(self) -> str:
        return self.raw


def validate_syntax(file_ref: str) -> bool:
    if not isinstance(file_ref, str) or not file_ref:
        return False
    return bool(_WORKER_RE.match(file_ref) or _COMPANY_DOC_RE.match(file_ref) or _SHARED_RE.match(file_ref))


def parse(file_ref: str) -> FileRefV1:
    """
    Parsea y valida un file_ref canónico.
    """
    m = _WORKER_RE.match(file_ref)
    if m:
        return FileRefV1(
            raw=file_ref,
            scope="worker",
            company_id=m.group("company_id"),
            worker_id=m.group("worker_id"),
            namespace=m.group("namespace"),
            name=m.group("name"),
        )
    m = _COMPANY_DOC_RE.match(file_ref)
    if m:
        return FileRefV1(
            raw=file_ref,
            scope="company_docs",
            company_id=m.group("company_id"),
            worker_id=None,
            namespace=m.group("namespace"),
            name=m.group("name"),
        )
    m = _SHARED_RE.match(file_ref)
    if m:
        return FileRefV1(
            raw=file_ref,
            scope="shared",
            company_id=None,
            worker_id=None,
            namespace=m.group("namespace"),
            name=m.group("name"),
        )
    # Forzar error tipado
    return FileRefV1(raw=file_ref, scope="shared", namespace="invalid", name="invalid")


def build_worker_ref(*, company_id: str, worker_id: str, namespace: str, name: str) -> str:
    return f"doc:company:{company_id}:worker:{worker_id}:{namespace}:{name}"


def build_company_doc_ref(*, company_id: str, namespace: str, name: str) -> str:
    return f"doc:company:{company_id}:company_docs:{namespace}:{name}"


def build_shared_ref(*, namespace: str, name: str) -> str:
    return f"doc:shared:{namespace}:{name}"




