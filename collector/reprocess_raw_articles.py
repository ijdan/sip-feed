"""
Ré-enrichit via Gemini (FR+EN) les articles sauvegardés en fallback brut
(ex. suite à un dépassement de quota LLM), sans les re-scraper.

Un article est considéré "brut" (non reformulé) s'il n'a ni keywords_fr
ni keywords_en — signature laissée par `save_raw_articles()` dans
processors/gemini_processor.py, qui ne remplit jamais ces champs.

Usage : python reprocess_raw_articles.py [--date YYYY-MM-DD] [--batch-size 15] [--dry-run]
Sans --date, retraite les articles collectés la veille (UTC).
"""
import os
import argparse
import logging
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ.get("FIRESTORE_PROJECT_ID", "tech-news-aggregator-001"))

from google.cloud import firestore
from processors.gemini_processor import enrich_articles_batch, DEFAULT_MODEL_PRIORITY

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger(__name__)

ENRICHED_FIELDS = [
    "title_fr", "title_en", "title",
    "short_description_fr", "short_description_en", "short_description",
    "long_description_fr", "long_description_en", "long_description",
    "keywords_fr", "keywords_en", "category",
]


def get_llm_settings(db: firestore.Client) -> tuple[list[str], bool]:
    """Réplique la logique de main.py::get_global_settings pour rester cohérent avec un run normal."""
    doc = db.collection("settings").document("global").get()
    data = doc.to_dict() if doc.exists else {}
    stored = [m for m in data.get("model_priority", []) if m in DEFAULT_MODEL_PRIORITY]
    for model in reversed(DEFAULT_MODEL_PRIORITY):
        if model not in stored:
            stored.insert(0, model)
    thinking_enabled = data.get("thinking_enabled", True)
    return stored, thinking_enabled


def find_raw_articles(db: firestore.Client, day: str) -> list[firestore.DocumentSnapshot]:
    """Articles collectés le jour `day` (YYYY-MM-DD, UTC) et jamais enrichis par le LLM."""
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


def reprocess(day: str, batch_size: int, dry_run: bool) -> None:
    db = firestore.Client(project=os.environ.get("FIRESTORE_PROJECT_ID", "tech-news-aggregator-001"))
    model_priority, thinking_enabled = get_llm_settings(db)

    raw_docs = find_raw_articles(db, day)
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
            updates = {field: result[field] for field in ENRICHED_FIELDS}
            firestore_batch.update(doc.reference, updates)
            logger.info(f"  ✓ {result['title_fr'][:60]}")
        firestore_batch.commit()
        updated += len(chunk)

    logger.info(f"Terminé — {updated} article(s) ré-enrichi(s), {errors} en échec.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="Jour à retraiter, YYYY-MM-DD (UTC). Défaut : hier.")
    parser.add_argument("--batch-size", type=int, default=15)
    parser.add_argument("--dry-run", action="store_true", help="N'écrit rien, liste seulement les articles concernés.")
    args = parser.parse_args()

    day = args.date or (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    reprocess(day, args.batch_size, args.dry_run)
