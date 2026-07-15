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

from processors.gemini_processor import generate_synthesis, MAX_SYNTHESIS_INPUT

logger = logging.getLogger(__name__)

FETCH_TIMEOUT = 10                # secondes max par téléchargement d'article
FETCH_MAX_WORKERS = 8             # téléchargements parallèles
MAX_CHARS_PER_ARTICLE = 12_000    # plafond de texte intégral par article
MIN_TEXT_LENGTH = 200             # en dessous, le texte extrait est jugé inexploitable
RECENT_ARTICLES_POOL = 500        # articles récents lus avant filtrage
SYNTHESIS_CORPUS_SIZE = 100       # taille max du corpus de synthèse

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


def build_corpus(articles: list[dict]) -> list[dict]:
    """Attache à chaque article son texte intégral nettoyé (`synthesis_content`).

    Le budget de caractères est réparti équitablement entre les articles dans
    la limite du prompt de synthèse. En cas d'échec de téléchargement, l'article
    reste dans le corpus : generate_synthesis retombe sur sa description stockée.
    Le contenu téléchargé n'est jamais persisté en Firestore.
    """
    budget = min(MAX_CHARS_PER_ARTICLE, MAX_SYNTHESIS_INPUT // max(len(articles), 1))
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


def run_synthesis(db, global_settings: dict, model_priority: list[str]) -> None:
    """Génère la synthèse du jour et l'écrit dans `syntheses/{date}`."""
    interest = global_settings.get("interest", "").strip()
    if not interest:
        return

    source_ids = global_settings.get("synthesis_source_ids") or []
    categories = global_settings.get("synthesis_categories") or []
    logger.info(f"Génération de la synthèse pour : «{interest}»...")
    logger.info(f"Périmètre — sources : {', '.join(source_ids) if source_ids else 'toutes'} ; "
                f"thèmes : {', '.join(categories) if categories else 'tous'}")

    recent = db.collection("articles").order_by(
        "collected_at", direction="DESCENDING"
    ).limit(RECENT_ARTICLES_POOL).stream()
    # Filtrage en Python : Firestore n'autorise qu'un seul opérateur `in` par requête
    articles = filter_articles([doc.to_dict() for doc in recent], source_ids, categories)

    if not articles:
        logger.warning("Aucun article dans le périmètre sélectionné — pas d'appel LLM.")
        result = {
            "synthesis": "⚠️ Aucun article dans le périmètre sélectionné (sources/thèmes) — synthèse non générée.",
            "cited_ids": [],
        }
    else:
        result = generate_synthesis(build_corpus(articles), interest, model_priority)

    db.collection("syntheses").document(date.today().isoformat()).set({
        "interest": interest,
        "source_ids": source_ids,
        "categories": categories,
        "content": result["synthesis"],
        "cited_ids": result["cited_ids"],
        "articles_count": len(articles),
        "generated_at": datetime.utcnow().isoformat(),
    })
    logger.info("Synthèse sauvegardée.")
