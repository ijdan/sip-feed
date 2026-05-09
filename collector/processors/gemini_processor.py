import os
import uuid
import json
from datetime import datetime
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

DEFAULT_MODEL_PRIORITY = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]

CATEGORIES = ["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"]

BATCH_PROMPT_FR = """
Tu es rédacteur en chef d'un média tech francophone de référence.
Tu vas traiter {count} articles en une seule passe.

Pour chaque article, produis une fiche de veille en français, rédigée avec le style
concis et précis d'un journaliste tech, à destination de professionnels (développeurs,
architectes, DSI).

Règles de rédaction :
- Traduis et reformule le titre pour qu'il soit percutant en français
- Écris tous les textes en français, même si la source est en anglais
- Sois factuel et précis : cite les technologies, versions, noms d'entreprises, chiffres clés
- Ajoute du contexte pertinent si tu le connais (positionnement concurrentiel, impact secteur,
  tendance de fond) — uniquement si c'est fiable et utile
- Style : phrases courtes, actives, ton professionnel sans jargon inutile
- N'invente aucun fait non présent dans la source ou dans tes connaissances avérées

Articles à traiter :
{articles}

Réponds UNIQUEMENT avec un tableau JSON valide de {count} objets, dans le même ordre que les articles :
[
  {{
    "title": "titre reformulé en français, percutant (max 90 caractères)",
    "short_description": "accroche journalistique en 2 phrases maximum, donne envie de lire",
    "long_description": "analyse complète en 5 à 8 phrases : faits, contexte, enjeux, impact potentiel",
    "category": "une valeur parmi {categories}"
  }}
]
"""

BATCH_PROMPT_NO_TRANSLATION = """
Tu es un assistant spécialisé en veille technologique.
Tu vas traiter {count} articles en une seule passe.

Pour chaque article, produis un résumé structuré dans la langue de la source.

Règles :
- Conserve la langue originale de l'article
- Sois factuel : cite technologies, versions, entreprises, chiffres clés
- Style : concis, professionnel
- N'invente aucun fait

Articles à traiter :
{articles}

Réponds UNIQUEMENT avec un tableau JSON valide de {count} objets :
[
  {{
    "title": "titre original ou légèrement reformulé (max 90 caractères)",
    "short_description": "résumé en 2 phrases maximum",
    "long_description": "résumé détaillé en 5 à 8 phrases",
    "category": "une valeur parmi {categories}"
  }}
]
"""


def enrich_articles_batch(raw_articles: list[dict], translate: bool = True, model_priority: list[str] | None = None) -> list[dict]:
    """Traite tous les articles en un seul appel Gemini, avec fallback sur les modèles suivants."""
    articles_text = ""
    for i, raw in enumerate(raw_articles):
        articles_text += (
            f"--- Article {i + 1} ---\n"
            f"Titre original : {raw['title']}\n"
            f"Contenu : {raw.get('raw_content', '')[:1500]}\n\n"
        )

    template = BATCH_PROMPT_FR if translate else BATCH_PROMPT_NO_TRANSLATION
    prompt = template.format(
        count=len(raw_articles),
        articles=articles_text,
        categories=", ".join(CATEGORIES),
    )

    models_to_try = model_priority or DEFAULT_MODEL_PRIORITY
    last_error = None
    text = None

    for model_name in models_to_try:
        try:
            import logging
            logging.getLogger(__name__).debug(f"Essai modèle : {model_name}")
            m = genai.GenerativeModel(model_name)
            response = m.generate_content(prompt)
            text = response.text.strip()
            logging.getLogger(__name__).info(f"Modèle utilisé avec succès : {model_name}")
            break
        except Exception as e:
            logging.getLogger(__name__).warning(f"Modèle {model_name} indisponible : {e.__class__.__name__} — {e}")
            last_error = e

    if text is None:
        raise last_error or RuntimeError("Aucun modèle disponible")

    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    enriched_list = json.loads(text)

    results = []
    for i, raw in enumerate(raw_articles):
        enriched = enriched_list[i] if i < len(enriched_list) else {}
        results.append({
            "id": str(uuid.uuid4()),
            "title": enriched.get("title", raw["title"]),
            "short_description": enriched.get("short_description", ""),
            "long_description": enriched.get("long_description", ""),
            "article_url": raw["article_url"],
            "source_name": raw["source_name"],
            "source_id": raw["source_id"],
            "category": enriched.get("category", "Autre"),
            "published_at": raw.get("published_at", datetime.utcnow().isoformat()),
            "collected_at": datetime.utcnow().isoformat(),
        })

    return results


def save_raw_articles(raw_articles: list[dict]) -> list[dict]:
    """Sauvegarde les articles sans traitement LLM."""
    return [
        {
            "id": str(uuid.uuid4()),
            "title": raw["title"],
            "short_description": raw.get("raw_content", "")[:200],
            "long_description": raw.get("raw_content", "")[:1000],
            "article_url": raw["article_url"],
            "source_name": raw["source_name"],
            "source_id": raw["source_id"],
            "category": "Autre",
            "published_at": raw.get("published_at", datetime.utcnow().isoformat()),
            "collected_at": datetime.utcnow().isoformat(),
        }
        for raw in raw_articles
    ]
