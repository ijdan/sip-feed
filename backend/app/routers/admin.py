import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GoogleRequest

from app.auth.google_oauth import require_admin
from app.db.firestore import get_db
from app.config import settings

router = APIRouter()

CLOUD_RUN_JOB_URL = (
    f"https://europe-west1-run.googleapis.com/apis/run.googleapis.com/v1"
    f"/namespaces/{settings.firestore_project_id}/jobs/collector:run"
)


class GlobalSettings(BaseModel):
    llm_enabled: bool = True
    translation_enabled: bool = True


def _get_access_token() -> str:
    creds, _ = google_auth_default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(GoogleRequest())
    return creds.token


@router.get("/settings", response_model=GlobalSettings)
def get_settings(_: dict = Depends(require_admin)):
    db = get_db()
    doc = db.collection("settings").document("global").get()
    if not doc.exists:
        return GlobalSettings()
    return GlobalSettings(**doc.to_dict())


@router.put("/settings", response_model=GlobalSettings)
def update_settings(payload: GlobalSettings, _: dict = Depends(require_admin)):
    db = get_db()
    db.collection("settings").document("global").set(payload.model_dump())
    return payload


@router.post("/purge", status_code=204)
def purge_articles(_: dict = Depends(require_admin)):
    db = get_db()
    batch = db.batch()
    docs = list(db.collection("articles").stream())
    for i, doc in enumerate(docs):
        batch.delete(doc.reference)
        if (i + 1) % 500 == 0:
            batch.commit()
            batch = db.batch()
    batch.commit()


@router.post("/collect", status_code=202)
def trigger_collection(_: dict = Depends(require_admin)):
    try:
        token = _get_access_token()
        resp = httpx.post(
            CLOUD_RUN_JOB_URL,
            headers={"Authorization": f"Bearer {token}"},
            json={},
            timeout=15,
        )
        if resp.status_code not in (200, 202):
            raise HTTPException(status_code=502, detail=f"Cloud Run error: {resp.text}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"status": "triggered"}


@router.post("/purge-and-collect", status_code=202)
def purge_and_collect(current_user: dict = Depends(require_admin)):
    purge_articles(current_user)
    return trigger_collection(current_user)
