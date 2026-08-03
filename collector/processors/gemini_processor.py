import os
import uuid
import json
import logging
from datetime import datetime
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# Cascade : le moins cher d'abord **parmi les modèles qui tiennent la qualité
# attendue**, puis montée d'un cran à chaque refus. Les Gemma sont les moins
# chers du catalogue mais produisent des descriptions trop courtes pour la
# fiche article (4 à 6 phrases attendues) — ils restent en repli de dernier
# recours, quand aucun modèle Gemini n'est disponible.
# Coûts en $ par million de tokens (entrée / sortie).
DEFAULT_MODEL_PRIORITY = [
    "gemini-3.1-flash-lite",   # 0,25 $ / 1,50 $ — GA, cheval de trait
    "gemini-3-flash-preview",  # 0,25 $ / 1,50 $ — même prix, preview
    "gemini-3.5-flash",        # 1,50 $ / 9,00 $ — qualité max
    "gemma-4-31b-it",          # 0,09 $ / 0,34 $ — repli
    "gemma-4-26b-a4b-it",      # 0,07 $ / 0,30 $ — dernier recours
]

CATEGORIES = ["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"]


# Limites de contenu pour les prompts LLM
# 1500 caractères ne suffisaient pas à nourrir une analyse de 4 à 6 phrases :
# le modèle n'avait pas assez de matière et produisait des descriptions courtes.
# À 4000, le surcoût est de l'ordre de 0,006 $ par run sur Flash Lite.
MAX_ARTICLE_CONTENT_FOR_BATCH = 4000    # chars max par article dans le prompt batch
MAX_GMAIL_CONTENT_FOR_PROMPT = 50_000  # chars max pour l'extraction Gmail
MAX_SYNTHESIS_INPUT = 180_000           # chars max pour le prompt de synthèse
MAX_REPORT_LOGS = 8_000                 # chars max des logs pour le rapport
FALLBACK_SHORT_DESC_LENGTH = 200        # chars max short_description (fallback brut)
FALLBACK_LONG_DESC_LENGTH = 1_000       # chars max long_description (fallback brut)
LLM_TEMPERATURE = 0.4                   # Température génération LLM
LLM_MAX_TOKENS_BATCH = 60_000           # Max tokens pour batch d'articles
LLM_MAX_TOKENS_SYNTHESIS = 8_000        # Max tokens pour la synthèse
TITLE_LOG_MAX_LENGTH = 60               # Longueur max des titres dans les logs
MAX_ERROR_DETAIL = 300                  # chars max du message d'erreur conservé dans les logs

logger = logging.getLogger(__name__)


def resolve_model_priority(stored: list[str] | None) -> list[str]:
    """Retourne l'ordre à appliquer — **littéralement celui choisi dans l'admin**.

    Aucune réécriture : pas de tri, pas d'insertion de modèle, pas de purge.
    L'ordre stocké en Firestore par la page admin fait autorité et est
    sollicité tel quel à chaque appel LLM. `DEFAULT_MODEL_PRIORITY` ne sert
    qu'à amorcer un projet neuf, quand aucun ordre n'a encore été choisi.

    Un modèle inconnu du catalogue est signalé mais tout de même sollicité :
    c'est un choix de l'administrateur, pas au code de le censurer.
    """
    if not stored:
        logger.info("Aucun ordre de modèles en base — amorçage sur la liste par défaut.")
        return list(DEFAULT_MODEL_PRIORITY)

    inconnus = [m for m in stored if m not in DEFAULT_MODEL_PRIORITY]
    if inconnus:
        logger.warning(
            f"Modèle(s) hors catalogue dans l'ordre choisi : {', '.join(inconnus)}. "
            "Ils seront sollicités quand même — les retirer depuis la page admin "
            "s'ils n'existent plus."
        )
    return list(stored)


# Diagnostic des échecs LLM. Sans ça, tous les échecs remontaient comme
# « quota épuisé » alors que la cause réelle est le plus souvent ailleurs
# (modèle inconnu de la version d'API appelée, paramètre non supporté, clé
# restreinte). Ne jamais parler de quota sans un 429 effectivement reçu.
_HTTP_DIAGNOSTIC = {
    400: "requête refusée par l'API — paramètre non supporté par ce modèle",
    401: "clé API absente ou invalide",
    403: "accès refusé — API non activée sur le projet, ou clé restreinte",
    404: "modèle introuvable sur la version d'API appelée",
    429: "DÉBIT OU QUOTA DÉPASSÉ (429) — réessayer plus tard",
    500: "erreur interne Google",
    503: "modèle temporairement surchargé",
}

