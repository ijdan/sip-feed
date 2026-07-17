import logging
logger = logging.getLogger(__name__)

import os
import subprocess
from datetime import date
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from google.auth import default as google_auth_default
from google.auth.transport.requests import Request as GoogleRequest
from pathlib import Path

from app.auth.google_oauth import require_admin
from app.db.firestore import get_db
from app.config import settings

# Chemin vers le collector (relatif au projet)
COLLECTOR_DIR = Path(__file__).resolve().parents[3] / "collector"
IS_LOCAL = os.environ.get("APP_ENV") == "local"


def _check_emulator_reachable():
    """Bloque les opérations destructives si l'émulateur n'est pas joignable."""
    if not IS_LOCAL:
        return  # en prod, pas de restriction
    import socket
    try:
        host = os.environ.get("FIRESTORE_EMULATOR_HOST", "localhost:8080").split(":")[0]
        port = int(os.environ.get("FIRESTORE_EMULATOR_HOST", "localhost:8080").split(":")[1])
        with socket.create_connection((host, port), timeout=1):
            pass
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="⛔ Émulateur Firestore non disponible. Lance './start-emulator.sh' avant de continuer — la production est protégée."
        )

router = APIRouter()

CLOUD_RUN_JOB_URL = (
    f"https://europe-west1-run.googleapis.com/apis/run.googleapis.com/v1"
    f"/namespaces/{settings.firestore_project_id}/jobs/collector:run"
)


DEFAULT_MODEL_PRIORITY = [
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
]

class GlobalSettings(BaseModel):
    llm_enabled: bool = True
    thinking_enabled: bool = True
    model_priority: list[str] = DEFAULT_MODEL_PRIORITY
    gmail_lookback_days: int = 1
    retention_days: int = 0
    interest: str = ""
    # Périmètre de la synthèse du jour — liste vide = aucune restriction
    synthesis_source_ids: list[str] = []
    synthesis_categories: list[str] = []
    # Volume max de texte (caractères) envoyé au LLM pour la synthèse
    synthesis_max_input_chars: int = 180_000
    # Nombre de synthèses affichées sur la page /admin/synthesis
    synthesis_display_count: int = 3


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


class SummaryPromptPayload(BaseModel):
    prompt: str = ""


def _summary_prompt_response(db) -> dict:
    from app.services.article_summarizer import SUMMARY_PROMPT, get_summary_prompt

    doc = db.collection("settings").document("prompts").get()
    data = doc.to_dict() if doc.exists else {}
    prompt, version = get_summary_prompt(db)
    return {
        "prompt": prompt,
        "is_custom": bool((data.get("summary_prompt") or "").strip()),
        "default_prompt": SUMMARY_PROMPT,
        "prompt_version": version,
        "updated_at": data.get("summary_prompt_updated_at"),
        "updated_by": data.get("summary_prompt_updated_by"),
    }


@router.get("/summary-prompt")
def get_summary_prompt_settings(_: dict = Depends(require_admin)):
    """Retourne le prompt de génération LinkedIn actif (personnalisé ou défaut)."""
    return _summary_prompt_response(get_db())


@router.put("/summary-prompt")
def update_summary_prompt(payload: SummaryPromptPayload, current_user: dict = Depends(require_admin)):
    """Enregistre le prompt personnalisé. Un prompt vide réinitialise au défaut du code."""
    from datetime import datetime, timezone

    from app.services.article_summarizer import PROMPT_PLACEHOLDERS

    prompt = payload.prompt.strip()
    if prompt:
        missing = [p for p in PROMPT_PLACEHOLDERS if p not in prompt]
        if "{text}" in missing:
            raise HTTPException(
                status_code=422,
                detail="Le prompt doit contenir le placeholder {text} (texte de l'article).",
            )
    db = get_db()
    db.collection("settings").document("prompts").set(
        {
            "summary_prompt": prompt,
            "summary_prompt_updated_at": datetime.now(timezone.utc).isoformat(),
            "summary_prompt_updated_by": current_user.get("email", ""),
        },
        merge=True,
    )
    return _summary_prompt_response(db)


