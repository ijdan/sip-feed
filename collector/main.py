import logging
import os
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")
# Requis par google-auth pour éviter le warning "No project ID could be determined"
_project = os.environ.get("FIRESTORE_PROJECT_ID", "tech-news-aggregator-001")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", _project)

from google.cloud import firestore

from scrapers.web_scraper import scrape_source
from scrapers.gmail_reader import read_gmail_source
from processors.gemini_processor import enrich_articles_batch, save_raw_articles, generate_run_report, generate_synthesis

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
    """Supprime les articles plus anciens que retention_days. Retourne le nombre supprimé."""
    if retention_days <= 0:
        return 0
    from datetime import datetime as _dt, timedelta
    cutoff = (_dt.utcnow() - timedelta(days=retention_days)).isoformat()
    docs = list(db.collection("articles").where("collected_at", "<", cutoff).stream())
    if not docs:
        return 0
    batch = db.batch()
    for i, doc in enumerate(docs):
        batch.delete(doc.reference)
        if (i + 1) % 500 == 0:
            batch.commit()
            batch = db.batch()
    batch.commit()
    logger.info(f"Rétention : {len(docs)} article(s) supprimé(s) (plus anciens que {retention_days}j)")
    return len(docs)


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
    all_raw = []
    seen_urls = set()  # déduplication en mémoire + DB

    for doc in sources:
        source = doc.to_dict()
        source["id"] = doc.id
        logger.info(f"Scraping source : {source['name']} ({source['type']})")

        try:
            if source["type"] == "web":
                raw_articles = scrape_source(source)
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

            elif source["type"] == "gmail":
                raw_articles = read_gmail_source(source, lookback_days=gmail_lookback_days)
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
            logger.error(f"Erreur source {source['name']}: {e}")

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
        logger.info(f"Génération de la synthèse pour : «{interest}»...")
        all_articles = list(db.collection("articles").order_by("collected_at", direction="DESCENDING").limit(100).stream())
        articles_for_synthesis = [doc.to_dict() for doc in all_articles]
        synthesis = generate_synthesis(articles_for_synthesis, interest, model_priority)
        from datetime import date as _date
        db.collection("syntheses").document(_date.today().isoformat()).set({
            "interest": interest,
            "content": synthesis,
            "articles_count": len(articles_for_synthesis),
            "generated_at": datetime.utcnow().isoformat(),
        })
        logger.info("Synthèse sauvegardée.")

    # Rapport de synthèse via LLM — toujours généré
    run_logs = "\n".join(_mem_handler.records)
    report = generate_run_report(run_logs, model_priority)

    # Persistance du rapport dans Firestore
    from datetime import datetime as _dt
    db.collection("reports").document("latest").set({
        "content": report,
        "generated_at": _dt.utcnow().isoformat(),
    })
    logger.info("📋 Rapport d'exécution généré et sauvegardé.")


if __name__ == "__main__":
    run()
