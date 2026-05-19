import logging
import time
logger = logging.getLogger(__name__)

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from app.db.firestore import get_db
from app.models.article import Article, ArticleList

router = APIRouter()

CATEGORIES = ["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"]

_retention_cache: dict = {"value": 0, "expires": 0.0}
_RETENTION_TTL = 300  # 5 minutes


def _get_retention_days() -> int:
    """Lit retention_days depuis settings/global, mis en cache 5 min."""
    now = time.monotonic()
    if now < _retention_cache["expires"]:
        return _retention_cache["value"]
    value = 0
    try:
        doc = get_db().collection("settings").document("global").get()
        if doc.exists:
            value = int(doc.to_dict().get("retention_days", 0) or 0)
    except Exception as e:
        logger.warning(f"Impossible de lire retention_days : {e}")
    _retention_cache["value"] = value
    _retention_cache["expires"] = now + _RETENTION_TTL
    return value


def _est_dans_fenetre(data: dict, retention_days: int) -> bool:
    """Vrai si l'article est dans la fenêtre de rétention (illimité si <= 0)."""
    if retention_days <= 0:
        return True
    collected_at = data.get("collected_at")
    if not collected_at:
        return True
    try:
        if isinstance(collected_at, str):
            collected_at = datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
        if collected_at.tzinfo is None:
            collected_at = collected_at.replace(tzinfo=timezone.utc)
    except Exception:
        return True
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=retention_days)
    return collected_at >= cutoff


@router.get("/stats")
def articles_stats():
    db = get_db()
    all_docs = list(db.collection("articles").stream())
    total = len(all_docs)
    counts = {cat: 0 for cat in CATEGORIES}
    for doc in all_docs:
        cat = doc.to_dict().get("category", "Autre")
        if cat in counts:
            counts[cat] += 1
        else:
            counts["Autre"] += 1
    return {"total": total, "by_category": counts}


@router.get("/")
def list_articles(
    category: str | None = Query(None),
    source_id: str | None = Query(None),
):
    db = get_db()
    query = db.collection("articles").order_by("published_at", direction="DESCENDING")

    if category:
        query = query.where("category", "==", category)
    if source_id:
        query = query.where("source_id", "==", source_id)

    retention_days = _get_retention_days()
    items = []
    for doc in query.stream():
        data = doc.to_dict()
        if retention_days > 0 and not _est_dans_fenetre(data, retention_days):
            continue
        items.append(Article(**{**data, "id": doc.id}))

    return ArticleList(items=items)


@router.get("/{article_id}", response_model=Article)
def get_article(article_id: str):
    db = get_db()
    doc = db.collection("articles").document(article_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Article introuvable")
    return Article(**{**doc.to_dict(), "id": doc.id})
