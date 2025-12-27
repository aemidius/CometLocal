from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PersonV1(BaseModel):
    worker_id: str
    full_name: str = ""
    tax_id: str = ""  # DNI/NIE/NIF
    role: str = ""  # p.ej. "worker", "admin", "prl"
    relation_type: str = ""  # p.ej. "employee", "contractor"


class PeopleV1(BaseModel):
    schema_version: Literal["v1"] = "v1"
    people: List[PersonV1] = Field(default_factory=list)









