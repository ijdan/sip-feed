"""
Recharge les feeds d'une journée donnée : purge les articles déjà
sauvegardés ce jour-là, puis relance le traitement de collecte actuel
(scraping + enrichissement Gemini bilingue), via main.run().

Utile quand une exécution précédente a été dégradée (ex. quota Gemini
dépassé → articles sauvegardés bruts par save_raw_articles) : la purge
supprime les articles concernés, main.run() ne les trouvera donc plus
via already_exists() et les recollectera normalement.

Usage : python refresh_feeds.py 2026-07-14 [--dry-run]
"""
import argparse
import logging
from datetime import datetime, timedelta

from main import db, run

logger = logging.getLogger(__name__)


def purge_day(day: str, dry_run: bool = False) -> int:
    """Supprime (ou compte, en dry-run) les articles dont collected_at tombe le `day` (YYYY-MM-DD, UTC)."""
    start = f"{day}T00:00:00"
    end_date = (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    end = f"{end_date}T00:00:00"

    docs = list(
        db.collection("articles")
        .where("collected_at", ">=", start)
        .where("collected_at", "<", end)
        .stream()
    )

    if dry_run:
        return len(docs)

    batch = db.batch()
    for i, doc in enumerate(docs):
        batch.delete(doc.reference)
        if (i + 1) % 500 == 0:
            batch.commit()
            batch = db.batch()
    batch.commit()
    return len(docs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("date", help="Jour à recharger, YYYY-MM-DD (UTC).")
    parser.add_argument("--dry-run", action="store_true", help="N'écrit rien, affiche seulement le nombre d'articles concernés.")
    args = parser.parse_args()

    count = purge_day(args.date, dry_run=args.dry_run)
    if args.dry_run:
        logger.info(f"[dry-run] {count} article(s) du {args.date} seraient purgés — traitement non relancé.")
    else:
        logger.info(f"{count} article(s) du {args.date} purgé(s).")
        run()
