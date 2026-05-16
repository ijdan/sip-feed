"""Service en mémoire pour la feature « filtrage des articles par ancienneté ».

Stockage volontairement simpliste (dict en mémoire) : la spec porte sur la
sémantique de filtrage et l'absence de suppression côté collector, pas sur
la persistance réelle.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

# État global du « Firestore » simulé.
_collections: dict[str, dict[str, dict]] = {"articles": {}}
_retention_days: int | None = None


def reset() -> None:
    _collections["articles"].clear()
    global _retention_days
    _retention_days = None


def set_articles(articles: Iterable[dict]) -> None:
    """Remplace le contenu de la collection « articles »."""
    _collections["articles"].clear()
    for article in articles:
        _collections["articles"][article["id"]] = dict(article)


def set_retention_days(valeur: int | None) -> None:
    global _retention_days
    _retention_days = valeur


def get_retention_days() -> int | None:
    return _retention_days


def lister_ids_collection(nom: str) -> list[str]:
    return list(_collections.get(nom, {}).keys())


def lister_articles(category: str | None = None) -> list[dict]:
    articles = list(_collections["articles"].values())

    if _retention_days and _retention_days > 0:
        seuil = datetime.now(tz=timezone.utc) - timedelta(days=_retention_days)
        articles = [a for a in articles if a.get("collected_at") and a["collected_at"] >= seuil]

    if category is not None:
        articles = [a for a in articles if a.get("category") == category]

    # Tri stable par id pour des résultats déterministes.
    articles.sort(key=lambda a: a["id"])
    return articles


def executer_collector() -> None:
    """Simule la fin d'exécution du collector : aucune suppression."""
    # Conformément à la spec v2 : le collector ne supprime plus rien.
    return None
