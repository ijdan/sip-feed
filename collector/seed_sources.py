"""Insère des sources de test dans Firestore."""
import uuid
from datetime import datetime
from google.cloud import firestore

db = firestore.Client(project="tech-news-aggregator-001")

sources = [
    {
        "name": "Hacker News",
        "type": "web",
        "url": "https://news.ycombinator.com",
        "active": True,
    },
    {
        "name": "The Verge Tech",
        "type": "web",
        "url": "https://www.theverge.com/tech",
        "active": True,
    },
]

for s in sources:
    source_id = str(uuid.uuid4())
    db.collection("sources").document(source_id).set({
        **s,
        "id": source_id,
        "created_by": "seed",
        "created_at": datetime.utcnow().isoformat(),
    })
    print(f"Source ajoutée : {s['name']}")

print("Done.")
