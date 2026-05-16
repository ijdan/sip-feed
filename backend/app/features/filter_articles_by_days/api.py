"""Endpoint FastAPI minimal pour la feature filter-articles-by-days."""
from __future__ import annotations

from fastapi import FastAPI

from . import service

app = FastAPI(title="Filter Articles by Days")


def _serialiser(article: dict) -> dict:
    sortie = {"id": article["id"]}
    if "category" in article:
        sortie["category"] = article["category"]
    if "collected_at" in article and article["collected_at"] is not None:
        sortie["collected_at"] = article["collected_at"].isoformat()
    return sortie


@app.get("/articles")
def get_articles(category: str | None = None) -> dict:
    articles = service.lister_articles(category=category)
    return {
        "articles": [_serialiser(a) for a in articles],
        "total": len(articles),
    }
