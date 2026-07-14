"""
Reformule via Gemini (FR+EN) les articles sauvegardés en fallback brut
(ex. suite à un dépassement de quota Gemini), à partir du résumé déjà
en base — sans re-scraper les sources.

Un article est "brut" s'il n'a ni keywords_fr ni keywords_en, signature
laissée par save_raw_articles() (processors/gemini_processor.py) quand
tous les modèles LLM ont échoué lors de la collecte initiale.

Usage : python refresh_summaries.py 2026-07-14 [--batch-size 20] [--dry-run]
"""
import argparse
import logging
from datetime import datetime, timedelta

from main import db, get_global_settings
from processors.gemini_processor import enrich_articles_batch

logger = logging.getLogger(__name__)

ENRICHED_FIELDS = [
    "title_fr", "title_en", "title",
    "short_description_fr", "short_description_en", "short_description",
    "long_description_fr", "long_description_en", "long_description",
    "keywords_fr", "keywords_en", "category",
]


def find_raw_articles(day: str) -> list:
    """Articles collectés le `day` (YYYY-MM-DD, UTC) et jamais reformulés par le LLM."""
    start = f"{day}T00:00:00"
    end_date = (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    end = f"{end_date}T00:00:00"

    docs = list(
        db.collection("articles")
        .where("collected_at", ">=", start)
        .where("collected_at", "<", end)
        .stream()
    )
    return [
        doc for doc in docs
        if not doc.to_dict().get("keywords_fr") and not doc.to_dict().get("keywords_en")
    ]


def refresh(day: str, batch_size: int, dry_run: bool) -> None:
    settings = get_global_settings()
    if not settings.get("llm_enabled", True):
        logger.info("LLM désactivé dans les settings — rien à reformuler.")
        return
    model_priority = settings["model_priority"]
    thinking_enabled = settings.get("thinking_enabled", True)

    raw_docs = find_raw_articles(day)
    logger.info(f"{len(raw_docs)} article(s) brut(s) trouvé(s) pour le {day} (modèles : {model_priority}).")
    if not raw_docs:
        return

    if dry_run:
        for doc in raw_docs:
            d = doc.to_dict()
            logger.info(f"  [dry-run] {d.get('title', '')[:60]} — {d.get('article_url', '')}")
        return

    updated = 0
    errors = 0

    for i in range(0, len(raw_docs), batch_size):
        chunk = raw_docs[i:i + batch_size]
        logger.info(f"Lot {i // batch_size + 1} — {len(chunk)} article(s)...")

        raw_articles = [
            {
                "title": (d := doc.to_dict()).get("title", ""),
                "raw_content": d.get("long_description", ""),
                "article_url": d.get("article_url", ""),
                "source_name": d.get("source_name", ""),
                "source_id": d.get("source_id", ""),
                "published_at": d.get("published_at", ""),
            }
            for doc in chunk
        ]

        try:
            enriched = enrich_articles_batch(raw_articles, model_priority=model_priority, thinking=thinking_enabled)
        except Exception as e:
            logger.error(f"  Échec du lot ({e.__class__.__name__}) — articles laissés bruts, à retenter plus tard.")
            errors += len(chunk)
            continue

        firestore_batch = db.batch()
        for doc, result in zip(chunk, enriched):
            firestore_batch.update(doc.reference, {field: result[field] for field in ENRICHED_FIELDS})
            logger.info(f"  ✓ {result['title_fr'][:60]}")
        firestore_batch.commit()
        updated += len(chunk)

    logger.info(f"Terminé — {updated} article(s) reformulé(s), {errors} en échec.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("date", help="Jour à retraiter, YYYY-MM-DD (UTC).")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true", help="N'écrit rien, liste seulement les articles concernés.")
    args = parser.parse_args()

    refresh(args.date, args.batch_size, args.dry_run)
