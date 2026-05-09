import os
import uuid
import json
from datetime import datetime
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

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

CATEGORIES = ["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"]

BATCH_PROMPT_FR = """
Tu es journaliste tech francophone exigeant. Pour chaque article anglais ci-dessous, produis une version française qui :
- traduit avec un français fluide et idiomatique (pas du mot-à-mot)
- explicite ce qui est implicite : si un acronyme, une entreprise ou un produit obscur apparaît, ajoute une courte glose entre parenthèses
- conserve les noms propres et sigles techniques en VO (OpenAI, AWS, GPT, etc.)
- adopte un ton journalistique précis et accessible
- n'invente aucun fait absent du contenu fourni

Pour chaque article, produis ces champs :
- "title" (max 12 mots) : titre clair et percutant en français
- "short_description" (1 phrase ~25 mots) : pitch qui pose l'enjeu central
- "long_description" (4 à 6 phrases) : reformulation enrichie — contexte, mécanisme, implications
- "category" : une valeur parmi {categories}

Articles à traiter :
{articles}

Réponds avec un tableau JSON de {count} objets dans le même ordre :
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


def enrich_articles_batch(raw_articles: list[dict], translate: bool = True, model_priority: list[str] | None = None, thinking: bool = True) -> list[dict]:
    """Traite tous les articles en un seul appel Gemini, avec fallback sur les modèles suivants."""
    articles_text = ""
    for i, raw in enumerate(raw_articles):
        articles_text += (
            f"[{i}]\n"
            f"TITRE_EN: {raw['title']}\n"
            f"CONTENU_EN: {raw.get('raw_content', '')[:1500]}\n\n"
        )

    template = BATCH_PROMPT_FR if translate else BATCH_PROMPT_NO_TRANSLATION
    prompt = template.format(
        count=len(raw_articles),
        articles=articles_text,
        categories=", ".join(CATEGORIES),
    )

    models_to_try = model_priority or DEFAULT_MODEL_PRIORITY
    text = _call_llm(prompt, models_to_try, thinking=thinking)

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


GMAIL_EXTRACTION_PROMPT = """
Tu reçois le contenu simplifié d'une newsletter tech.
Elle contient des liens au format [titre](url) suivis d'une description.

Ta mission en une seule passe :
1. Retenir TOUS les liens qui pointent vers un article, un blog, une étude, un outil,
   une annonce produit ou un événement tech — même s'ils semblent courts ou peu détaillés.
   Ignorer UNIQUEMENT : désabonnement, parrainage, offres d'emploi, gestion de compte,
   liens vers les réseaux sociaux de la newsletter, publicités explicites.
2. Pour chaque lien retenu, produire une fiche enrichie en français.

Règles de rédaction :
- Traduis et reformule le titre en français, percutant (max 90 caractères)
- Écris les descriptions en français même si la source est en anglais
- Sois factuel : cite technologies, entreprises, chiffres clés
- Ajoute du contexte pertinent si tu le connais
- N'invente aucun fait absent du contenu fourni

Contenu de la newsletter :
---
{content}
---

Réponds UNIQUEMENT avec un tableau JSON valide. Si aucun lien pertinent, retourne [].
[
  {{
    "title": "titre reformulé en français (max 90 caractères)",
    "url": "URL de l'article telle quelle",
    "short_description": "accroche journalistique en 2 phrases maximum",
    "long_description": "analyse complète en 5 à 8 phrases : faits, contexte, enjeux, impact",
    "category": "une valeur parmi {categories}"
  }}
]
"""


BASE_GENERATION_CONFIG = {
    "temperature": 0.4,
    "max_output_tokens": 60000,
    "response_mime_type": "application/json",
}


def _call_llm(prompt: str, models_to_try: list[str], thinking: bool = True) -> str:
    """Appelle le LLM en cascade jusqu'au premier modèle disponible."""
    import logging
    logger = logging.getLogger(__name__)

    # thinking_budget: -1 = auto (modèle décide), 0 = désactivé
    thinking_config = {"thinking_budget": -1 if thinking else 0}
    logger.debug(f"Thinking mode : {'activé (auto)' if thinking else 'désactivé'}")

    last_error = None
    for model_name in models_to_try:
        try:
            logger.debug(f"Essai modèle : {model_name}")
            try:
                config = {**BASE_GENERATION_CONFIG, "thinking_config": thinking_config}
                m = genai.GenerativeModel(model_name, generation_config=config)
                response = m.generate_content(prompt)
            except Exception:
                # Fallback sans thinking si le modèle ne le supporte pas
                m = genai.GenerativeModel(model_name, generation_config=BASE_GENERATION_CONFIG)
                response = m.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            logger.info(f"Modèle utilisé avec succès : {model_name}")
            return text.strip()
        except Exception as e:
            logger.warning(f"Modèle {model_name} indisponible : {e.__class__.__name__}")
            last_error = e
    raise last_error or RuntimeError("Aucun modèle disponible")


