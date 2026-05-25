from pydantic import BaseModel, ConfigDict


class ArticleSummary(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    article_id: str
    article_url: str
    summary_fr: str
    summary_en: str
    model_used: str
    generated_at: str
    word_count_fr: int
    word_count_en: int
    cached: bool = False
