import logging
import os
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")

from google.cloud import firestore

from scrapers.web_scraper import scrape_source
from scrapers.gmail_reader import read_gmail_source
from processors.gemini_processor import enrich_articles_batch, save_raw_articles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = firestore.Client()

MAX_ARTICLES_PER_RUN = 20


def get_global_settings() -> dict:
    doc = db.collection("settings").document("global").get()
    if doc.exists:
        return doc.to_dict()
    return {"llm_enabled": True, "translation_enabled": True}


def already_exists(url: str) -> bool:
    docs = list(db.collection("articles").where("article_url", "==", url).limit(1).stream())
    return len(docs) > 0


def run():
    global_settings = get_global_settings()
    llm_enabled = global_settings.get("llm_enabled", True)
    translation_enabled = global_settings.get("translation_enabled", True) and llm_enabled
    logger.info(f"Settings — LLM: {llm_enabled}, Traduction FR: {translation_enabled}")

    all_sources = [doc for doc in db.collection("sources").where("active", "==", True).stream()]
    # Gmail en premier pour que les newsletters aient la priorité sur l'attribution
    sources = sorted(all_sources, key=lambda d: 0 if d.to_dict().get("type") == "gmail" else 1)
    logger.info(f"{len(sources)} source(s) active(s) trouvée(s)")

    # Étape 1 : collecte brute depuis toutes les sources
    all_raw = []
    seen_urls = set()  # déduplication en mémoire + DB

    for doc in sources:
        source = doc.to_dict()
        source["id"] = doc.id
        logger.info(f"Scraping source : {source['name']} ({source['type']})")

        try:
            if source["type"] == "web":
                raw_articles = scrape_source(source)
            elif source["type"] == "gmail":
                raw_articles = read_gmail_source(source)
            else:
                continue

            for raw in raw_articles:
                if len(all_raw) >= MAX_ARTICLES_PER_RUN:
                    break
                url = raw["article_url"]
                if url in seen_urls or already_exists(url):
                    logger.info(f"  Déjà collecté, ignoré : {raw['title'][:60]}")
                    continue
                seen_urls.add(url)
                all_raw.append(raw)
                logger.info(f"  Nouveau : {raw['title'][:60]}")

        except Exception as e:
            logger.error(f"Erreur scraping {source['name']}: {e}")

    if not all_raw:
        logger.info("Aucun nouvel article à traiter.")
        return

    # Étape 2 : traitement LLM ou brut selon settings
    if llm_enabled:
        logger.info(f"Envoi de {len(all_raw)} article(s) à Gemini (traduction FR: {translation_enabled})...")
        try:
            enriched_articles = enrich_articles_batch(all_raw, translate=translation_enabled)
        except Exception as e:
            logger.error(f"Erreur Gemini : {e}")
            return
    else:
        logger.info("LLM désactivé — sauvegarde des articles bruts.")
        enriched_articles = save_raw_articles(all_raw)

    # Étape 3 : sauvegarde dans Firestore
    for article in enriched_articles:
        db.collection("articles").document(article["id"]).set(article)
        logger.info(f"  Sauvegardé : {article['title'][:60]}")

    logger.info(f"Collecte terminée — {len(enriched_articles)} article(s) ajouté(s).")


if __name__ == "__main__":
    run()