# Google renvoie aussi un 429 quand le compte lui-même est bloqué (solde
# prépayé épuisé, facturation suspendue). Ce n'est PAS un dépassement de
# quota : les compteurs de la console restent au vert, et aucun modèle de la
# cascade ne peut aboutir. Inutile d'essayer les suivants.
#
# ATTENTION : ne jamais chercher le mot « billing » seul. TOUS les 429 de
# Gemini contiennent « check your plan and billing details », y compris un
# simple dépassement de débit — ce marqueur trop large faisait passer une
# limite de débit pour un compte suspendu et interrompait la cascade à tort.
_BILLING_MARKERS = (
    "prepayment credits",
    "credits are depleted",
    "billing account",
    "consumer_suspended",
)

# Signaux d'un dépassement ordinaire. Ils l'emportent sur les marqueurs
# ci-dessus : un message qui nomme une métrique de quota décrit un débit
# dépassé, pas une facturation suspendue — la cascade doit monter d'un cran.
_RATE_LIMIT_MARKERS = (
    "quota exceeded for metric",
    "exceeded your current quota",
    "rate limit",
)

BILLING_DIAGNOSTIC = (
    "FACTURATION BLOQUÉE (429) — ce n'est pas un dépassement de quota : "
    "le solde prépayé du projet est épuisé ou la facturation est suspendue. "
    "Recharger le projet sur https://ai.studio/projects"
)


def _is_account_level_failure(exc: Exception, code: int | None) -> bool:
    """Vrai si l'échec vient du compte (facturation) et non du modèle appelé.

    En cas de doute, on répond False : mieux vaut monter d'un cran pour rien
    que d'interrompre la cascade sur un simple dépassement de débit.
    """
    if code != 429:
        return False
    message = str(exc).lower()
    if any(marker in message for marker in _RATE_LIMIT_MARKERS):
        return False
    return any(marker in message for marker in _BILLING_MARKERS)


def _is_quota_failure(exc: Exception, code: int | None) -> bool:
    """Vrai si le modèle a refusé pour dépassement de quota ou de débit.

    C'est le cas nominal de la cascade : on monte d'un cran en gamme, donc en
    prix. À distinguer d'une anomalie (modèle inconnu, requête invalide,
    réponse illisible), qui fait aussi monter d'un cran mais signale un défaut
    à corriger — et du blocage de compte, où aucun modèle ne peut aboutir.
    """
    return code == 429 and not _is_account_level_failure(exc, code)


def _http_code(exc: Exception) -> int | None:
    """Code HTTP porté par une exception google-api-core, s'il y en a un."""
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    code = getattr(getattr(exc, "response", None), "status_code", None)
    return code if isinstance(code, int) else None


def _describe_llm_error(exc: Exception) -> str:
    """Rend l'échec d'un appel Gemini lisible : code HTTP, diagnostic, message brut.

    Le message brut est toujours conservé — c'est lui qui permet de trancher
    entre un vrai dépassement de quota et une erreur de configuration.
    """
    message = str(exc).strip().replace("\n", " ")[:MAX_ERROR_DETAIL]
    code = _http_code(exc)

    if _is_account_level_failure(exc, code):
        diagnostic = BILLING_DIAGNOSTIC
    else:
        diagnostic = _HTTP_DIAGNOSTIC.get(code) if code is not None else None

    prefix = f"HTTP {code} — {diagnostic}" if diagnostic else exc.__class__.__name__
    return f"{prefix} : {message}"


def _entete_echec(errors: list[str], interrompu: bool) -> str:
    """En-tête honnête d'un message de repli : ne pas dire « tous les modèles »
    quand la cascade a été coupée au premier."""
    if interrompu:
        return "le compte est bloqué, cascade interrompue au premier modèle"
    return f"les {len(errors)} modèle(s) de la cascade ont échoué"


def _log_montee(etape: str, model_name: str, exc: Exception, reason: str) -> None:
    """Journalise la montée d'un cran en distinguant le cas nominal du défaut."""
    motif = "dépassement" if _is_quota_failure(exc, _http_code(exc)) else "anomalie"
    logger.warning(f"{etape} : {motif} sur {model_name} — montée d'un cran : {reason}")


def _stop_cascade(exc: Exception, etape: str, restants: list[str]) -> bool:
    """Vrai si l'échec est au niveau du compte : les modèles suivants échoueront pareil."""
    if not _is_account_level_failure(exc, _http_code(exc)):
        return False
    if restants:
        logger.error(
            f"{etape} : échec au niveau du compte — cascade interrompue, "
            f"{len(restants)} modèle(s) non essayé(s) ({', '.join(restants)}). "
            "Aucun modèle ne peut aboutir tant que la facturation est bloquée."
        )
    return True


