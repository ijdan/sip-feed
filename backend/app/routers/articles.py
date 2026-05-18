import logging
import time
logger = logging.getLogger(__name__)

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from google.cloud.firestore_v1.aggregation import AggregationQuery
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


def _count_query(query) -> int:
    """Compte les documents d'une requête Firestore via aggregation (sans les charger)."""
    try:
        result = query.count().get()
        return result[0][0].value
    except Exception:
        # Fallback si count() non supporté (émulateur ancien)
        return len(list(query.stream()))


@router.get("/")
def list_articles(
    category: str | None = Query(None),
    source_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    db = get_db()
    query = db.collection("articles").order_by("published_at", direction="DESCENDING")

    if category:
        query = query.where("category", "==", category)
    if source_id:
        query = query.where("source_id", "==", source_id)

    retention_days = _get_retention_days()

    if retention_days <= 0:
        # C1 : total via aggregation (pas de chargement en mémoire)
        total = _count_query(query)
        start = (page - 1) * page_size
        page_docs = list(query.offset(start).limit(page_size).stream())
        items = [Article(**{**doc.to_dict(), "id": doc.id}) for doc in page_docs]
    else:
        # Filtrage par fenêtre de rétention en mémoire — Firestore ne permet pas
        # un where("collected_at",...) combiné à order_by("published_at").
        all_docs = list(query.stream())
        kept = [doc for doc in all_docs if _est_dans_fenetre(doc.to_dict(), retention_days)]
        total = len(kept)
        start = (page - 1) * page_size
        page_docs = kept[start:start + page_size]
        items = [Article(**{**doc.to_dict(), "id": doc.id}) for doc in page_docs]

    return ArticleList(items=items, total=total, page=page, page_size=page_size)


@router.get("/{article_id}", response_model=Article)
def get_article(article_id: str):
    db = get_db()
    doc = db.collection("articles").document(article_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Article introuvable")
    return Article(**{**doc.to_dict(), "id": doc.id})
