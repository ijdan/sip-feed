"""Analyse quotidienne des logs GCP par LLM.

Cf. features/daily-log-analysis.feature.

Le job log-analyzer est censé tourner chaque nuit (Cloud Run Job + Cloud Scheduler).
Il récupère les logs WARNING+ des 24 dernières heures depuis Cloud Logging,
les soumet à Gemini, et stocke un rapport structuré dans
`log_analyses/{YYYY-MM-DD}` (la date couverte = veille de l'exécution).
"""
import json
import logging
import os
from datetime import datetime, date, timedelta, timezone

logger = logging.getLogger(__name__)

# Limites
MAX_LOG_ENTRIES = 2000           # plafond du nombre d'entrées collectées
MAX_ITEMS = 20                   # plafond du nombre d'items produits par le LLM
PRIORITES = ["CRITIQUE", "HAUTE", "MOYENNE", "BASSE"]
_PRIORITE_ORDRE = {p: i for i, p in enumerate(PRIORITES)}

MESSAGE_AUCUNE_ANOMALIE = "Aucune anomalie détectée sur les dernières 24h."
MESSAGE_INDISPONIBILITE_LLM = (
    "⚠️ Analyse LLM indisponible — tous les modèles Gemini ont retourné une erreur. "
    "Les logs ont été collectés mais n'ont pas pu être analysés."
)
MESSAGE_VOLUME_TRONQUE = (
    "Volume de logs tronqué à {max_entries} entrées (les ERROR ont été priorisés "
    "sur les WARNING)."
)


# ─── Collecte des logs ────────────────────────────────────────────────────────

def fetch_log_entries(period_start: datetime, period_end: datetime) -> list[dict]:
    """Récupère toutes les entrées WARNING+ de Cloud Logging sur la période.

    Retourne une liste de dicts {severity, message, timestamp}.
    Cette fonction est mockée dans les tests.
    """
    from google.cloud import logging_v2

    project_id = os.environ.get("FIRESTORE_PROJECT_ID", "tech-news-aggregator-001")
    client = logging_v2.Client(project=project_id)

    filtre = (
        f'severity>=WARNING '
        f'AND timestamp>="{period_start.isoformat()}" '
        f'AND timestamp<"{period_end.isoformat()}"'
    )
    entries: list[dict] = []
    for entry in client.list_entries(filter_=filtre, order_by="timestamp desc"):
        payload = entry.payload
        if isinstance(payload, dict):
            message = payload.get("message", "")
        else:
            message = str(payload) if payload else ""
        entries.append({
            "severity": str(entry.severity or "DEFAULT"),
            "message": message,
            "timestamp": entry.timestamp.isoformat() if entry.timestamp else "",
        })
    return entries


def collect_logs(
    period_start: datetime,
    period_end: datetime,
    max_entries: int = MAX_LOG_ENTRIES,
    fetcher=None,
) -> tuple[list[dict], bool]:
    """Collecte les logs WARNING+ et les tronque en priorisant les ERROR.

    Retourne (entrées_collectées, volume_tronqué).
    """
    fetcher = fetcher or fetch_log_entries
    raw = fetcher(period_start, period_end)

    # Garde-fou : ne retient que WARNING+
    raw = [e for e in raw if str(e.get("severity", "")).upper() in {
        "WARNING", "ERROR", "CRITICAL", "ALERT", "EMERGENCY"
    }]

    if len(raw) <= max_entries:
        return raw, False

    # Volume dépassé : les ERROR (et au-dessus) sont prioritaires
    errors = [e for e in raw if str(e.get("severity", "")).upper() != "WARNING"]
    warnings = [e for e in raw if str(e.get("severity", "")).upper() == "WARNING"]
    keep_warnings = max_entries - len(errors)
    if keep_warnings < 0:
        keep_warnings = 0
        errors = errors[:max_entries]
    collected = errors + warnings[:keep_warnings]
    logger.warning(
        "Volume de logs tronqué : %d entrées brutes → %d retenues (ERROR priorisés)",
        len(raw), len(collected),
    )
    return collected, True


# ─── Analyse LLM ──────────────────────────────────────────────────────────────

LOG_ANALYSIS_PROMPT = """
Tu es un expert SRE chargé d'analyser les logs WARNING+ d'une application Python
(backend FastAPI + collector de news tech sur GCP) sur les dernières 24h.

Voici les logs bruts ({count} entrées) :
---
{logs}
---

Produis un rapport structuré en JSON avec ces champs :
- "resume" : (string) synthèse globale en 2-3 phrases en français — l'état de santé,
  les problèmes majeurs, ou « aucune anomalie » si tout est nominal.
- "items" : (array, max 20 éléments) liste des points notables, chaque item contenant :
    - "point_notable" : (string) description claire du problème en français
    - "prompt_correction" : (string) prompt prêt à copier-coller pour demander
       à Claude/Gemini de corriger ce point (mentionne le fichier suspect si possible)
    - "date" : (string) timestamp ISO de la première occurrence du problème
    - "priorite" : (string) une valeur parmi "CRITIQUE", "HAUTE", "MOYENNE", "BASSE"

Règles :
- Groupe les logs similaires en un seul item
- Priorise : CRITIQUE = production down, HAUTE = fonctionnalité cassée,
  MOYENNE = dégradation, BASSE = warning informatif
- N'invente aucun fait absent des logs

Réponds UNIQUEMENT avec un objet JSON valide {{"resume": "...", "items": [...]}}.
"""


