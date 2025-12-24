from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field
from pydantic import field_validator
from pydantic.alias_generators import to_camel
from pydantic import AliasChoices
from pydantic.config import ConfigDict


class SelectorSpecV1(BaseModel):
    """
    Selector determinista serializable para config store.
    Compatibilidad: en JSON histórico se aceptan strings (se interpretan como css).
    """

    kind: Literal["css", "xpath"] = "css"
    value: str


def normalize_selector(sel: Any) -> Optional[SelectorSpecV1]:
    """
    Parsing tolerante para selectors en platforms.json.
    Formatos aceptados:
    A) SelectorSpecV1 dict: {"kind":"css"|"xpath","value":"..."}
    B) string css directo: "input[name='ClientName']"
    C) TargetV1 dict legacy: {"type":"css"|"xpath","selector":"..."} (y variantes equivalentes)
    """
    if sel is None or sel == "":
        return None
    if isinstance(sel, SelectorSpecV1):
        return sel
    if isinstance(sel, str):
        return SelectorSpecV1(kind="css", value=sel)
    if isinstance(sel, dict):
        # Formato v2 (kind/value)
        if "kind" in sel and "value" in sel:
            return SelectorSpecV1.model_validate(sel)
        # Formato TargetV1 legacy (type/selector)
        if "type" in sel and "selector" in sel:
            t = str(sel.get("type") or "").strip().lower()
            v = str(sel.get("selector") or "")
            if t in ("css", "xpath") and v:
                return SelectorSpecV1(kind=t, value=v)
        # Algunas variantes vistas en configs manuales
        if "kind" in sel and "selector" in sel:
            t = str(sel.get("kind") or "").strip().lower()
            v = str(sel.get("selector") or "")
            if t in ("css", "xpath") and v:
                return SelectorSpecV1(kind=t, value=v)
    raise TypeError("selector must be a string, {kind,value} or legacy TargetV1 {type,selector}")


class CoordinationV1(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    label: str = ""
    client_code: str = ""
    username: str = ""
    password_ref: str = ""  # referencia en secrets.json
    url_override: Optional[str] = None
    # Nuevo nombre de UI/config: post_login_check (backward-compatible con post_login_selector)
    post_login_selector: Optional[SelectorSpecV1] = Field(
        default=None,
        validation_alias=AliasChoices("post_login_selector", "post_login_check"),
        serialization_alias="post_login_check",
    )

    @field_validator("post_login_selector", mode="before")
    @classmethod
    def _coerce_post_login_selector(cls, v):
        return normalize_selector(v)


class LoginFieldsV1(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    requires_client: bool = True
    # Nuevo esquema de UI/config (keys exactas pedidas):
    # - client_input, user_input, pass_input, submit_btn
    # Backward-compat con nombres legacy *_selector.
    client_code_selector: Optional[SelectorSpecV1] = Field(
        default=None,
        validation_alias=AliasChoices("client_code_selector", "client_input"),
        serialization_alias="client_input",
    )
    username_selector: Optional[SelectorSpecV1] = Field(
        default=None,
        validation_alias=AliasChoices("username_selector", "user_input"),
        serialization_alias="user_input",
    )
    password_selector: Optional[SelectorSpecV1] = Field(
        default=None,
        validation_alias=AliasChoices("password_selector", "pass_input"),
        serialization_alias="pass_input",
    )
    submit_selector: Optional[SelectorSpecV1] = Field(
        default=None,
        validation_alias=AliasChoices("submit_selector", "submit_btn"),
        serialization_alias="submit_btn",
    )

    @field_validator("client_code_selector", "username_selector", "password_selector", "submit_selector", mode="before")
    @classmethod
    def _coerce_selector(cls, v):
        return normalize_selector(v)


class PlatformV1(BaseModel):
    key: str  # p.ej. "egestiona_kern"
    base_url: str
    login_fields: LoginFieldsV1 = Field(default_factory=LoginFieldsV1)
    coordinations: List[CoordinationV1] = Field(default_factory=list)


class PlatformsV1(BaseModel):
    schema_version: Literal["v1"] = "v1"
    platforms: List[PlatformV1] = Field(default_factory=list)


