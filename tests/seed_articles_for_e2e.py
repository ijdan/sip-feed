"""Insère 30 articles factices dans l'émulateur Firestore pour les tests E2E.

Pré-requis : FIRESTORE_EMULATOR_HOST défini (ex. localhost:8080).
Lance : python tests/seed_articles_for_e2e.py
"""
import os
import sys
import time
import uuid
import traceback
from datetime import datetime, timedelta

os.environ.setdefault("GRPC_DNS_RESOLVER", "native")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "tech-news-aggregator-001")

from google.cloud import firestore

PROJECT = os.environ.get("FIRESTORE_PROJECT_ID", "tech-news-aggregator-001")
CATEGORIES = ["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"]
NB_ARTICLES = 30
NB_SOURCES = 3

EMULATOR_HOST = os.environ.get("FIRESTORE_EMULATOR_HOST")
if not EMULATOR_HOST:
    print(
        "ERREUR : FIRESTORE_EMULATOR_HOST non défini. Refus de seeder en prod.",
        file=sys.stderr,
    )
    sys.exit(1)

print(f"Cible : émulateur Firestore sur {EMULATOR_HOST}, projet {PROJECT}")

db = firestore.Client(project=PROJECT)

# Le port HTTP de l'émulateur peut répondre avant que l'API gRPC soit prête.
# On retry une écriture probe avec un backoff jusqu'à 60s avant d'abandonner.
probe_id = f"__probe_{uuid.uuid4().hex}"
probe_ref = db.collection("__probe").document(probe_id)
deadline = time.time() + 60
last_error = None
while time.time() < deadline:
    try:
        probe_ref.set({"ts": datetime.utcnow().isoformat()})
        probe_ref.delete()
        print("Émulateur Firestore opérationnel (probe write/delete OK).")
        break
    except Exception as e:
        last_error = e
        print(f"  Émulateur pas encore prêt ({type(e).__name__}: {str(e)[:80]}), retry…")
        time.sleep(2)
else:
    print(f"ERREUR : émulateur jamais devenu prêt en 60s.", file=sys.stderr)
    traceback.print_exception(type(last_error), last_error, last_error.__traceback__)
    sys.exit(1)

now = datetime.utcnow()

try:
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
except Exception as e:
    print(f"ERREUR pendant le seed : {type(e).__name__}: {e}", file=sys.stderr)
    traceback.print_exc()
    sys.exit(2)

print(f"{NB_ARTICLES} articles seedés dans l'émulateur Firestore.")
