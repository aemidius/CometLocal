from pydantic import BaseModel
from typing import List, Optional

class Step(BaseModel):
    type: str
    description: str
    objective: Optional[str] = None
    url: Optional[str] = None

class Plan(BaseModel):
    steps: List[Step]
