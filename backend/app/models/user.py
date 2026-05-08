from pydantic import BaseModel
from typing import Literal
from datetime import datetime

Role = Literal["admin", "reader"]


class User(BaseModel):
    id: str
    email: str
    role: Role
    created_at: datetime
