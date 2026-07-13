import asyncio
import json
import logging
import time
logger = logging.getLogger(__name__)

from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from app.auth.google_oauth import require_admin
from app.db.firestore import get_db
from app.models.article import Article, ArticleList
from app.services.article_summarizer import (
    fetch_article_text,
    get_model_priority,
    _sync_call_llm_with_progress,
    PROMPT_VERSION,
)

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
    ids: str | None = Query(None),
):
    db = get_db()

    # Récupération par IDs explicites — sans filtre de rétention (favoris anciens)
    if ids:
        id_list = [i.strip() for i in ids.split(",") if i.strip()][:200]
        items = []
        for article_id in id_list:
            doc = db.collection("articles").document(article_id).get()
            if doc.exists:
                data = doc.to_dict()
                items.append(Article(**{**data, "id": doc.id}))
        items.sort(key=lambda a: a.published_at or "", reverse=True)
        return ArticleList(items=items)

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


@router.post("/{article_id}/summary")
async def article_summary(
    article_id: str,
    current_user: dict = Depends(require_admin),
):
    """Génère (ou restitue) un résumé long-form en streaming SSE.

    Événements émis :
      {"type": "progress", "message": "..."}  — étape en cours
      {"type": "result",   "data": {...}}      — résumé prêt
      {"type": "error",    "message": "...", "status": N}
    """
    identifier = current_user.get("email", "admin")
    return StreamingResponse(
        _summary_event_stream(article_id, identifier),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _summary_event_stream(article_id: str, identifier: str):
    """Générateur async SSE pour la génération de résumé."""

    def sse(event_type: str, **kwargs) -> str:
        return f"data: {json.dumps({'type': event_type, **kwargs})}\n\n"

    db = get_db()

    # ── Cache Firestore ────────────────────────────────────────────────────────
    yield sse("progress", message="Recherche en base…")
    summary_ref = db.collection("article_summaries").document(article_id)
    summary_doc = summary_ref.get()
    if summary_doc.exists:
        cached = summary_doc.to_dict()
        if cached.get("prompt_version") == PROMPT_VERSION:
            yield sse("progress", message="Résumé trouvé en base — restitution immédiate.")
            yield sse("result", data={**cached, "cached": True})
            return
        yield sse("progress", message="Résumé obsolète — régénération avec le nouveau format…")

    # ── Récupération de l'article ──────────────────────────────────────────────
    article_doc = db.collection("articles").document(article_id).get()
    if not article_doc.exists:
        yield sse("error", message="Article introuvable", status=404)
        return
    article_url = article_doc.to_dict().get("article_url", "")

    # ── Scraping ───────────────────────────────────────────────────────────────
    yield sse("progress", message="Extraction de l'article source en cours…")
    try:
        text = await fetch_article_text(article_url)
    except httpx.TimeoutException:
        yield sse("error", message="L'article source n'a pas répondu dans les délais.", status=504)
        return
    except httpx.HTTPStatusError as exc:
        yield sse("error", message=f"L'article source n'est pas accessible ({exc.response.status_code}).", status=502)
        return
    except Exception as exc:
        logger.error(f"Erreur scraping {article_url} : {exc}")
        yield sse("error", message="L'article source n'est pas accessible.", status=502)
        return

    # ── LLM avec progression ───────────────────────────────────────────────────
    model_priority = get_model_priority(db)
    loop = asyncio.get_running_loop()
    progress_queue: asyncio.Queue = asyncio.Queue()

    def send_progress(msg: str) -> None:
        loop.call_soon_threadsafe(progress_queue.put_nowait, msg)

    llm_task = asyncio.create_task(
        asyncio.to_thread(_sync_call_llm_with_progress, text, model_priority, send_progress)
    )

    # Drain la queue de progression pendant que le thread tourne
    while not llm_task.done():
        await asyncio.sleep(0.15)
        while not progress_queue.empty():
            yield sse("progress", message=progress_queue.get_nowait())

    # Vider les messages restants émis juste avant la fin du thread
    while not progress_queue.empty():
        yield sse("progress", message=progress_queue.get_nowait())

    try:
        summary_fr, summary_en, model_used = llm_task.result()
    except Exception as exc:
        logger.error(f"Résumé LLM échoué pour {article_id} : {exc}")
        yield sse("error", message="Résumé indisponible — quota LLM dépassé. Réessayez plus tard.", status=503)
        return

    # ── Persistance ────────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    doc_data = {
        "article_id": article_id,
        "article_url": article_url,
        "summary_fr": summary_fr,
        "summary_en": summary_en,
        "model_used": model_used,
        "generated_at": now,
        "word_count_fr": len(summary_fr.split()),
        "word_count_en": len(summary_en.split()),
        "prompt_version": PROMPT_VERSION,
    }
    summary_ref.set(doc_data)

    # Stats fire-and-forget
    asyncio.create_task(_log_summary_stat(identifier))

    yield sse("result", data={**doc_data, "cached": False})


async def _log_summary_stat(identifier: str) -> None:
    """Incrémente le compteur de résumés dans api_stats (non-bloquant)."""
    try:
        today = date.today().isoformat()
        db = get_db()
        ref = db.collection("api_stats").document(today)
        doc = ref.get()
        counts = doc.to_dict() if doc.exists else {}
        key = f"summary:{identifier}"
        counts[key] = counts.get(key, 0) + 1
        ref.set(counts)
    except Exception as exc:
        logger.debug(f"Stats résumé ignorées : {exc}")
