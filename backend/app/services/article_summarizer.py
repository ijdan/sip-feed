import os
import json
import logging
import asyncio

import httpx
from bs4 import BeautifulSoup
import google.generativeai as genai

logger = logging.getLogger(__name__)

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

SUMMARY_PROMPT = """\
En tant que journaliste logiciel expert, résume l'article ci-dessous en 2000 mots.

Règles :
- Sois factuel, cite les technologies, entreprises et chiffres clés
- Structure le résumé avec des sections claires
- N'invente aucun fait absent du texte source
- Conserve les noms propres et acronymes techniques en version originale

Réponds UNIQUEMENT avec un objet JSON strict :
{{
  "summary_fr": "résumé complet en français (~2000 mots)",
  "summary_en": "complete summary in English (~2000 words)"
}}

Article à résumer :
---
{text}
---
"""

_STRIP_TAGS = [
    "script", "style", "nav", "header", "footer", "aside",
    "form", "iframe", "noscript", "svg", "button", "input",
    "select", "textarea", "label",
]

_STRIP_CLASS_KEYWORDS = [
    "ads", "advert", "banner", "cookie", "popup", "newsletter",
    "sidebar", "related", "social", "promo",
]


async def fetch_article_text(url: str) -> str:
    """Récupère et nettoie le texte brut d'un article (timeout 30 s)."""
    async with httpx.AsyncClient(
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; SipFeedBot/1.0)"},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for tag in soup(_STRIP_TAGS):
        tag.decompose()
    for tag in soup.find_all(class_=lambda c: c and any(
        k in " ".join(c).lower() for k in _STRIP_CLASS_KEYWORDS
    )):
        tag.decompose()

    main = soup.find("article") or soup.find("main") or soup.find("body")
    text = (main or soup).get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)[:50_000]


from typing import Callable


def _sync_call_llm(text: str, models_to_try: list[str]) -> tuple[str, str, str]:
    """Cascade LLM synchrone. Retourne (summary_fr, summary_en, model_used)."""
    return _sync_call_llm_with_progress(text, models_to_try, send_progress=None)


def _sync_call_llm_with_progress(
    text: str,
    models_to_try: list[str],
    send_progress: Callable[[str], None] | None,
) -> tuple[str, str, str]:
    """Cascade LLM synchrone avec callbacks de progression.

    send_progress est appelé depuis le thread — utiliser call_soon_threadsafe côté appelant.
    """
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    prompt = SUMMARY_PROMPT.format(text=text)
    generation_config = {
        "temperature": 0.4,
        "max_output_tokens": 8192,
        "response_mime_type": "application/json",
    }
    last_error: Exception | None = None
    for i, model_name in enumerate(models_to_try):
        if send_progress:
            if i == 0:
                send_progress(f"Génération du résumé LLM en cours ({model_name})…")
            else:
                send_progress(f"Modèle précédent indisponible — essai avec {model_name}…")
        try:
            logger.debug(f"Résumé — essai modèle : {model_name}")
            m = genai.GenerativeModel(model_name, generation_config=generation_config)
            response = m.generate_content(prompt)
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            result = json.loads(raw.strip())
            logger.info(f"Résumé généré par {model_name}")
            return result.get("summary_fr", ""), result.get("summary_en", ""), model_name
        except Exception as exc:
            logger.warning(f"Résumé : {model_name} indisponible ({exc.__class__.__name__})")
            last_error = exc
    raise last_error or RuntimeError("Aucun modèle LLM disponible")


async def generate_summary(text: str, models_to_try: list[str]) -> tuple[str, str, str]:
    """Wrapper async pour la cascade LLM sans progression (exécuté dans un thread pool)."""
    return await asyncio.to_thread(_sync_call_llm, text, models_to_try)


def get_model_priority(db) -> list[str]:
    """Lit model_priority depuis settings/global, retourne DEFAULT_MODEL_PRIORITY si absent."""
    try:
        doc = db.collection("settings").document("global").get()
        if doc.exists:
            priority = doc.to_dict().get("model_priority") or []
            if priority:
                return priority
    except Exception as exc:
        logger.warning(f"Impossible de lire model_priority : {exc}")
    return DEFAULT_MODEL_PRIORITY
