import logging
import os
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")

from google.cloud import firestore

from scrapers.web_scraper import scrape_source
from scrapers.gmail_reader import read_gmail_source
from processors.gemini_processor import enrich_article

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = firestore.Client()


def already_exists(url: str) -> bool:
    """Vérifie si un article avec cette URL est déjà en base."""
    docs = list(db.collection("articles").where("article_url", "==", url).limit(1).stream())
    return len(docs) > 0


def run():
    sources = [doc for doc in db.collection("sources").where("active", "==", True).stream()]
    logger.info(f"{len(sources)} source(s) active(s) trouvée(s)")

    for doc in sources:
        source = doc.to_dict()
        source["id"] = doc.id
        logger.info(f"Traitement source : {source['name']} ({source['type']})")

        try:
            if source["type"] == "web":
                raw_articles = scrape_source(source)
            elif source["type"] == "gmail":
                raw_articles = read_gmail_source(source)
            else:
                continue

            saved = 0
            for raw in raw_articles:
                if saved >= 10:
                    break
                if already_exists(raw["article_url"]):
                    logger.info(f"  Déjà collecté, ignoré : {raw['title'][:60]}")
                    continue
                article = enrich_article(raw, source)
                db.collection("articles").document(article["id"]).set(article)
                logger.info(f"  Article sauvegardé : {article['title'][:60]}")
                saved += 1

        except Exception as e:
            logger.error(f"Erreur sur la source {source['name']}: {e}")

    logger.info("Collecte terminée.")


if __name__ == "__main__":
    run()