def _call_log_llm(prompt: str, model_priority: list[str]) -> str:
    """Wrapper autour du LLM Gemini — séparé pour faciliter le mock."""
    from processors.gemini_processor import _call_llm
    return _call_llm(prompt, model_priority, thinking=False)


def analyze_logs_with_llm(
    log_entries: list[dict],
    model_priority: list[str],
    llm_caller=None,
) -> dict:
    """Soumet les logs à Gemini et retourne {resume, items}.

    En cas d'échec de tous les modèles, retourne un rapport vide
    avec un message d'indisponibilité.
    """
    if not log_entries:
        return {"resume": MESSAGE_AUCUNE_ANOMALIE, "items": []}

    logs_text = "\n".join(
        f"[{e.get('severity', '')}] {e.get('timestamp', '')} — {e.get('message', '')}"
        for e in log_entries
    )
    prompt = LOG_ANALYSIS_PROMPT.format(count=len(log_entries), logs=logs_text[:60000])

    caller = llm_caller or _call_log_llm
    try:
        raw = caller(prompt, model_priority)
    except Exception as e:
        logger.error("Analyse LLM impossible — tous les modèles ont échoué : %s", e)
        return {"resume": MESSAGE_INDISPONIBILITE_LLM, "items": []}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Réponse LLM non parsable : %s", e)
        return {"resume": MESSAGE_INDISPONIBILITE_LLM, "items": []}

    items = parsed.get("items", []) or []
    # Validation et nettoyage de chaque item
    cleaned = []
    for item in items:
        priorite = str(item.get("priorite", "")).upper()
        if priorite not in PRIORITES:
            priorite = "MOYENNE"
        cleaned.append({
            "point_notable": item.get("point_notable", ""),
            "prompt_correction": item.get("prompt_correction", ""),
            "date": item.get("date", ""),
            "priorite": priorite,
        })

    # Tri par priorité décroissante, plafonné à MAX_ITEMS
    cleaned.sort(key=lambda x: _PRIORITE_ORDRE.get(x["priorite"], 99))
    cleaned = cleaned[:MAX_ITEMS]

    return {"resume": parsed.get("resume", "").strip(), "items": cleaned}


# ─── Orchestration ────────────────────────────────────────────────────────────

def run_log_analysis(
    db,
    now: datetime | None = None,
    model_priority: list[str] | None = None,
    fetcher=None,
    llm_caller=None,
) -> dict:
    """Exécute le job log-analyzer : collecte → analyse → écriture Firestore.

    - `now` : moment de l'exécution (défaut : maintenant UTC). La période couverte
      est la journée précédente (24h).
    - Idempotent : si un document existe déjà à `log_analyses/{date_couverte}`,
      le job ne fait rien et retourne le document existant.
    """
    now = now or datetime.now(timezone.utc)
    date_couverte = (now - timedelta(days=1)).date()
    cle = date_couverte.isoformat()

    doc_ref = db.collection("log_analyses").document(cle)
    existing = doc_ref.get()
    if existing.exists:
        logger.info("Rapport déjà présent pour %s — job idempotent, aucune action.", cle)
        return existing.to_dict()

    period_start = datetime.combine(date_couverte, datetime.min.time(), tzinfo=timezone.utc)
    period_end = period_start + timedelta(days=1)

    try:
        entries, truncated = collect_logs(period_start, period_end, fetcher=fetcher)
    except Exception as e:
        logger.error("Impossible de récupérer les logs Cloud Logging : %s", e)
        entries, truncated = [], False

    model_priority = model_priority or []
    if not entries:
        rapport = {"resume": MESSAGE_AUCUNE_ANOMALIE, "items": []}
    else:
        rapport = analyze_logs_with_llm(entries, model_priority, llm_caller=llm_caller)

    if truncated:
        suffixe = " " + MESSAGE_VOLUME_TRONQUE.format(max_entries=MAX_LOG_ENTRIES)
        rapport["resume"] = (rapport.get("resume", "") + suffixe).strip()

    document = {
        "date": cle,
        "generated_at": now.isoformat(),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "logs_count": len(entries),
        "resume": rapport["resume"],
        "items": rapport["items"],
    }
    doc_ref.set(document)
    logger.info("Rapport log-analyzer écrit : log_analyses/%s (%d items)", cle, len(rapport["items"]))
    return document
