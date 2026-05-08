"""Supprime les articles en double (même URL), garde le plus récent."""
import os
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")

from google.cloud import firestore

db = firestore.Client(project="tech-news-aggregator-001")

all_docs = list(db.collection("articles").stream())
print(f"{len(all_docs)} articles en base")

seen = {}
to_delete = []

for doc in all_docs:
    data = doc.to_dict()
    url = data.get("article_url", "")
    collected_at = data.get("collected_at", "")

    if url not in seen:
        seen[url] = (doc.id, collected_at)
    else:
        existing_id, existing_date = seen[url]
        if collected_at >= existing_date:
            to_delete.append(existing_id)
            seen[url] = (doc.id, collected_at)
        else:
            to_delete.append(doc.id)

print(f"{len(to_delete)} doublon(s) à supprimer")
for doc_id in to_delete:
    db.collection("articles").document(doc_id).delete()
    print(f"  Supprimé : {doc_id}")

print("Done.")
