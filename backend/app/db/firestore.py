from google.cloud import firestore
from app.config import settings

_db: firestore.Client | None = None


def get_db() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(project=settings.firestore_project_id)
    return _db
