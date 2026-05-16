"""API FastAPI minimale exposée aux tests d'acceptance.

La logique de filtrage est portée par le service. En production, la même
règle est appliquée dans backend/app/routers/articles.py.
"""
from fastapi import FastAPI

from . import service

app = FastAPI()


@app.get("/articles")
def lister_articles(category: str | None = None):
    articles = service.lister_articles_filtres(category=category)
    return {"articles": articles, "total": len(articles)}
