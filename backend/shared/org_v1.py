from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class OrgV1(BaseModel):
    schema_version: Literal["v1"] = "v1"
    legal_name: str = ""
    tax_id: str = ""
    org_type: str = "SCCL"
    notes: str = ""





