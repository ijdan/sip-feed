from pydantic import BaseModel
from typing import Literal
from datetime import datetime

Role = Literal["admin", "reader"]


class User(BaseModel):
    internal_id: str       # identifiant interne stable (usr_xxxx)
    email: str
    name: str = ""
    avatar: str = ""
    role: Role = "reader"
    provider: str = "google"
    created_at: str


class UserUpdate(BaseModel):
    name: str | None = None


class UserPreferences(BaseModel):
    favorites: list[str] = []
    reading_list: list[str] = []
    read_articles: list[str] = []
    dismissed: list[str] = []
