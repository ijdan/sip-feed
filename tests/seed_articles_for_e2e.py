"""Insère 30 articles factices dans l'émulateur Firestore pour les tests E2E.

Pré-requis : FIRESTORE_EMULATOR_HOST défini (ex. localhost:8080).
Lance : python tests/seed_articles_for_e2e.py
"""
import os
import sys
import uuid
from datetime import datetime, timedelta

os.environ.setdefault("GRPC_DNS_RESOLVER", "native")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "tech-news-aggregator-001")

from google.cloud import firestore

PROJECT = os.environ.get("FIRESTORE_PROJECT_ID", "tech-news-aggregator-001")
CATEGORIES = ["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"]
NB_ARTICLES = 30
NB_SOURCES = 3

if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
    print(
        "ERREUR : FIRESTORE_EMULATOR_HOST non défini. Refus de seeder en prod.",
        file=sys.stderr,
    )
    sys.exit(1)

db = firestore.Client(project=PROJECT)
now = datetime.utcnow()

for i in range(NB_ARTICLES):
    cat = CATEGORIES[i % len(CATEGORIES)]
    src_idx = i % NB_SOURCES
    article_id = str(uuid.uuid4())
    db.collection("articles").document(article_id).set({
        "id": article_id,
        "title": f"Article de test {i}",
        "title_fr": f"Article de test FR {i}",
        "title_en": f"Test article EN {i}",
        "short_description": f"Description courte de l'article {i}.",
        "short_description_fr": f"Description courte FR de l'article {i}.",
        "short_description_en": f"Short EN description of article {i}.",
        "long_description": f"Description longue de l'article {i}.",
        "long_description_fr": f"Description longue FR de l'article {i}.",
        "long_description_en": f"Long EN description of article {i}.",
        "keywords_fr": [cat, f"mot-cle-{i}"],
        "keywords_en": [cat, f"keyword-{i}"],
        "article_url": f"https://example.com/test-{i}",
        "source_name": f"Source de test {src_idx}",
        "source_id": f"test-source-{src_idx}",
        "category": cat,
        "published_at": (now - timedelta(hours=i)).isoformat(),
        "collected_at": (now - timedelta(hours=i)).isoformat(),
    })

print(f"{NB_ARTICLES} articles seedés dans l'émulateur Firestore.")