@router.post("/purge", status_code=204)
def purge_articles(_: dict = Depends(require_admin)):
    _check_emulator_reachable()
    db = get_db()
    batch = db.batch()
    docs = list(db.collection("articles").stream())
    for i, doc in enumerate(docs):
        batch.delete(doc.reference)
        if (i + 1) % 500 == 0:
            batch.commit()
            batch = db.batch()
    batch.commit()


def _trigger_local(source_id: str | None = None, synthesis_only: bool = False,
                   synthesis_date: str | None = None,
                   synthesis_date_end: str | None = None) -> dict:
    """En local : lance le collector en sous-processus avec l'émulateur."""
    venv_python = COLLECTOR_DIR / "venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else "python3"
    env = {
        **os.environ,
        "GRPC_DNS_RESOLVER": "native",
        "GOOGLE_CLOUD_PROJECT": settings.firestore_project_id,
    }
    if source_id:
        env["COLLECTOR_SOURCE_ID"] = source_id
    if synthesis_only:
        env["COLLECTOR_SYNTHESIS_ONLY"] = "1"
    if synthesis_date:
        env["COLLECTOR_SYNTHESIS_DATE"] = synthesis_date
    if synthesis_date_end:
        env["COLLECTOR_SYNTHESIS_DATE_END"] = synthesis_date_end

    import tempfile, pathlib
    log_file = pathlib.Path(tempfile.gettempdir()) / "collector_local.log"
    subprocess.Popen(
        [python, "main.py"],
        cwd=str(COLLECTOR_DIR),
        env=env,
        stdout=open(log_file, "w"),
        stderr=subprocess.STDOUT,
    )
    logger.info(f"Collector lancé — logs : {log_file}")
    return {"status": "triggered_local", "source_id": source_id}


def _trigger_job(source_id: str | None = None, synthesis_only: bool = False,
                 synthesis_date: str | None = None,
                 synthesis_date_end: str | None = None) -> dict:
    """Déclenche le Cloud Run Job, avec filtre source ou mode synthèse seule optionnels."""
    token = _get_access_token()
    env_vars = []
    if source_id:
        env_vars.append({"name": "COLLECTOR_SOURCE_ID", "value": source_id})
    if synthesis_only:
        env_vars.append({"name": "COLLECTOR_SYNTHESIS_ONLY", "value": "1"})
    if synthesis_date:
        env_vars.append({"name": "COLLECTOR_SYNTHESIS_DATE", "value": synthesis_date})
    if synthesis_date_end:
        env_vars.append({"name": "COLLECTOR_SYNTHESIS_DATE_END", "value": synthesis_date_end})
    body: dict = {}
    if env_vars:
        body = {"overrides": {"containerOverrides": [{"env": env_vars}]}}
    resp = httpx.post(
        CLOUD_RUN_JOB_URL,
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=15,
    )
    if resp.status_code not in (200, 202):
        raise HTTPException(status_code=502, detail=f"Cloud Run error: {resp.text}")
    return {"status": "triggered", "source_id": source_id}


@router.post("/collect", status_code=202)
def trigger_collection(_: dict = Depends(require_admin)):
    if IS_LOCAL:
        _check_emulator_reachable()
        return _trigger_local()
    try:
        return _trigger_job()
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/sources/{source_id}/collect", status_code=202)
def collect_single_source(source_id: str, _: dict = Depends(require_admin)):
    """Déclenche la collecte pour une source spécifique uniquement."""
    db = get_db()
    if not db.collection("sources").document(source_id).get().exists:
        raise HTTPException(status_code=404, detail="Source introuvable")
    if IS_LOCAL:
        _check_emulator_reachable()
        return _trigger_local(source_id=source_id)
    try:
        return _trigger_job(source_id=source_id)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/synthesis/generate", status_code=202)
