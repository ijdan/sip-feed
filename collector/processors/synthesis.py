"""Traitement de la synthèse du jour.

Isolé du pipeline principal du collector : l'étape synthèse de `run()`
(main.py) délègue entièrement ici. Le traitement :
1. lit le périmètre saisi dans l'IHM admin (`synthesis_source_ids`,
   `synthesis_categories` dans `settings/global`) et filtre les articles
   récents en conséquence ;
2. télécharge le contenu intégral de chaque article du corpus et le réduit
   à du texte brut (suppression HTML, CSS, scripts, images) ;
3. envoie le tout au LLM avec le prompt de synthèse et le centre d'intérêt,
   puis écrit le résultat dans `syntheses/{date}`.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date

import httpx
from bs4 import BeautifulSoup, Comment

from processors.gemini_processor import generate_synthesis, select_relevant_articles, MAX_SYNTHESIS_INPUT

logger = logging.getLogger(__name__)

FETCH_TIMEOUT = 10                # secondes max par téléchargement d'article
FETCH_MAX_WORKERS = 8             # téléchargements parallèles
MAX_CHARS_PER_ARTICLE = 12_000    # plafond de texte intégral par article
MIN_TEXT_LENGTH = 200             # en dessous, le texte extrait est jugé inexploitable
RECENT_ARTICLES_POOL = 500        # articles récents lus avant filtrage
SYNTHESIS_CORPUS_SIZE = 100       # taille max du corpus de synthèse
SELECTION_MIN_CORPUS = 8          # en dessous, la pré-sélection LLM coûterait plus qu'elle n'économise
SELECTION_MAX_ARTICLES = 25       # articles max retenus par la pré-sélection

# Balises sans valeur textuelle pour la synthèse (mise en page, médias, code embarqué)
_STRIPPED_TAGS = ["script", "style", "img", "svg", "picture", "video", "audio",
                  "iframe", "noscript", "nav", "header", "footer", "form", "aside"]


def extract_text(html: str) -> str:
    """Réduit une page HTML à son texte brut : ni balise, ni CSS, ni script, ni image."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_STRIPPED_TAGS):
        tag.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    lines = (" ".join(line.split()) for line in soup.get_text(separator="\n").splitlines())
    return "\n".join(line for line in lines if line)


def fetch_article_text(url: str) -> str | None:
    """Télécharge un article et retourne son texte nettoyé, ou None si inexploitable."""
    try:
        response = httpx.get(
            url,
            timeout=FETCH_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TechNewsBot/1.0)"},
        )
        response.raise_for_status()
    except Exception as e:
        logger.warning(f"  Contenu inaccessible ({e.__class__.__name__}) : {url}")
        return None

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type and "text" not in content_type:
        logger.warning(f"  Contenu non textuel ({content_type or 'type inconnu'}) : {url}")
        return None

    text = extract_text(response.text)
    if len(text) < MIN_TEXT_LENGTH:
        logger.warning(f"  Texte extrait trop court ({len(text)} caractères) : {url}")
        return None
    return text


def filter_articles(articles: list[dict], source_ids: list[str], categories: list[str]) -> list[dict]:
    """Applique le périmètre admin. Liste vide = aucune restriction (rétrocompat)."""
    selected = [
        a for a in articles
        if (not source_ids or a.get("source_id") in source_ids)
        and (not categories or a.get("category") in categories)
    ]
    return selected[:SYNTHESIS_CORPUS_SIZE]


