from pydantic import BaseModel
from typing import Literal
from datetime import datetime

SourceType = Literal["web", "gmail"]


class SourceCreate(BaseModel):
    name: str
    type: SourceType
    url: str | None = None
    gmail_sender: str | None = None
    active: bool = True


class Source(SourceCreate):
    id: str
    created_by: str
    created_at: datetime
