import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
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


DEFAULT_MODEL_PRIORITY = [
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite",
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]

class GlobalSettings(BaseModel):
    llm_enabled: bool = True
    thinking_enabled: bool = True
    model_priority: list[str] = DEFAULT_MODEL_PRIORITY
    gmail_lookback_days: int = 1
    retention_days: int = 0


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
    data = doc.to_dict()
    stored = data.get("model_priority", [])
    # Garde uniquement les modèles connus, ajoute les nouveaux en tête
    stored = [m for m in stored if m in DEFAULT_MODEL_PRIORITY]
    for model in reversed(DEFAULT_MODEL_PRIORITY):
        if model not in stored:
            stored.insert(0, model)
    data["model_priority"] = stored
    # Persiste la liste nettoyée
    db.collection("settings").document("global").update({"model_priority": stored})
    return GlobalSettings(**data)


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


@router.get("/report")
def get_latest_report(_: dict = Depends(require_admin)):
    db = get_db()
    doc = db.collection("reports").document("latest").get()
    if not doc.exists:
        return {"content": None, "generated_at": None}
    return doc.to_dict()


@router.get("/logs")
def get_collector_logs(limit: int = Query(100, le=500), _: dict = Depends(require_admin)):
    try:
        token = _get_access_token()
        resp = httpx.post(
            "https://logging.googleapis.com/v2/entries:list",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "resourceNames": [f"projects/{settings.firestore_project_id}"],
                "filter": 'resource.type="cloud_run_job" AND resource.labels.job_name="collector"',
                "orderBy": "timestamp desc",
                "pageSize": limit,
            },
            timeout=15,
        )
        resp.raise_for_status()
        entries = resp.json().get("entries", [])

        logs = []
        for e in entries:
            text = e.get("textPayload") or e.get("jsonPayload", {}).get("message", "")
            if not text:
                continue
            severity = e.get("severity", "INFO")
            logs.append({
                "timestamp": e.get("timestamp", ""),
                "severity": severity,
                "message": text,
            })
        return {"logs": logs}
    except Exception as ex:
        raise HTTPException(status_code=502, detail=str(ex))