def build_corpus(articles: list[dict], max_input_chars: int = MAX_SYNTHESIS_INPUT) -> list[dict]:
    """Attache à chaque article son texte intégral nettoyé (`synthesis_content`).

    Le budget de caractères est réparti équitablement entre les articles dans
    la limite du prompt de synthèse. En cas d'échec de téléchargement, l'article
    reste dans le corpus : generate_synthesis retombe sur sa description stockée.
    Le contenu téléchargé n'est jamais persisté en Firestore.
    """
    budget = min(MAX_CHARS_PER_ARTICLE, max_input_chars // max(len(articles), 1))
    with ThreadPoolExecutor(max_workers=FETCH_MAX_WORKERS) as pool:
        texts = list(pool.map(lambda a: fetch_article_text(a.get("article_url", "")), articles))

    fetched = 0
    for article, text in zip(articles, texts):
        if text:
            article["synthesis_content"] = text[:budget]
            fetched += 1
    logger.info(
        f"Contenu intégral récupéré pour {fetched}/{len(articles)} article(s) "
        f"(budget {budget} caractères/article) — fallback résumé pour les autres."
    )
    return articles


def _add_usage(total: dict, usage: dict | None) -> dict:
    """Cumule la consommation de tokens de plusieurs appels LLM."""
    for key in total:
        total[key] += (usage or {}).get(key, 0)
    return total


def run_synthesis(db, global_settings: dict, model_priority: list[str],
                  new_articles: list[dict] | None = None) -> None:
    """Génère la synthèse du jour et l'écrit dans `syntheses/{date}`.

    `new_articles` : articles ajoutés par le run en cours. Si la synthèse du
    jour existe déjà pour le même périmètre et qu'aucun nouvel article n'y
    entre, la génération est sautée (aucun token consommé).
    """
    interest = global_settings.get("interest", "").strip()
    if not interest:
        return

    source_ids = global_settings.get("synthesis_source_ids") or []
    categories = global_settings.get("synthesis_categories") or []
    max_input_chars = int(global_settings.get("synthesis_max_input_chars") or MAX_SYNTHESIS_INPUT)
    today_ref = db.collection("syntheses").document(date.today().isoformat())

    # Levier économie n°1 : ne pas régénérer si rien n'a changé depuis la
    # synthèse du jour (même centre d'intérêt, même périmètre, aucun nouvel
    # article dans le périmètre).
    if new_articles is not None:
        snapshot = today_ref.get()
        if snapshot.exists:
            previous = snapshot.to_dict() or {}
            same_scope = (previous.get("interest") == interest
                          and previous.get("source_ids", []) == source_ids
                          and previous.get("categories", []) == categories)
            # Une synthèse en échec (⚠️ quota LLM…) doit être retentée au run suivant
            previous_failed = str(previous.get("content", "")).startswith("⚠️")
            if same_scope and not previous_failed and not filter_articles(new_articles, source_ids, categories):
                logger.info("Synthèse du jour déjà à jour — aucun nouvel article dans le périmètre, "
                            "aucun appel LLM.")
                return

    logger.info(f"Génération de la synthèse pour : «{interest}»...")
    logger.info(f"Périmètre — sources : {', '.join(source_ids) if source_ids else 'toutes'} ; "
                f"thèmes : {', '.join(categories) if categories else 'tous'} ; "
                f"plafond prompt : {max_input_chars} caractères")

    recent = db.collection("articles").order_by(
        "collected_at", direction="DESCENDING"
    ).limit(RECENT_ARTICLES_POOL).stream()
    # Filtrage en Python : Firestore n'autorise qu'un seul opérateur `in` par requête
    articles = filter_articles([doc.to_dict() for doc in recent], source_ids, categories)

    usage = {"prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    corpus: list[dict] = articles
    result = None

    if not articles:
        logger.warning("Aucun article dans le périmètre sélectionné — pas d'appel LLM.")
        corpus = []
        result = {
            "synthesis": "⚠️ Aucun article dans le périmètre sélectionné (sources/thèmes) — synthèse non générée.",
            "cited_ids": [],
        }
    else:
        # Levier économie n°2 : pré-sélection sur les seuls résumés, le contenu
        # intégral n'est téléchargé et envoyé que pour les articles retenus.
        fetch_full = True
        if len(articles) > SELECTION_MIN_CORPUS:
            selection = select_relevant_articles(articles, interest, model_priority, SELECTION_MAX_ARTICLES)
            if selection is None:
                logger.warning("Pré-sélection LLM indisponible — synthèse sur les résumés uniquement "
                               "(pas de contenu intégral).")
                fetch_full = False
            else:
                _add_usage(usage, selection["usage"])
                selected_ids = set(selection["selected_ids"])
                selected = [a for a in articles if a.get("id") in selected_ids]
                if not selected:
                    logger.info("Pré-sélection : aucun article pertinent — pas de second appel LLM.")
                    corpus = []
                    result = {
                        "synthesis": f"ℹ️ Aucun article du périmètre jugé pertinent pour «{interest}» "
                                     "— synthèse non générée.",
                        "cited_ids": [],
                    }
                else:
                    corpus = selected

        if result is None:
            if fetch_full:
                corpus = build_corpus(corpus, max_input_chars)
            result = generate_synthesis(corpus, interest, model_priority, max_input_chars)
            _add_usage(usage, result.get("usage"))

    # Levier économie n°4 : consommation réelle tracée (logs → rapport de run,
    # champ `usage` → IHM admin).
    logger.info(f"Consommation LLM synthèse — {usage['total_tokens']} tokens "
                f"(prompt : {usage['prompt_tokens']}, sortie : {usage['output_tokens']}).")

    today_ref.set({
        "interest": interest,
        "source_ids": source_ids,
        "categories": categories,
        "content": result["synthesis"],
        "cited_ids": result["cited_ids"],
        "articles_count": len(corpus),
        "perimeter_count": len(articles),
        "usage": usage,
        "generated_at": datetime.utcnow().isoformat(),
    })
    logger.info("Synthèse sauvegardée.")
