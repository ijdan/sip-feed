"""
Migration des articles existants : ajout des mots-clés FR + EN en un seul appel Gemini.
Usage : python migrate_keywords.py [--dry-run] [--batch-size 404]
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

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

MODEL_PRIORITY = [
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
]

GENERATION_CONFIG = {
    "temperature": 0.3,
    "max_output_tokens": 65536,
    "response_mime_type": "application/json",
}

BATCH_SIZE = 150  # ~20K tokens de sortie par batch, bien sous la limite

PROMPT_TEMPLATE = """
Tu es un expert en classification de contenu tech.
Pour chaque article ci-dessous, extrais entre 10 et 15 mots-clés du domaine du logiciel et de la technologie.

Règles strictes :
- Mots simples ou expressions courtes (1 à 3 mots maximum)
- Domaine exclusif : logiciel, technologie, informatique, numérique
- Privilégier : langages, frameworks, protocoles, plateformes, entreprises tech, concepts informatiques, acronymes
- Exclure : mots génériques non techniques (ex: "annonce", "nouveau", "impact", "résultat")
- Les termes identiques en VO (OpenAI, AWS, Rust) apparaissent dans les deux listes tels quels

Articles à traiter ({count} articles) :
{articles}

Réponds UNIQUEMENT avec un tableau JSON valide, dans le même ordre que les articles :
[
  {{
    "id": "identifiant_article",
    "keywords_fr": ["mot1", "mot2", ...],
    "keywords_en": ["word1", "word2", ...]
  }}
]
"""


def call_llm(prompt: str) -> str:
    for model_name in MODEL_PRIORITY:
        try:
            logger.info(f"  Essai modèle : {model_name}")
            m = genai.GenerativeModel(model_name, generation_config=GENERATION_CONFIG)
            response = m.generate_content(prompt)
            logger.info(f"  ✓ Modèle utilisé : {model_name}")
            return response.text.strip()
        except Exception as e:
            logger.warning(f"  {model_name} indisponible : {e.__class__.__name__}")
    raise RuntimeError("Aucun modèle disponible")


def migrate(dry_run: bool = False):
    db = firestore.Client(project=os.environ.get("FIRESTORE_PROJECT_ID", "tech-news-aggregator-001"))

    # Récupère les articles sans mots-clés
    all_docs = list(db.collection("articles").stream())
    to_migrate = [
        doc for doc in all_docs
        if not doc.to_dict().get("keywords_fr")
    ]

    logger.info(f"Articles total : {len(all_docs)}")
    logger.info(f"Articles sans mots-clés : {len(to_migrate)}")

    if not to_migrate:
        logger.info("Rien à migrer.")
        return

    if dry_run:
        logger.info("Mode dry-run — aucune modification.")
        return

    # Traitement par batchs pour ne pas dépasser la limite de tokens de sortie
    results = []
    total_batches = (len(to_migrate) + BATCH_SIZE - 1) // BATCH_SIZE
    logger.info(f"Traitement en {total_batches} batch(s) de {BATCH_SIZE} articles max")

    for batch_num in range(total_batches):
        batch_docs = to_migrate[batch_num * BATCH_SIZE:(batch_num + 1) * BATCH_SIZE]
        logger.info(f"\nBatch {batch_num + 1}/{total_batches} — {len(batch_docs)} articles...")

        articles_text = ""
        for doc in batch_docs:
            d = doc.to_dict()
            articles_text += (
                f"ID: {doc.id}\n"
                f"TITRE: {d.get('title_fr') or d.get('title', '')}\n"
                f"CONTENU: {(d.get('long_description_fr') or d.get('long_description', ''))[:600]}\n\n"
            )

        estimated_tokens = len(articles_text) // 4
        logger.info(f"  Taille estimée : ~{estimated_tokens:,} tokens")

        prompt = PROMPT_TEMPLATE.format(
            count=len(batch_docs),
            articles=articles_text,
        )

        try:
            text = call_llm(prompt)
            batch_results = json.loads(text)
            results.extend(batch_results)
            logger.info(f"  ✓ {len(batch_results)} articles traités")
        except Exception as e:
            logger.error(f"  Échec batch {batch_num + 1} : {e}")
            logger.error("  Ce batch sera ignoré — relancez le script pour réessayer.")

    logger.info(f"\nTotal réponses reçues : {len(results)}")

    # Indexation par ID pour le mapping
    results_by_id = {r["id"]: r for r in results if r.get("id")}

    # Mise à jour Firestore par batchs de 500
    updated = 0
    missing = 0
    batch = db.batch()
    batch_count = 0

    for doc in to_migrate:
        r = results_by_id.get(doc.id)
        if not r or not r.get("keywords_fr"):
            missing += 1
            logger.warning(f"  Manquant : {doc.id[:20]} — {doc.to_dict().get('title', '')[:50]}")
            continue

        # Ajouter la catégorie en tête des mots-clés
        d = doc.to_dict()
        cat = d.get("category", "Autre")
        CATEGORY_FR_EN = {
            "IA": ("IA", "AI"), "DevOps": ("DevOps", "DevOps"), "Cloud": ("Cloud", "Cloud"),
            "Sécurité": ("Sécurité", "Security"), "Dev": ("Dev", "Dev"),
            "IT": ("IT", "IT"), "Autre": ("Autre", "Other"),
        }
        cat_fr, cat_en = CATEGORY_FR_EN.get(cat, (cat, cat))
        kw_fr = r["keywords_fr"]
        kw_en = r.get("keywords_en", [])
        if cat_fr and cat_fr not in kw_fr:
            kw_fr = [cat_fr] + kw_fr
        if cat_en and cat_en not in kw_en:
            kw_en = [cat_en] + kw_en

        batch.update(doc.reference, {
            "keywords_fr": kw_fr,
            "keywords_en": kw_en,
        })
        updated += 1
        batch_count += 1

        if batch_count >= 500:
            batch.commit()
            batch = db.batch()
            batch_count = 0

    if batch_count > 0:
        batch.commit()

    logger.info(f"\n{'='*50}")
    logger.info(f"Migration terminée : {updated} articles mis à jour, {missing} manquants.")
    if missing > 0:
        logger.info("Relancez le script pour traiter les articles manquants.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Affiche le plan sans modifier la base")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
