import os
import uuid
import json
from datetime import datetime
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

DEFAULT_MODEL_PRIORITY = [
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
]

CATEGORIES = ["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"]

# Limites de contenu pour les prompts LLM
MAX_ARTICLE_CONTENT_FOR_BATCH = 1500    # chars max par article dans le prompt batch
MAX_GMAIL_CONTENT_FOR_PROMPT = 50_000  # chars max pour l'extraction Gmail
MAX_SYNTHESIS_INPUT = 180_000           # chars max pour le prompt de synthèse
MAX_REPORT_LOGS = 8_000                 # chars max des logs pour le rapport
FALLBACK_SHORT_DESC_LENGTH = 200        # chars max short_description (fallback brut)
FALLBACK_LONG_DESC_LENGTH = 1_000       # chars max long_description (fallback brut)
LLM_TEMPERATURE = 0.4                   # Température génération LLM
LLM_MAX_TOKENS_BATCH = 60_000           # Max tokens pour batch d'articles
LLM_MAX_TOKENS_SYNTHESIS = 8_000        # Max tokens pour la synthèse
TITLE_LOG_MAX_LENGTH = 60               # Longueur max des titres dans les logs

BATCH_PROMPT_BILINGUAL = """
Tu es journaliste tech bilingue (français / anglais).
Pour chaque article ci-dessous, produis simultanément deux fiches : une en français, une en anglais.

Règles communes :
- Conserve les noms propres, acronymes et sigles techniques en VO (OpenAI, AWS, GPT, Kubernetes, etc.)
- Sois factuel : cite technologies, entreprises, chiffres clés
- Ajoute du contexte pertinent si tu le connais
- N'invente aucun fait absent du contenu fourni

Version française :
- Français fluide et idiomatique (pas du mot-à-mot)
- Si un acronyme ou produit obscur apparaît, ajoute une glose entre parenthèses
- Ton journalistique précis et accessible

Version anglaise :
- Reformulation journalistique claire, pas le texte brut source
- Style concis à l'américaine (WSJ, TechCrunch)
- Reformule le titre si trop technique pour un public large

Le contenu peut être en anglais ou en français — adapte-toi à la langue source.

Pour chaque article, produis exactement ces champs :
- "title_fr" (max 12 mots) : titre percutant en français
- "title_en" (max 12 mots) : titre journalistique en anglais
- "short_description_fr" (1 phrase ~25 mots) : accroche en français
- "short_description_en" (1 phrase ~25 mots) : accroche en anglais
- "long_description_fr" (4 à 6 phrases) : analyse enrichie en français
- "long_description_en" (4 à 6 phrases) : analyse enrichie en anglais
- "category" : une valeur parmi {categories}
- "keywords_fr" : liste de 10 à 15 mots simples en français (technologies, entreprises, concepts, acteurs clés). Ex: ["intelligence artificielle", "sécurité", "OpenAI"]
- "keywords_en" : liste de 10 à 15 mots simples en anglais (mêmes concepts). Ex: ["artificial intelligence", "security", "OpenAI"]

Règles pour les mots-clés :
- Mots simples ou expressions courtes (1 à 3 mots maximum)
- Domaine exclusif : logiciel, technologie, informatique, numérique. Exclure les mots génériques non techniques (ex: "annonce", "nouveau", "article", "résultat", "stress")
- Privilégier : langages de programmation, frameworks, protocoles, plateformes, entreprises tech, concepts informatiques, acronymes techniques
- Pas de doublons entre FR et EN pour les termes identiques en VO (OpenAI, AWS, GPT, Kubernetes → dans les deux listes tels quels)

Articles à traiter :
{articles}

Réponds avec un tableau JSON de {count} objets dans le même ordre :
"""



def _format_articles_for_batch_prompt(raw_articles: list[dict]) -> str:
    """Formate les articles bruts pour le prompt batch Gemini."""
    return "".join(
        f"[{i}]\nTITRE: {raw['title']}\nCONTENU: {raw.get('raw_content', '')[:MAX_ARTICLE_CONTENT_FOR_BATCH]}\n\n"
        for i, raw in enumerate(raw_articles)
    )


