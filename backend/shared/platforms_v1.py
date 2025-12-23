from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field
from pydantic import field_validator


class SelectorSpecV1(BaseModel):
    """
    Selector determinista serializable para config store.
    Compatibilidad: en JSON histórico se aceptan strings (se interpretan como css).
    """

    kind: Literal["css", "xpath"] = "css"
    value: str


class CoordinationV1(BaseModel):
    label: str = ""
    client_code: str = ""
    username: str = ""
    password_ref: str = ""  # referencia en secrets.json
    url_override: Optional[str] = None
    post_login_selector: Optional[SelectorSpecV1] = None

    @field_validator("post_login_selector", mode="before")
    @classmethod
    def _coerce_post_login_selector(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, SelectorSpecV1):
            return v
        if isinstance(v, str):
            return SelectorSpecV1(kind="css", value=v)
        if isinstance(v, dict):
            return SelectorSpecV1.model_validate(v)
        raise TypeError("post_login_selector must be a string or {kind,value}")


class LoginFieldsV1(BaseModel):
    requires_client: bool = True
    client_code_selector: Optional[SelectorSpecV1] = None
    username_selector: Optional[SelectorSpecV1] = None
    password_selector: Optional[SelectorSpecV1] = None
    submit_selector: Optional[SelectorSpecV1] = None

    @field_validator("client_code_selector", "username_selector", "password_selector", "submit_selector", mode="before")
    @classmethod
    def _coerce_selector(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, SelectorSpecV1):
            return v
        if isinstance(v, str):
            return SelectorSpecV1(kind="css", value=v)
        if isinstance(v, dict):
            return SelectorSpecV1.model_validate(v)
        raise TypeError("selector must be a string or {kind,value}")


class PlatformV1(BaseModel):
    key: str  # p.ej. "egestiona_kern"
    base_url: str
    login_fields: LoginFieldsV1 = Field(default_factory=LoginFieldsV1)
    coordinations: List[CoordinationV1] = Field(default_factory=list)


class PlatformsV1(BaseModel):
    schema_version: Literal["v1"] = "v1"
    platforms: List[PlatformV1] = Field(default_factory=list)


