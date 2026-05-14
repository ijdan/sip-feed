import logging
logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
import uuid

from app.auth.google_oauth import verify_jwt, require_admin
from app.db.firestore import get_db
from app.models.source import Source, SourceCreate

router = APIRouter()


@router.get("/", response_model=list[Source])
def list_sources(current_user: dict = Depends(verify_jwt)):
    db = get_db()
    docs = db.collection("sources").stream()
    return [Source(**{**doc.to_dict(), "id": doc.id}) for doc in docs]


@router.post("/", response_model=Source)
def create_source(payload: SourceCreate, current_user: dict = Depends(require_admin)):
    if payload.type == "web" and not payload.url:
        raise HTTPException(status_code=400, detail="URL requise pour une source web")
    if payload.type == "gmail" and not payload.gmail_sender:
        raise HTTPException(status_code=400, detail="gmail_sender requis pour une source Gmail")

    db = get_db()
    source_id = str(uuid.uuid4())
    data = {
        **payload.model_dump(),
        "id": source_id,
        "created_by": current_user["sub"],
        "created_at": datetime.utcnow().isoformat(),
    }
    db.collection("sources").document(source_id).set(data)
    return Source(**data)


@router.put("/{source_id}", response_model=Source)
def update_source(source_id: str, payload: SourceCreate, current_user: dict = Depends(require_admin)):
    db = get_db()
    ref = db.collection("sources").document(source_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Source introuvable")
    ref.update(payload.model_dump())
    doc = ref.get().to_dict()
    return Source(**{**doc, "id": source_id})


@router.patch("/{source_id}/toggle", response_model=Source)
def toggle_source(source_id: str, current_user: dict = Depends(require_admin)):
    db = get_db()
    ref = db.collection("sources").document(source_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Source introuvable")
    current_active = doc.to_dict().get("active", True)
    ref.update({"active": not current_active})
    return Source(**{**doc.to_dict(), "id": source_id, "active": not current_active})


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: str, current_user: dict = Depends(require_admin)):
    db = get_db()
    ref = db.collection("sources").document(source_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="Source introuvable")
    ref.delete()
