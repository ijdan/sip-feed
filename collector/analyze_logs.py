"""Point d'entrée du Cloud Run Job log-analyzer.

Exécuté chaque nuit à 05h00 CET par Cloud Scheduler.
Réutilise l'image Docker du collector (même dépendances Dockerfile).
"""
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from google.cloud import firestore
from processors.gemini_processor import DEFAULT_MODEL_PRIORITY
from processors.log_analyzer import run_log_analysis


def main():
    project_id = os.environ.get("FIRESTORE_PROJECT_ID", "tech-news-aggregator-001")
    db = firestore.Client(project=project_id)

    settings_doc = db.collection("settings").document("global").get()
    model_priority = DEFAULT_MODEL_PRIORITY
    if settings_doc.exists:
        stored = settings_doc.to_dict().get("model_priority", [])
        if stored:
            model_priority = stored

    result = run_log_analysis(db, model_priority=model_priority)
    logging.info(
        "Analyse terminée : %d items — %s",
        len(result.get("items", [])),
        result.get("resume", "")[:80],
    )


if __name__ == "__main__":
    main()