def extract_and_enrich_gmail(
    email_contents: list[str],
    source: dict,
    model_priority: list[str] | None = None,
) -> list[dict]:
    """Traite chaque email individuellement pour maximiser la couverture."""
    import logging
    logger = logging.getLogger(__name__)

    if not email_contents:
        return []

    models_to_try = model_priority or DEFAULT_MODEL_PRIORITY
    all_articles = []

    for i, content in enumerate(email_contents, 1):
        logger.info(f"  Traitement email {i}/{len(email_contents)} via LLM...")
        prompt = GMAIL_EXTRACTION_PROMPT.format(
            content=content[:50000],
            categories=", ".join(CATEGORIES),
        )
        try:
            text = _call_llm(prompt, models_to_try)
            articles = json.loads(text)
            logger.info(f"  → {len(articles)} article(s) extrait(s)")
            for a in articles:
                if a.get("url") and a.get("title"):
                    all_articles.append({
                        "id": str(uuid.uuid4()),
                        "title": a.get("title", ""),
                        "short_description": a.get("short_description", ""),
                        "long_description": a.get("long_description", ""),
                        "article_url": a.get("url", ""),
                        "source_name": source["name"],
                        "source_id": source["id"],
                        "category": a.get("category", "Autre") if a.get("category") in CATEGORIES else "Autre",
                        "published_at": datetime.utcnow().isoformat(),
                        "collected_at": datetime.utcnow().isoformat(),
                    })
        except Exception as e:
            logger.error(f"  Échec traitement email {i} : {e.__class__.__name__}")

    logger.info(f"Total Gmail : {len(all_articles)} article(s) extrait(s) sur {len(email_contents)} email(s)")
    return all_articles


REPORT_PROMPT = """
Tu es un assistant chargé de rédiger un rapport de synthèse clair et concis
d'une exécution de collecte de veille technologique.

Voici les logs bruts de l'exécution :
---
{logs}
---

Rédige un rapport structuré en français destiné à l'administrateur de l'application.
Le rapport doit être lisible en 30 secondes. Utilise des émojis pour faciliter
la lecture visuelle.

Structure attendue :

**Sources sollicitées**
Liste chaque source (nom, type web/gmail), avec indication active/inactive.

**Collecte emails** (si source Gmail présente)
Pour chaque expéditeur : nombre d'emails trouvés, nombre d'articles extraits
par email, total retenu après déduplication.

**Traitement LLM**
Indique quel modèle a effectivement traité les articles, ou si le fallback
brut a été utilisé (et pourquoi : quota, modèle introuvable...).

**Résultat**
Nombre d'articles nouveaux sauvegardés. Signale les doublons ignorés.

**Anomalies**
Erreurs rencontrées (quota épuisé, modèle non trouvé, source inaccessible...).
Si aucune anomalie, indique-le explicitement.

**Recommandations** (si pertinent)
Suggestions courtes si des problèmes récurrents sont détectés.

Sois factuel, concis. N'invente rien qui ne figure pas dans les logs.
"""


def generate_run_report(logs: str, model_priority: list[str] | None = None) -> str:
    """Génère un rapport de synthèse de l'exécution via LLM."""
    import logging
    logger = logging.getLogger(__name__)

    prompt = REPORT_PROMPT.format(logs=logs[:8000])
    models_to_try = model_priority or DEFAULT_MODEL_PRIORITY

    for model_name in models_to_try:
        try:
            m = genai.GenerativeModel(model_name)
            response = m.generate_content(prompt)
            logger.debug(f"Rapport généré par {model_name}")
            return response.text.strip()
        except Exception as e:
            logger.debug(f"Rapport : modèle {model_name} indisponible ({e.__class__.__name__})")

    return "⚠️ Rapport indisponible — tous les modèles LLM sont hors quota."


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
