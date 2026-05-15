from pydantic import BaseModel, field_validator
from typing import Literal
from urllib.parse import urlparse
from datetime import datetime

SourceType = Literal["web", "gmail"]


class SourceCreate(BaseModel):
    name: str
    type: SourceType
    url: str | None = None
    gmail_sender: str | None = None
    active: bool = True

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("L'URL doit utiliser le scheme http ou https")
        if not parsed.netloc:
            raise ValueError("URL invalide : hostname manquant")
        return v


class Source(SourceCreate):
    id: str
    created_by: str
    created_at: datetime
