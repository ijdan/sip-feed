"""Service applicatif du filtrage par rétention.

Sert d'adaptateur entre les tests d'acceptance et la logique métier
implémentée en production (backend/app/routers/articles.py et collector/main.py).
Un mini-store en mémoire reproduit le comportement Firestore pour les tests.
"""
from datetime import datetime, timezone

_articles: list[dict] = []
_retention_days: int | None = None


def set_articles(articles: list[dict]) -> None:
    """Remplace les articles du store en mémoire."""
    global _articles
    _articles = [dict(a) for a in articles]


def set_retention_days(valeur: int | None) -> None:
    """Définit la valeur de rétention (0 ou None = illimité)."""
    global _retention_days
    _retention_days = valeur


def get_retention_days() -> int | None:
    return _retention_days


def _est_dans_fenetre(article: dict) -> bool:
    """Vrai si l'article est dans la fenêtre de rétention courante."""
    if not _retention_days or _retention_days <= 0:
        return True
    collected_at = article.get("collected_at")
    if collected_at is None:
        return True
    if isinstance(collected_at, str):
        collected_at = datetime.fromisoformat(collected_at)
    now = datetime.now(tz=timezone.utc)
    if collected_at.tzinfo is None:
        collected_at = collected_at.replace(tzinfo=timezone.utc)
    age_jours = (now - collected_at).total_seconds() / 86400
    return age_jours <= _retention_days


def lister_articles_filtres(category: str | None = None) -> list[dict]:
    """Retourne les articles filtrés par fenêtre de rétention puis par catégorie."""
    resultats = [a for a in _articles if _est_dans_fenetre(a)]
    if category:
        resultats = [a for a in resultats if a.get("category") == category]
    return resultats


def lister_ids_collection(collection: str) -> list[str]:
    """Retourne tous les IDs présents dans la "collection" Firestore simulée.

    Aucun filtre de rétention : les articles hors fenêtre doivent rester
    présents dans le stockage (cf. scénario "restent présents dans Firestore").
    """
    if collection != "articles":
        return []
    return [a["id"] for a in _articles]


def executer_collector() -> None:
    """Simule la fin d'un run du collector.

    En production, le collector ne supprime plus les articles anciens
    (cf. collector/main.py — apply_retention est un no-op). Cette fonction
    est donc volontairement vide : le store n'est pas modifié.
    """
    return None