class LLMCascadeError(RuntimeError):
    """Tous les modèles de la cascade ont échoué — porte le détail par modèle."""

    def __init__(self, failures: list[tuple[str, str]], aborted: bool = False):
        self.failures = failures
        self.aborted = aborted
        if not failures:
            super().__init__("aucun modèle LLM configuré dans model_priority")
            return
        detail = " | ".join(f"{model} → {reason}" for model, reason in failures)
        entete = (
            "cascade interrompue — le blocage vient du compte, pas du modèle"
            if aborted else f"les {len(failures)} modèle(s) de la cascade ont échoué"
        )
        super().__init__(f"{entete} : {detail}")


def _extract_response_text(response, model_name: str) -> str:
    """Lit le texte d'une réponse Gemini en explicitant les réponses vides.

    Une réponse tronquée (thinking qui consomme tout le budget de sortie) ou
    bloquée par les filtres de sécurité ne porte aucun texte : `response.text`
    lève alors une erreur opaque. On la remplace par la vraie raison.
    """
    try:
        return response.text.strip()
    except Exception as exc:
        candidates = getattr(response, "candidates", None) or []
        finish_reason = getattr(candidates[0], "finish_reason", None) if candidates else None
        feedback = getattr(response, "prompt_feedback", None)
        raise RuntimeError(
            f"{model_name} a répondu sans texte exploitable "
            f"(finish_reason={finish_reason}, prompt_feedback={feedback}) : "
            f"{str(exc)[:MAX_ERROR_DETAIL]}"
        ) from exc


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
- "short_description_fr" (1 phrase de 25 mots minimum) : accroche en français
- "short_description_en" (1 phrase de 25 mots minimum) : accroche en anglais
- "long_description_fr" (4 à 6 phrases, 500 caractères minimum) : analyse enrichie en français
- "long_description_en" (4 à 6 phrases, 500 caractères minimum) : analyse enrichie en anglais

Les longueurs minimales sont impératives : une description trop courte est
inexploitable. Développe le contexte et les enjeux pour les atteindre, sans
jamais inventer de fait absent du contenu fourni.
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


_thinking_unsupported_logged = False


def _generate(model_name: str, prompt: str, thinking: bool | None):
    """Un appel Gemini. thinking=None retire complètement `thinking_config`."""
    config = dict(BASE_GENERATION_CONFIG)
    if thinking is not None:
        # thinking_budget: -1 = auto (modèle décide), 0 = désactivé
        config["thinking_config"] = {"thinking_budget": -1 if thinking else 0}
    return genai.GenerativeModel(model_name, generation_config=config).generate_content(prompt)


def _call_llm(prompt: str, models_to_try: list[str], thinking: bool = True) -> str:
    """Appelle les modèles dans l'ordre reçu — trié du moins cher au plus cher.

    On monte d'un cran (donc en prix) dès qu'un modèle refuse. Le motif de la
    montée est journalisé distinctement :
    - dépassement de quota ou de débit → cas nominal, c'est le rôle de la cascade ;
    - anomalie (modèle inconnu, requête invalide, réponse illisible ou non-JSON)
      → on monte aussi, mais c'est un défaut à corriger ;
    - blocage du compte → arrêt immédiat, aucun modèle ne peut aboutir.

    La validité du JSON est vérifiée **ici** : une réponse malformée doit faire
    monter d'un cran, pas faire échouer tout le run en aval.
    """
    global _thinking_unsupported_logged

    logger.debug(f"Thinking mode : {'activé (auto)' if thinking else 'désactivé'}")
    failures: list[tuple[str, str]] = []

    for model_name in models_to_try:
        try:
            logger.debug(f"Essai modèle : {model_name}")
            try:
                response = _generate(model_name, prompt, thinking=thinking)
            except ValueError as exc:
                # Le SDK installé ignore `thinking_config` : il rejette la config
                # avant tout appel réseau. On réessaie sans, mais on le dit — sinon
                # le réglage « thinking » de l'admin est silencieusement sans effet.
                if "thinking_config" not in str(exc):
                    raise
                if not _thinking_unsupported_logged:
                    logger.warning(
                        "Le SDK google-generativeai installé ne supporte pas "
                        "`thinking_config` — le réglage « thinking » de l'admin est "
                        "sans effet. Appels effectués sans ce paramètre."
                    )
                    _thinking_unsupported_logged = True
                response = _generate(model_name, prompt, thinking=None)

            text = _extract_response_text(response, model_name)
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            text = text.strip()

            # Un JSON illisible est un échec du modèle, pas du run : on doit
            # pouvoir monter d'un cran. Sans ça, un petit modèle bavard fait
            # tomber toute la collecte en articles bruts.
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"réponse non conforme au JSON demandé ({exc.msg} "
                    f"ligne {exc.lineno}, colonne {exc.colno})"
                ) from exc

            logger.info(f"Modèle utilisé avec succès : {model_name}")
            return text
        except Exception as exc:
            reason = _describe_llm_error(exc)
            _log_montee("Cascade LLM", model_name, exc, reason)
            failures.append((model_name, reason))

            if _stop_cascade(exc, "Cascade LLM", models_to_try[len(failures):]):
                raise LLMCascadeError(failures, aborted=True) from exc

    raise LLMCascadeError(failures)


