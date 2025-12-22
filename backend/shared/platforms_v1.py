from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class CoordinationV1(BaseModel):
    label: str = ""
    client_code: str = ""
    username: str = ""
    password_ref: str = ""  # referencia en secrets.json
    url_override: Optional[str] = None
    post_login_selector: Optional[str] = None


class LoginFieldsV1(BaseModel):
    requires_client: bool = True
    client_code_selector: Optional[str] = None
    username_selector: Optional[str] = None
    password_selector: Optional[str] = None
    submit_selector: Optional[str] = None


class PlatformV1(BaseModel):
    key: str  # p.ej. "egestiona_kern"
    base_url: str
    login_fields: LoginFieldsV1 = Field(default_factory=LoginFieldsV1)
    coordinations: List[CoordinationV1] = Field(default_factory=list)


class PlatformsV1(BaseModel):
    schema_version: Literal["v1"] = "v1"
    platforms: List[PlatformV1] = Field(default_factory=list)