def generate_synthesis_now(date_: str | None = Query(None, alias="date"),
                           end_date_: str | None = Query(None, alias="end_date"),
                           _: dict = Depends(require_admin)):
    """Déclenche manuellement la génération de la synthèse (mode synthèse seule).

    Le collector est lancé avec COLLECTOR_SYNTHESIS_ONLY=1 : aucune collecte,
    régénération forcée (le skip « rien de nouveau » est contourné).
    `date` (YYYY-MM-DD, optionnelle) : restreint le corpus aux articles
    collectés ce jour-là et écrit dans syntheses/{date}.
    `end_date` (YYYY-MM-DD, optionnelle) : étend le corpus aux articles
    collectés entre `date` et `end_date` incluses (date de départ ≤ date de
    fin), document écrit dans syntheses/{date}_{end_date}.
    """
    if end_date_ and not date_:
        raise HTTPException(status_code=400,
                            detail="Date de départ requise quand une date de fin est fournie.")
    synthesis_date = None
    synthesis_date_end = None
    if date_:
        try:
            parsed = date.fromisoformat(date_)
        except ValueError:
            raise HTTPException(status_code=400, detail="Date invalide — format attendu : YYYY-MM-DD.")
        if parsed > date.today():
            raise HTTPException(status_code=400, detail="La date ne peut pas être dans le futur.")
        parsed_end = None
        if end_date_:
            try:
                parsed_end = date.fromisoformat(end_date_)
            except ValueError:
                raise HTTPException(status_code=400,
                                    detail="Date de fin invalide — format attendu : YYYY-MM-DD.")
            if parsed_end > date.today():
                raise HTTPException(status_code=400, detail="La date de fin ne peut pas être dans le futur.")
            if parsed > parsed_end:
                raise HTTPException(status_code=400,
                                    detail="La date de départ doit être antérieure ou égale à la date de fin.")
            if parsed_end == parsed:
                parsed_end = None  # plage d'un seul jour = comportement jour unique
        if parsed != date.today():
            synthesis_date = parsed.isoformat()  # aujourd'hui = comportement par défaut
        if parsed_end:
            # end > start ≥ aujourd'hui étant rejeté, une plage implique start < aujourd'hui
            synthesis_date_end = parsed_end.isoformat()

    db = get_db()
    doc = db.collection("settings").document("global").get()
    interest = (doc.to_dict() or {}).get("interest", "").strip() if doc.exists else ""
    if not interest:
        raise HTTPException(status_code=400,
                            detail="Aucun centre d'intérêt renseigné — synthèse désactivée.")
    if IS_LOCAL:
        _check_emulator_reachable()
        return _trigger_local(synthesis_only=True, synthesis_date=synthesis_date,
                              synthesis_date_end=synthesis_date_end)
    try:
        return _trigger_job(synthesis_only=True, synthesis_date=synthesis_date,
                            synthesis_date_end=synthesis_date_end)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/purge-and-collect", status_code=202)
def purge_and_collect(current_user: dict = Depends(require_admin)):
    purge_articles(current_user)
    return trigger_collection(current_user)


@router.get("/stats")
def get_stats(_: dict = Depends(require_admin)):
    from datetime import date, timedelta
    db = get_db()

    # Nombre d'utilisateurs enregistrés
    users_count = len(list(db.collection("users").stream()))

    # Appels API : agréger sur today, 7j, 30j
    today = date.today()
    periods = {"today": 0, "last_7": 6, "last_30": 29}
    api_calls: dict = {}

    for days_back in range(30):
        day = (today - timedelta(days=days_back)).isoformat()
        doc = db.collection("api_stats").document(day).get()
        if not doc.exists:
            continue
        for identifier, count in doc.to_dict().items():
            if identifier not in api_calls:
                api_calls[identifier] = {"today": 0, "last_7": 0, "last_30": 0}
            if days_back == 0:
                api_calls[identifier]["today"] += count
            if days_back <= 6:
                api_calls[identifier]["last_7"] += count
            api_calls[identifier]["last_30"] += count

    # Stats articles par utilisateur
    user_stats = []
    for pref_doc in db.collection("user_preferences").stream():
        d = pref_doc.to_dict()
        user_stats.append({
            "email": pref_doc.id,
            "favorites": len(d.get("favorites", [])),
            "reading_list": len(d.get("reading_list", [])),
            "read_articles": len(d.get("read_articles", [])),
            "dismissed": len(d.get("dismissed", [])),
        })

    return {
        "users_count": users_count,
        "api_calls": [
            {"identifier": k, **v}
            for k, v in sorted(api_calls.items(), key=lambda x: -x[1]["last_30"])
        ],
        "user_article_stats": sorted(user_stats, key=lambda x: -x["favorites"]),
    }


