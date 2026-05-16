import logging
import os
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")
# Requis par google-auth pour éviter le warning "No project ID could be determined"
_project = os.environ.get("FIRESTORE_PROJECT_ID", "tech-news-aggregator-001")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", _project)

from google.cloud import firestore

from scrapers.web_scraper import scrape_source
from scrapers.gmail_reader import read_gmail_source
from processors.gemini_processor import (
    enrich_articles_batch, save_raw_articles, generate_run_report,
    generate_synthesis, TITLE_LOG_MAX_LENGTH,
)

# Handler pour capturer les logs en mémoire
class _MemoryHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[str] = []
    def emit(self, record):
        self.records.append(self.format(record))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
_mem_handler = _MemoryHandler()
_mem_handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
logging.getLogger().addHandler(_mem_handler)

db = firestore.Client(project=os.environ.get("FIRESTORE_PROJECT_ID", "tech-news-aggregator-001"))

MAX_ARTICLES_PER_RUN = 20


DEFAULT_MODEL_PRIORITY = ["gemini-3-flash-preview", "gemini-2.5-flash", "gemini-3.1-flash-lite", "gemma-4-31b-it", "gemma-4-26b-a4b-it", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-2.0-flash-lite"]

def get_global_settings() -> dict:
    doc = db.collection("settings").document("global").get()
    data = doc.to_dict() if doc.exists else {}
    # Filtre les modèles inconnus et ajoute les nouveaux
    stored = [m for m in data.get("model_priority", []) if m in DEFAULT_MODEL_PRIORITY]
    for model in reversed(DEFAULT_MODEL_PRIORITY):
        if model not in stored:
            stored.insert(0, model)
    data["model_priority"] = stored
    data.setdefault("llm_enabled", True)
    data.setdefault("translation_enabled", True)
    return data


def already_exists(url: str) -> bool:
    docs = list(db.collection("articles").where("article_url", "==", url).limit(1).stream())
    return len(docs) > 0


def apply_retention(retention_days: int) -> int:
    """No-op : la rétention est désormais appliquée en lecture côté API.

    Les articles anciens restent stockés dans Firestore et sont filtrés
    à la volée par backend/app/routers/articles.py selon `retention_days`.
    Cf. features/filter-articles-by-days.feature.
    """
    if retention_days > 0:
        logger.info(f"Rétention {retention_days}j appliquée en lecture (API) — aucune suppression côté collector.")
    return 0


def run():
    global_settings = get_global_settings()
    llm_enabled = global_settings.get("llm_enabled", True)
    thinking_enabled = global_settings.get("thinking_enabled", True) and llm_enabled
    model_priority = global_settings.get("model_priority", DEFAULT_MODEL_PRIORITY)
    gmail_lookback_days = global_settings.get("gmail_lookback_days", 1)
    retention_days = global_settings.get("retention_days", 0)
    interest = global_settings.get("interest", "").strip()
    logger.info(f"Settings — LLM: {llm_enabled}, Thinking: {thinking_enabled}, Modèles: {model_priority}, Gmail lookback: {gmail_lookback_days}j, Rétention: {'illimitée' if retention_days == 0 else str(retention_days) + 'j'}")

    # Si une source spécifique est demandée, ne traiter que celle-là
    specific_source_id = os.environ.get("COLLECTOR_SOURCE_ID")
    if specific_source_id:
        doc = db.collection("sources").document(specific_source_id).get()
        all_sources = [doc] if doc.exists else []
        logger.info(f"Mode source unique : {specific_source_id}")
    else:
        all_sources = [doc for doc in db.collection("sources").where("active", "==", True).stream()]

    # Gmail en premier pour que les newsletters aient la priorité sur l'attribution
    sources = sorted(all_sources, key=lambda d: 0 if d.to_dict().get("type") == "gmail" else 1)
    logger.info(f"{len(sources)} source(s) active(s) :")
    for doc in sources:
        s = doc.to_dict()
        detail = s.get("url") or s.get("gmail_sender", "")
        logger.info(f"  [{s['type'].upper()}] {s['name']} — {detail}")

    # Étape 1 : collecte brute depuis toutes les sources
    all_raw: list[dict] = []
    seen_urls: set[str] = set()

    def _add_articles_to_batch(articles: list[dict]) -> None:
        """Ajoute les articles au batch avec déduplication et logging. Modifie all_raw et seen_urls."""
        for raw in articles:
            if len(all_raw) >= MAX_ARTICLES_PER_RUN:
                break
            url = raw["article_url"]
            if url in seen_urls or already_exists(url):
                logger.info(f"  Déjà collecté, ignoré : {raw['title'][:TITLE_LOG_MAX_LENGTH]}")
                continue
            seen_urls.add(url)
            all_raw.append(raw)
            logger.info(f"  Nouveau : {raw['title'][:TITLE_LOG_MAX_LENGTH]}")

    for doc in sources:
        source = doc.to_dict()
        source["id"] = doc.id
        logger.info(f"Scraping source : {source['name']} ({source['type']})")

        try:
            if source["type"] == "web":
                _add_articles_to_batch(scrape_source(source))
            elif source["type"] == "gmail":
                _add_articles_to_batch(read_gmail_source(source, lookback_days=gmail_lookback_days))
        except ConnectionError as e:
            logger.warning(f"Erreur réseau source {source['name']} — sera retenté au prochain run : {e}")
        except TimeoutError as e:
            logger.warning(f"Timeout source {source['name']} — sera retenté au prochain run : {e}")
        except ValueError as e:
            logger.error(f"Erreur parsing source {source['name']} (données corrompues ?) : {e}")
        except Exception as e:
            logger.error(f"Erreur inattendue source {source['name']} : {type(e).__name__}: {e}")

    articles_collected = 0

    if not all_raw:
        logger.info("Aucun nouvel article à traiter — rétention non appliquée.")
    else:
        # Étape 2 : traitement LLM ou brut selon settings
        if llm_enabled:
            logger.info(f"Envoi de {len(all_raw)} article(s) à Gemini (bilingue FR+EN)...")
            try:
                enriched_articles = enrich_articles_batch(all_raw, model_priority=model_priority, thinking=thinking_enabled)
            except Exception as e:
                logger.error(f"Tous les modèles LLM ont échoué ({e.__class__.__name__}) — sauvegarde des articles bruts sans enrichissement.")
                enriched_articles = save_raw_articles(all_raw)
        else:
            logger.info("LLM désactivé — sauvegarde des articles bruts.")
            enriched_articles = save_raw_articles(all_raw)

        # Étape 3 : sauvegarde dans Firestore
        for article in enriched_articles:
            db.collection("articles").document(article["id"]).set(article)
            logger.info(f"  Sauvegardé : {article['title'][:60]}")

        articles_collected = len(enriched_articles)
        logger.info(f"Collecte terminée — {articles_collected} article(s) ajouté(s).")

        # Rétention : nettoyage des anciens articles (seulement si nouveaux articles trouvés)
        apply_retention(retention_days)

    # Synthèse centrée sur le centre d'intérêt (si renseigné)
    if interest:
        try:
            logger.info(f"Génération de la synthèse pour : «{interest}»...")
            all_articles = list(db.collection("articles").order_by("collected_at", direction="DESCENDING").limit(100).stream())
            articles_for_synthesis = [doc.to_dict() for doc in all_articles]
            result = generate_synthesis(articles_for_synthesis, interest, model_priority)
            db.collection("syntheses").document(date.today().isoformat()).set({
                "interest": interest,
                "content": result["synthesis"],
                "cited_ids": result["cited_ids"],
                "articles_count": len(articles_for_synthesis),
                "generated_at": datetime.utcnow().isoformat(),
            })
            logger.info("Synthèse sauvegardée.")
        except Exception as e:
            logger.error(f"Erreur lors de la génération de la synthèse : {e}")

    # Rapport de synthèse via LLM — toujours généré
    run_logs = "\n".join(_mem_handler.records)
    report = generate_run_report(run_logs, model_priority)

    # Persistance du rapport dans Firestore
    db.collection("reports").document("latest").set({
        "content": report,
        "generated_at": datetime.utcnow().isoformat(),
    })
    logger.info("📋 Rapport d'exécution généré et sauvegardé.")


if __name__ == "__main__":
    run()
