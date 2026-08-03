import os
import json
import hashlib
import logging
import asyncio

import httpx
from bs4 import BeautifulSoup
import google.generativeai as genai

logger = logging.getLogger(__name__)

# Doit rester aligné sur app/routers/admin.py et collector/processors/gemini_processor.py.
DEFAULT_MODEL_PRIORITY = [
    "gemma-4-26b-a4b-it",      # 0,07 $ / 0,30 $
    "gemma-4-31b-it",          # 0,09 $ / 0,34 $
    "gemini-3.1-flash-lite",   # 0,25 $ / 1,50 $ — GA
    "gemini-3-flash-preview",  # 0,25 $ / 1,50 $ — preview
    "gemini-3.5-flash",        # 1,50 $ / 9,00 $
]

PROMPT_VERSION = "linkedin-v3"

SUMMARY_PROMPT = """\
En tant que journaliste expert en technologie avec une plume narrative, rédige un post LinkedIn mémorable \
basé sur l'article ci-dessous.

Contexte de l'article :
- Titre : {title}
- Source : {source}

Ton style : tu combines la narration journalistique (arc temporel, protagonistes nommés, contexte avant/après) \
avec un regard contrarian — tu identifies ce que l'article révèle que le consensus habituel occulte ou \
que la majorité n'a pas encore vu. Tu peux utiliser la première personne avec parcimonie pour apporter \
ta voix ("ce qui me frappe ici", "je ne m'attendais pas à", "ce que peu ont relevé").

Structure impérative du post (dans cet ordre) :
1. Mise en scène (2-3 lignes) : situe l'article dans son contexte narratif — qui sont les acteurs, \
quelle décision ou tendance est en jeu, depuis quand. Mentionne le titre, l'auteur s'il est nommé dans \
le texte, et la source.
2. Retournement (1-2 lignes) : identifie ce que cet article révèle de surprenant, de contre-intuitif \
ou de sous-estimé par rapport au discours dominant — c'est la phrase qui accroche et qui fait lire la suite.
3. Développement (3-4 paragraphes) : déroule les idées clés avec la voix d'un analyste qui a compris \
plus loin que le titre — contexte réel, enjeux, nuances, ce que ça change concrètement.
4. Section "À retenir :" : 3 à 4 points clés sous forme de tirets simples (- Point).

Règles de format :
- 300 à 400 mots au total
- Texte brut uniquement : aucun #, **, *, _ ni > — seuls les tirets (-) de la section "À retenir" sont autorisés
- Paragraphes séparés par une ligne vide
- Conserve les noms propres, entreprises, technologies et chiffres clés de l'article
- N'invente aucun fait absent du texte source

Réponds UNIQUEMENT avec un objet JSON strict :
{
  "summary_fr": "post LinkedIn en français (300-400 mots, texte brut)",
  "summary_en": "LinkedIn post in English (300-400 words, plain text)"
}

Article :
---
{text}
---
"""

# Placeholders attendus dans le template de prompt (substitution littérale,
# pas str.format — un prompt édité par l'admin peut contenir des accolades).
PROMPT_PLACEHOLDERS = ["{title}", "{source}", "{text}"]


def render_prompt(template: str, title: str, source: str, text: str) -> str:
    """Substitue les placeholders {title}, {source}, {text} dans le template."""
    return (
        template
        .replace("{title}", title)
        .replace("{source}", source)
        .replace("{text}", text)
    )


def get_summary_prompt(db) -> tuple[str, str]:
    """Retourne (template, version) du prompt de résumé.

    Lit settings/prompts.summary_prompt en Firestore ; si absent ou vide,
    retombe sur SUMMARY_PROMPT. La version d'un prompt personnalisé est dérivée
    de son hash pour invalider le cache article_summaries à chaque modification.
    """
    try:
        doc = db.collection("settings").document("prompts").get()
        if doc.exists:
            custom = (doc.to_dict().get("summary_prompt") or "").strip()
            if custom:
                digest = hashlib.sha256(custom.encode("utf-8")).hexdigest()[:12]
                return custom, f"linkedin-custom-{digest}"
    except Exception as exc:
        logger.warning(f"Impossible de lire le prompt personnalisé : {exc}")
    return SUMMARY_PROMPT, PROMPT_VERSION

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
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"},
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
    prompt_template: str | None = None,
) -> tuple[str, str, str]:
    """Cascade LLM synchrone avec callbacks de progression.

    send_progress est appelé depuis le thread — utiliser call_soon_threadsafe côté appelant.
    prompt_template permet d'injecter le prompt personnalisé lu en Firestore
    (défaut : SUMMARY_PROMPT).
    """
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    meta = article_meta or {}
    prompt = render_prompt(
        prompt_template or SUMMARY_PROMPT,
        title=meta.get("title") or "Non renseigné",
        source=meta.get("source") or "Non renseignée",
        text=text,
    )
    generation_config = {
        "temperature": 0.7,
        "max_output_tokens": 2048,
        "response_mime_type": "application/json",
    }
    errors: list[str] = []
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
            detail = str(exc)[:200]
            logger.warning(f"Résumé : {model_name} indisponible ({exc.__class__.__name__}: {detail})")
            errors.append(f"{model_name} ({exc.__class__.__name__} : {detail})")
    raise RuntimeError(
        "tous les modèles ont échoué — " + "; ".join(errors) if errors else "aucun modèle LLM disponible"
    )


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
