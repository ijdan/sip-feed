from pydantic import BaseModel, field_validator, ConfigDict
from typing import Literal
from datetime import datetime

Category = Literal["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"]
VALID_CATEGORIES = {"IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"}


class Article(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    title_fr: str = ""
    title_en: str = ""
    short_description: str
    short_description_fr: str = ""
    short_description_en: str = ""
    long_description: str
    long_description_fr: str = ""
    long_description_en: str = ""
    keywords_fr: list[str] = []
    keywords_en: list[str] = []
    article_url: str
    source_name: str
    source_id: str
    category: str
    published_at: str
    collected_at: str

    @field_validator("category")
    @classmethod
    def normalize_category(cls, v: str) -> str:
        if v in VALID_CATEGORIES:
            return v
        return "Autre"


class ArticleList(BaseModel):
    items: list[Article]