def extract_and_enrich_gmail(
    email_contents: list[str],
    source: dict,
    model_priority: list[str] | None = None,
) -> list[dict]:
    """Traite chaque email individuellement pour maximiser la couverture."""
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
            logger.error(f"  Échec traitement email {i} — {_describe_llm_error(e)}")

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
    for rang, model_name in enumerate(models_to_try):
        try:
            m = genai.GenerativeModel(model_name, generation_config=config)
            response = m.generate_content(prompt)
            result = json.loads(_extract_response_text(response, model_name))
            ids = [i for i in result.get("selected_ids", []) if isinstance(i, str)][:max_selected]
            usage = _usage_from_response(response)
            logger.info(f"Sélection par {model_name} — {len(ids)}/{len(articles)} article(s) retenus, "
                        f"{usage['total_tokens']} tokens")
            return {"selected_ids": ids, "usage": usage}
        except Exception as e:
            _log_montee("Sélection", model_name, e, _describe_llm_error(e))
            if _stop_cascade(e, "Sélection", models_to_try[rang + 1:]):
                break

    return None


def generate_synthesis(articles: list[dict], interest: str, model_priority: list[str] | None = None,
                       max_input_chars: int = MAX_SYNTHESIS_INPUT) -> dict:
    """Génère une synthèse ciblée. Retourne {synthesis, cited_ids, usage}."""
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
    interrompu = False
    for model_name in models_to_try:
        try:
            m = genai.GenerativeModel(model_name, generation_config=config)
            response = m.generate_content(prompt)
            result = json.loads(_extract_response_text(response, model_name))
            usage = _usage_from_response(response)
            logger.info(f"Synthèse générée par {model_name} — {len(result.get('cited_ids', []))} articles cités, "
                        f"{usage['total_tokens']} tokens")
            return {
                "synthesis": result.get("synthesis", ""),
                "cited_ids": result.get("cited_ids", []),
                "usage": usage,
            }
        except Exception as e:
            reason = _describe_llm_error(e)
            _log_montee("Synthèse", model_name, e, reason)
            errors.append(f"- **{model_name}** : {reason}")
            if _stop_cascade(e, "Synthèse", models_to_try[len(errors):]):
                interrompu = True
                break

    details = "\n".join(errors)
    return {
        "synthesis": f"⚠️ Synthèse indisponible — {_entete_echec(errors, interrompu)} :\n{details}",
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
brut a été utilisé. Si des modèles ont échoué, recopie la cause EXACTE telle
qu'elle figure dans les logs (code HTTP et message). N'attribue jamais un
échec à un dépassement de quota si les logs ne montrent pas un code 429.

**Résultat**
Nombre d'articles nouveaux sauvegardés. Signale les doublons ignorés.

**Anomalies**
Erreurs rencontrées, reprises littéralement des logs (code HTTP + message).
N'invente pas de cause : si les logs ne la donnent pas, écris-le.
Si aucune anomalie, indique-le explicitement.

**Recommandations** (si pertinent)
Suggestions courtes si des problèmes récurrents sont détectés.

Sois factuel, concis. N'invente rien qui ne figure pas dans les logs.
"""


def generate_run_report(logs: str, model_priority: list[str] | None = None) -> str:
    """Génère un rapport de synthèse de l'exécution via LLM."""
    prompt = REPORT_PROMPT.format(logs=logs[:8000])
    models_to_try = model_priority or DEFAULT_MODEL_PRIORITY

    errors = []
    interrompu = False
    for model_name in models_to_try:
        try:
            m = genai.GenerativeModel(model_name)
            response = m.generate_content(prompt)
            logger.info(f"Rapport généré par {model_name}")
            return _extract_response_text(response, model_name)
        except Exception as e:
            reason = _describe_llm_error(e)
            _log_montee("Rapport", model_name, e, reason)
            errors.append(f"- **{model_name}** : {reason}")
            if _stop_cascade(e, "Rapport", models_to_try[len(errors):]):
                interrompu = True
                break

    details = "\n".join(errors) or "aucun modèle configuré dans model_priority."
    return f"⚠️ Rapport indisponible — {_entete_echec(errors, interrompu)} :\n{details}"


def save_raw_articles(raw_articles: list[dict]) -> list[dict]:
    """Sauvegarde les articles sans traitement LLM (fallback si la cascade échoue)."""
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