@router.get("/syntheses")
def get_syntheses(date_: str | None = Query(None, alias="date"),
                  end_date_: str | None = Query(None, alias="end_date"),
                  _: dict = Depends(require_admin)):
    """Retourne les N dernières synthèses existantes avec les articles cités.

    N = `settings/global.synthesis_display_count` (défaut 3). Les IDs de la
    collection `syntheses` étant des dates ISO, le tri sur l'ID décroissant
    donne les plus récentes — y compris celles générées a posteriori pour
    une date passée.
    `date` (YYYY-MM-DD, optionnelle) : retourne uniquement la synthèse de ce
    jour-là. Avec `end_date`, retourne la synthèse de la plage
    `{date}_{end_date}` (consultation d'une période générée manuellement).
    """
    db = get_db()
    if date_:
        try:
            start = date.fromisoformat(date_).isoformat()
            end = date.fromisoformat(end_date_).isoformat() if end_date_ else None
        except ValueError:
            raise HTTPException(status_code=400, detail="Date invalide — format attendu : YYYY-MM-DD.")
        doc_id = f"{start}_{end}" if end and end != start else start
        docs = [db.collection("syntheses").document(doc_id).get()]
    else:
        settings_doc = db.collection("settings").document("global").get()
        count = (settings_doc.to_dict() or {}).get("synthesis_display_count", 3) if settings_doc.exists else 3
        count = max(1, min(int(count or 3), 30))
        # Tri par date de GÉNÉRATION (generated_at), pas par date cible (ID du
        # document) : une synthèse générée aujourd'hui pour une date passée
        # compte comme la plus récente. generated_at est un champ ordinaire →
        # le tri descendant est supporté nativement (contrairement à __name__).
        docs = list(db.collection("syntheses").order_by(
            "generated_at", direction="DESCENDING"
        ).limit(count).stream())
    results = []
    for doc in docs:
        if not doc.exists:
            continue
        day = doc.id
        data = doc.to_dict()
        # C2 : batch fetch en un seul appel Firestore (évite N+1 queries)
        cited_ids = data.get("cited_ids", [])
        cited_articles = []
        if cited_ids:
            refs = [db.collection("articles").document(id) for id in cited_ids]
            article_docs = db.get_all(refs)
            # Résumés IA déjà générés (cache article_summaries), en batch également
            summary_refs = [db.collection("article_summaries").document(id) for id in cited_ids]
            ids_with_summary = {s.id for s in db.get_all(summary_refs) if s.exists}
            for a_doc in article_docs:
                if a_doc.exists:
                    a = a_doc.to_dict()
                    cited_articles.append({
                        "id": a_doc.id,
                        "title_fr": a.get("title_fr") or a.get("title", ""),
                        "title_en": a.get("title_en") or a.get("title", ""),
                        "short_description_fr": a.get("short_description_fr", ""),
                        "short_description_en": a.get("short_description_en", ""),
                        "long_description_fr": a.get("long_description_fr", ""),
                        "long_description_en": a.get("long_description_en", ""),
                        "article_url": a.get("article_url", ""),
                        "source_name": a.get("source_name", ""),
                        "has_summary": a_doc.id in ids_with_summary,
                    })
        results.append({"date": day, **data, "cited_articles": cited_articles})
    return {"syntheses": results}


@router.get("/report")
def get_latest_report(_: dict = Depends(require_admin)):
    db = get_db()
    doc = db.collection("reports").document("latest").get()
    if not doc.exists:
        return {"content": None, "generated_at": None}
    return doc.to_dict()


@router.get("/log-analysis")
def get_log_analysis(_: dict = Depends(require_admin)):
    from datetime import date as date_type, timedelta
    db = get_db()
    # Le job tourne la nuit et couvre la veille → la clé = hier, pas aujourd'hui
    yesterday = (date_type.today() - timedelta(days=1)).isoformat()
    doc = db.collection("log_analyses").document(yesterday).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Rapport non disponible pour cette date.")
    return doc.to_dict()


@router.get("/log-analysis/{date_str}")
def get_log_analysis_by_date(date_str: str, _: dict = Depends(require_admin)):
    from datetime import date as date_type
    try:
        date_type.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=422, detail="Format de date invalide (attendu : YYYY-MM-DD).")
    db = get_db()
    doc = db.collection("log_analyses").document(date_str).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Rapport non disponible pour cette date.")
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
