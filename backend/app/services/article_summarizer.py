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

PROMPT_VERSION = "linkedin-v2"

SUMMARY_PROMPT = """\
En tant que journaliste expert en technologie, rédige un post LinkedIn basé sur l'article ci-dessous.

Contexte de l'article :
- Titre : {title}
- Source : {source}

Ton rôle : tu as lu cet article et tu partages avec ton réseau ce que tu en as retenu. \
Positionne-toi en expert qui explique, contextualise et met en avant les points clés — pas en simple résumeur.

Structure impérative du post (dans cet ordre) :
1. Contexte (1-2 lignes) : indique le titre de l'article, l'auteur s'il est mentionné dans le texte, et la source. Situe le lecteur dès l'ouverture.
2. Accroche (1-2 lignes) : une observation forte qui donne envie de lire la suite.
3. Corps (3-4 paragraphes) : explique ce que tu as compris, pourquoi c'est intéressant, les idées clés dans tes propres mots de journaliste.
4. Section "À retenir :" : 3 à 4 points clés sous forme de tirets simples (- Point).

Règles de format :
- 300 à 400 mots au total
- Texte brut uniquement : aucun #, **, *, _ ni > — seuls les tirets (-) de la section "À retenir" sont autorisés
- Paragraphes séparés par une ligne vide
- Conserve les noms propres, technologies et chiffres clés de l'article
- N'invente aucun fait absent du texte source

Réponds UNIQUEMENT avec un objet JSON strict :
{{
  "summary_fr": "post LinkedIn en français (300-400 mots, texte brut)",
  "summary_en": "LinkedIn post in English (300-400 words, plain text)"
}}

Article :
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
    article_meta: dict | None = None,
) -> tuple[str, str, str]:
    """Cascade LLM synchrone avec callbacks de progression.

    send_progress est appelé depuis le thread — utiliser call_soon_threadsafe côté appelant.
    """
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    meta = article_meta or {}
    prompt = SUMMARY_PROMPT.format(
        title=meta.get("title") or "Non renseigné",
        source=meta.get("source") or "Non renseignée",
        text=text,
    )
    generation_config = {
        "temperature": 0.7,
        "max_output_tokens": 2048,
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