def enrich_articles_batch(raw_articles: list[dict], model_priority: list[str] | None = None, thinking: bool = True, **_) -> list[dict]:
    """Traite tous les articles en un seul appel Gemini — produit FR + EN simultanément."""
    prompt = BATCH_PROMPT_BILINGUAL.format(
        count=len(raw_articles),
        articles=_format_articles_for_batch_prompt(raw_articles),
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

    # Traduction des catégories pour les mots-clés
    CATEGORY_FR_EN = {
        "IA": ("IA", "AI"), "DevOps": ("DevOps", "DevOps"), "Cloud": ("Cloud", "Cloud"),
        "Sécurité": ("Sécurité", "Security"), "Dev": ("Dev", "Dev"),
        "IT": ("IT", "IT"), "Autre": ("Autre", "Other"),
    }

    results = []
    for i, raw in enumerate(raw_articles):
        e = enriched_list[i] if i < len(enriched_list) else {}
        category = e.get("category", "Autre") if e.get("category") in CATEGORIES else "Autre"
        cat_fr, cat_en = CATEGORY_FR_EN.get(category, (category, category))

        kw_fr = e.get("keywords_fr", [])
        kw_en = e.get("keywords_en", [])
        if cat_fr and cat_fr not in kw_fr:
            kw_fr = [cat_fr] + kw_fr
        if cat_en and cat_en not in kw_en:
            kw_en = [cat_en] + kw_en

        results.append({
            "id": str(uuid.uuid4()),
            "title_fr": e.get("title_fr", raw["title"]),
            "title_en": e.get("title_en", raw["title"]),
            "title": e.get("title_fr", raw["title"]),  # compat
            "short_description_fr": e.get("short_description_fr", ""),
            "short_description_en": e.get("short_description_en", ""),
            "short_description": e.get("short_description_fr", ""),  # compat
            "long_description_fr": e.get("long_description_fr", ""),
            "long_description_en": e.get("long_description_en", ""),
            "long_description": e.get("long_description_fr", ""),  # compat
            "keywords_fr": kw_fr,
            "keywords_en": kw_en,
            "article_url": raw["article_url"],
            "source_name": raw["source_name"],
            "source_id": raw["source_id"],
            "category": category,
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
    "temperature": LLM_TEMPERATURE,
    "max_output_tokens": LLM_MAX_TOKENS_BATCH,
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


SYNTHESIS_PROMPT = """
Tu es un analyste tech expert en veille stratégique.

Centre d'intérêt : {interest}

Tu disposes ci-dessous d'un corpus de {count} articles tech récemment collectés,
chacun identifié par un ID unique.
Ton objectif : produire une synthèse de veille ciblée sur le centre d'intérêt indiqué,
en t'appuyant UNIQUEMENT sur les articles fournis.

Règles :
- Ne retiens que les articles pertinents par rapport au centre d'intérêt
- Si aucun article n'est pertinent, dis-le explicitement
- Structure ta réponse avec des émojis
- Référence les articles pertinents dans le texte avec leur titre
- Ton analytique, factuel, orienté décision

Structure attendue pour la synthèse :

**🔭 Vue d'ensemble**
En 2-3 phrases : l'état du sujet à la lumière des articles collectés.

**🔑 Points clés**
Les 3 à 5 insights les plus importants, chacun illustré par des articles du corpus.

**📈 Tendances émergentes**
Ce qui semble émerger ou évoluer sur ce sujet.

**❓ Ce qui manque**
Angles ou questions que les articles ne couvrent pas.

---
Corpus ({count} articles) :
{articles}

---
Réponds en JSON strict avec ces deux champs :
{{
  "synthesis": "le texte complet de la synthèse en markdown",
  "cited_ids": ["id_article_1", "id_article_2", ...]
}}
cited_ids doit contenir uniquement les IDs des articles que tu as réellement utilisés.
"""


def _usage_from_response(response) -> dict:
    """Extrait la consommation de tokens d'une réponse Gemini (0 si indisponible)."""
    meta = getattr(response, "usage_metadata", None)
    return {
        "prompt_tokens": getattr(meta, "prompt_token_count", 0) or 0,
        "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
        "total_tokens": getattr(meta, "total_token_count", 0) or 0,
    }


SELECTION_PROMPT = """
Tu es un assistant de veille technologique.

Centre d'intérêt : {interest}

Voici {count} articles (titre + résumé), chacun identifié par un ID unique.
Sélectionne UNIQUEMENT les articles réellement pertinents pour le centre d'intérêt,
au maximum {max_selected}. Sois strict : en cas de doute, écarte l'article.

Articles :
{articles}

Réponds en JSON strict : {{"selected_ids": ["id1", "id2", ...]}}
Si aucun article n'est pertinent, réponds {{"selected_ids": []}}.
"""


def select_relevant_articles(articles: list[dict], interest: str, model_priority: list[str] | None = None,
                             max_selected: int = 25) -> dict | None:
    """Étape 1 de la synthèse : sélectionne sur les seuls résumés les articles
    pertinents pour le centre d'intérêt (appel LLM léger, avant récupération
    du contenu intégral). Retourne {selected_ids, usage}, ou None si tous les
    modèles ont échoué."""
    import logging
    logger = logging.getLogger(__name__)

    articles_text = ""
    for a in articles:
        title = a.get("title_fr") or a.get("title", "")
        desc = (a.get("long_description_fr") or a.get("long_description", ""))[:400]
        articles_text += f"[ID:{a.get('id', '')}] {title}\n{desc}\n\n"

    config = {"temperature": 0.1, "max_output_tokens": 2_000, "response_mime_type": "application/json"}
    prompt = SELECTION_PROMPT.format(
        interest=interest,
        count=len(articles),
        max_selected=max_selected,
        articles=articles_text[:MAX_SYNTHESIS_INPUT],
    )

    models_to_try = model_priority or DEFAULT_MODEL_PRIORITY
    for model_name in models_to_try:
        try:
            m = genai.GenerativeModel(model_name, generation_config=config)
            response = m.generate_content(prompt)
            result = json.loads(response.text.strip())
            ids = [i for i in result.get("selected_ids", []) if isinstance(i, str)][:max_selected]
            usage = _usage_from_response(response)
            logger.info(f"Sélection par {model_name} — {len(ids)}/{len(articles)} article(s) retenus, "
                        f"{usage['total_tokens']} tokens")
            return {"selected_ids": ids, "usage": usage}
        except Exception as e:
            logger.warning(f"Sélection : {model_name} indisponible ({e.__class__.__name__}: {str(e)[:200]})")

    return None


def generate_synthesis(articles: list[dict], interest: str, model_priority: list[str] | None = None,
                       max_input_chars: int = MAX_SYNTHESIS_INPUT) -> dict:
    """Génère une synthèse ciblée. Retourne {synthesis, cited_ids, usage}."""
    import logging
    logger = logging.getLogger(__name__)

    _no_usage = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    if not interest.strip():
        return {"synthesis": "", "cited_ids": [], "usage": _no_usage}

    articles_text = ""
    for a in articles:
        article_id = a.get("id", "")
        title = a.get("title_fr") or a.get("title", "")
        # Texte intégral nettoyé si fourni (cf. processors/synthesis.py), sinon résumé stocké
        body = a.get("synthesis_content") or a.get("long_description_fr") or a.get("long_description", "")[:500]
        articles_text += f"[ID:{article_id}] {title}\n{body}\n\n"

    config = {"temperature": LLM_TEMPERATURE, "max_output_tokens": LLM_MAX_TOKENS_SYNTHESIS, "response_mime_type": "application/json"}
    prompt = SYNTHESIS_PROMPT.format(
        interest=interest,
        count=len(articles),
        articles=articles_text[:max_input_chars],
    )

    models_to_try = model_priority or DEFAULT_MODEL_PRIORITY
    errors = []
    for model_name in models_to_try:
        try:
            m = genai.GenerativeModel(model_name, generation_config=config)
            response = m.generate_content(prompt)
            result = json.loads(response.text.strip())
            usage = _usage_from_response(response)
            logger.info(f"Synthèse générée par {model_name} — {len(result.get('cited_ids', []))} articles cités, "
                        f"{usage['total_tokens']} tokens")
            return {
                "synthesis": result.get("synthesis", ""),
                "cited_ids": result.get("cited_ids", []),
                "usage": usage,
            }
        except Exception as e:
            detail = str(e)[:200]
            logger.warning(f"Synthèse : {model_name} indisponible ({e.__class__.__name__}: {detail})")
            errors.append(f"- **{model_name}** : {e.__class__.__name__} — {detail}")

    details = "\n".join(errors)
    return {
        "synthesis": f"⚠️ Synthèse indisponible — tous les modèles LLM ont échoué :\n{details}",
        "cited_ids": [],
        "usage": _no_usage,
    }


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
            logger.info(f"Rapport généré par {model_name}")
            return response.text.strip()
        except Exception as e:
            logger.warning(f"Rapport : modèle {model_name} indisponible ({e.__class__.__name__})")

    return "⚠️ Rapport indisponible — tous les modèles LLM sont hors quota."


def save_raw_articles(raw_articles: list[dict]) -> list[dict]:
    """Sauvegarde les articles sans traitement LLM (fallback quota)."""
    return [
        {
            "id": str(uuid.uuid4()),
            "title_fr": raw["title"],
            "title_en": raw["title"],
            "title": raw["title"],
            "short_description_fr": raw.get("raw_content", "")[:200],
            "short_description_en": raw.get("raw_content", "")[:200],
            "short_description": raw.get("raw_content", "")[:200],
            "long_description_fr": raw.get("raw_content", "")[:1000],
            "long_description_en": raw.get("raw_content", "")[:1000],
            "long_description": raw.get("raw_content", "")[:1000],
            "keywords_fr": [],
            "keywords_en": [],
            "article_url": raw["article_url"],
            "source_name": raw["source_name"],
            "source_id": raw["source_id"],
            "category": "Autre",
            "published_at": raw.get("published_at", datetime.utcnow().isoformat()),
            "collected_at": datetime.utcnow().isoformat(),
        }
        for raw in raw_articles
    ]
