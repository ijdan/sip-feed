"""
Migration des articles existants vers le format bilingue.
Génère les versions anglaises pour les articles qui n'en ont pas encore.
Usage : python migrate_bilingual.py [--batch-size 20] [--dry-run]
"""
import os
import sys
import json
import logging
import argparse
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", os.environ.get("FIRESTORE_PROJECT_ID", "tech-news-aggregator-001"))

import google.generativeai as genai
from google.cloud import firestore

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger(__name__)

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

TRANSLATION_PROMPT = """
Tu es journaliste tech anglophone (style WSJ / TechCrunch).
Pour chaque article ci-dessous (rédigé en français), produis une version anglaise de qualité journalistique.

Règles :
- Conserve les noms propres, acronymes et sigles techniques en VO (OpenAI, AWS, GPT, etc.)
- Style concis, percutant, adapté à un public tech anglophone
- N'invente aucun fait

Pour chaque article, produis exactement :
- "title_en" (max 12 mots) : titre journalistique en anglais
- "short_description_en" (1 phrase ~25 mots) : accroche en anglais
- "long_description_en" (4 à 6 phrases) : analyse enrichie en anglais

Articles à traiter :
{articles}

Réponds avec un tableau JSON de {count} objets dans le même ordre.
"""

GENERATION_CONFIG = {
    "temperature": 0.4,
    "max_output_tokens": 60000,
    "response_mime_type": "application/json",
}

MODEL_PRIORITY = [
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
]


def call_llm(prompt: str) -> str:
    for model_name in MODEL_PRIORITY:
        try:
            m = genai.GenerativeModel(model_name, generation_config=GENERATION_CONFIG)
            response = m.generate_content(prompt)
            logger.info(f"  Modèle : {model_name}")
            return response.text.strip()
        except Exception as e:
            logger.warning(f"  {model_name} indisponible : {e.__class__.__name__}")
    raise RuntimeError("Aucun modèle disponible")


def migrate(batch_size: int = 20, dry_run: bool = False):
    db = firestore.Client(project=os.environ.get("FIRESTORE_PROJECT_ID", "tech-news-aggregator-001"))

    # Récupère les articles sans version anglaise
    all_docs = list(db.collection("articles").stream())
    to_migrate = [
        doc for doc in all_docs
        if not doc.to_dict().get("title_en")
    ]

    logger.info(f"Articles sans version anglaise : {len(to_migrate)} / {len(all_docs)}")
    if dry_run:
        logger.info("Mode dry-run — aucune modification.")
        return

    migrated = 0
    errors = 0

    for i in range(0, len(to_migrate), batch_size):
        batch_docs = to_migrate[i: i + batch_size]
        logger.info(f"\nBatch {i // batch_size + 1} — {len(batch_docs)} article(s)...")

        articles_text = ""
        for j, doc in enumerate(batch_docs):
            d = doc.to_dict()
            articles_text += (
                f"[{j}]\n"
                f"TITRE_FR: {d.get('title_fr') or d.get('title', '')}\n"
                f"CONTENU_FR: {d.get('long_description_fr') or d.get('long_description', '')[:1000]}\n\n"
            )

        prompt = TRANSLATION_PROMPT.format(
            articles=articles_text,
            count=len(batch_docs),
        )

        try:
            text = call_llm(prompt)
            results = json.loads(text)

            firestore_batch = db.batch()
            for j, doc in enumerate(batch_docs):
                r = results[j] if j < len(results) else {}
                if r.get("title_en"):
                    firestore_batch.update(doc.reference, {
                        "title_en": r.get("title_en", ""),
                        "short_description_en": r.get("short_description_en", ""),
                        "long_description_en": r.get("long_description_en", ""),
                    })
                    logger.info(f"  ✓ {r['title_en'][:60]}")
                    migrated += 1
            firestore_batch.commit()

        except Exception as e:
            logger.error(f"  Erreur batch : {e}")
            errors += len(batch_docs)

    logger.info(f"\nMigration terminée : {migrated} articles mis à jour, {errors} erreurs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    migrate(batch_size=args.batch_size, dry_run=args.dry_run)
