"""Tests fonctionnels — synthèse du jour (périmètre admin + contenu intégral).

Le LLM (genai.GenerativeModel) et les téléchargements HTTP sont mockés :
aucun quota Gemini ni accès réseau consommés.
"""
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Charger le .env du collector pour GEMINI_API_KEY
COLLECTOR_DIR = Path(__file__).resolve().parents[1] / "collector"
load_dotenv(COLLECTOR_DIR / ".env")

# Fournir une clé factice si absente (pour les tests avec mock)
if not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = "AIza_TEST_KEY_FOR_UNIT_TESTS"

sys.path.insert(0, str(COLLECTOR_DIR))

ARTICLES = [
    {"id": "a1", "title_fr": "Article IA TLDR", "source_id": "tldr", "category": "IA",
     "article_url": "https://example.com/a1", "long_description_fr": "Résumé stocké de a1."},
    {"id": "a2", "title_fr": "Article Dev HN", "source_id": "hn", "category": "Dev",
     "article_url": "https://example.com/a2", "long_description_fr": "Résumé stocké de a2."},
    {"id": "a3", "title_fr": "Article Cloud TLDR", "source_id": "tldr", "category": "Cloud",
     "article_url": "https://example.com/a3", "long_description_fr": "Résumé stocké de a3."},
]


# ---------------------------------------------------------------------------
# Filtrage du périmètre (US-SYN-102)
# ---------------------------------------------------------------------------

def test_filter_articles_by_source_and_category():
    """Seuls les articles des sources ET thèmes sélectionnés sont retenus."""
    from processors.synthesis import filter_articles
    result = filter_articles(ARTICLES, source_ids=["tldr"], categories=["IA"])
    assert [a["id"] for a in result] == ["a1"]


def test_filter_articles_empty_selection_keeps_all():
    """Sélection vide = aucune restriction (rétrocompat comportement actuel)."""
    from processors.synthesis import filter_articles
    result = filter_articles(ARTICLES, source_ids=[], categories=[])
    assert [a["id"] for a in result] == ["a1", "a2", "a3"]


def test_filter_articles_caps_corpus_size():
    """Le corpus est plafonné à SYNTHESIS_CORPUS_SIZE articles."""
    from processors.synthesis import filter_articles, SYNTHESIS_CORPUS_SIZE
    many = [{"id": f"a{i}", "source_id": "s", "category": "IA"} for i in range(SYNTHESIS_CORPUS_SIZE + 20)]
    assert len(filter_articles(many, [], [])) == SYNTHESIS_CORPUS_SIZE


# ---------------------------------------------------------------------------
# Nettoyage HTML (US-SYN-103)
# ---------------------------------------------------------------------------

def test_extract_text_strips_html_css_scripts_images():
    """Le texte extrait ne contient ni balise, ni CSS, ni script, ni image."""
    from processors.synthesis import extract_text
    html = """
    <html><head><style>.big { font-size: 99px; }</style>
    <script>alert("xss")</script></head>
    <body><nav>Menu du site</nav><header>Bannière</header>
    <!-- commentaire caché -->
    <article><h1>Titre   de l'article</h1>
    <img src="photo.png" alt=""/><svg><circle/></svg>
    <p>Premier paragraphe    utile.</p><p>Second paragraphe.</p></article>
    <footer>Pied de page</footer></body></html>
    """
    text = extract_text(html)
    assert "Titre de l'article" in text
    assert "Premier paragraphe utile." in text
    assert "Second paragraphe." in text
    for interdit in ["<", "font-size", "alert", "photo.png", "commentaire caché",
                     "Menu du site", "Bannière", "Pied de page"]:
        assert interdit not in text


def test_fetch_article_text_fallback_on_error(monkeypatch):
    """URL injoignable → None (l'article retombera sur son résumé stocké)."""
    import processors.synthesis as synthesis

    def _raise(*args, **kwargs):
        raise ConnectionError("réseau coupé")

    monkeypatch.setattr(synthesis.httpx, "get", _raise)
    assert synthesis.fetch_article_text("https://example.com/down") is None


def test_build_corpus_truncates_and_falls_back(monkeypatch):
    """Contenu récupéré → tronqué au budget ; échec → pas de synthesis_content."""
    import processors.synthesis as synthesis

    def fake_fetch(url):
        if url.endswith("/a1"):
            return "x" * 50_000  # page très volumineuse
        return None  # a2, a3 injoignables

    monkeypatch.setattr(synthesis, "fetch_article_text", fake_fetch)
    articles = [dict(a) for a in ARTICLES]
    corpus = synthesis.build_corpus(articles)

    assert len(corpus[0]["synthesis_content"]) <= synthesis.MAX_CHARS_PER_ARTICLE
    assert "synthesis_content" not in corpus[1]
    assert "synthesis_content" not in corpus[2]


# ---------------------------------------------------------------------------
# Prompt de synthèse (US-SYN-104)
# ---------------------------------------------------------------------------

def test_generate_synthesis_uses_full_content(monkeypatch):
    """Le prompt contient le centre d'intérêt, le texte intégral quand présent,
    et le résumé stocké en fallback."""
    import processors.gemini_processor as gp

    captured = {}

    class FakeModel:
        def __init__(self, model_name, generation_config=None):
            pass
        def generate_content(self, prompt):
            captured["prompt"] = prompt
            class R:
                text = json.dumps({"synthesis": "**🔭 Vue d'ensemble** ok", "cited_ids": ["a1"]})
            return R()

    monkeypatch.setattr(gp.genai, "GenerativeModel", FakeModel)

    articles = [dict(a) for a in ARTICLES[:2]]
    articles[0]["synthesis_content"] = "TEXTE_INTEGRAL_NETTOYE_A1"
    result = gp.generate_synthesis(articles, "SDLC à l'aune de l'IA", ["fake-model"])

    assert result["cited_ids"] == ["a1"]
    assert "SDLC à l'aune de l'IA" in captured["prompt"]
    assert "TEXTE_INTEGRAL_NETTOYE_A1" in captured["prompt"]      # texte intégral utilisé
    assert "Résumé stocké de a2." in captured["prompt"]           # fallback résumé


# ---------------------------------------------------------------------------
# Orchestration run_synthesis (US-SYN-102/104)
# ---------------------------------------------------------------------------

class _FakeDoc:
    def __init__(self, data):
        self._data = data
    def to_dict(self):
        return self._data


class _FakeDb:
    """Simule le strict nécessaire de Firestore pour run_synthesis."""
    def __init__(self, articles):
        self._articles = articles
        self.written: dict = {}

    def collection(self, name):
        self._collection = name
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n):
        return self

    def stream(self):
        return [_FakeDoc(a) for a in self._articles]

    def document(self, doc_id):
        self._doc_id = doc_id
        return self

    def set(self, data):
        self.written[self._doc_id] = data


def test_run_synthesis_empty_perimeter_skips_llm(monkeypatch):
    """Corpus vide → document écrit avec warning explicite, aucun appel LLM."""
    import processors.synthesis as synthesis

    def _fail(*args, **kwargs):
        raise AssertionError("le LLM ne doit pas être appelé sur un corpus vide")

    monkeypatch.setattr(synthesis, "generate_synthesis", _fail)
    db = _FakeDb(ARTICLES)
    settings = {"interest": "IA", "synthesis_source_ids": ["source-inconnue"], "synthesis_categories": []}

    synthesis.run_synthesis(db, settings, ["fake-model"])

    doc = next(iter(db.written.values()))
    assert "Aucun article dans le périmètre" in doc["content"]
    assert doc["articles_count"] == 0
    assert doc["cited_ids"] == []


def test_run_synthesis_writes_perimeter(monkeypatch):
    """Le document syntheses/{date} trace le périmètre utilisé (sources + thèmes)."""
    import processors.synthesis as synthesis

    monkeypatch.setattr(synthesis, "build_corpus", lambda articles: articles)
    monkeypatch.setattr(
        synthesis, "generate_synthesis",
        lambda articles, interest, model_priority: {"synthesis": "ok", "cited_ids": ["a1"]},
    )
    db = _FakeDb(ARTICLES)
    settings = {"interest": "IA", "synthesis_source_ids": ["tldr"], "synthesis_categories": ["IA", "Cloud"]}

    synthesis.run_synthesis(db, settings, ["fake-model"])

    doc = next(iter(db.written.values()))
    assert doc["source_ids"] == ["tldr"]
    assert doc["categories"] == ["IA", "Cloud"]
    assert doc["articles_count"] == 2  # a1 (IA) + a3 (Cloud), tous deux tldr
    assert doc["content"] == "ok"


def test_run_synthesis_no_interest_writes_nothing():
    """Centre d'intérêt vide → synthèse désactivée, aucune écriture."""
    from processors.synthesis import run_synthesis
    db = _FakeDb(ARTICLES)
    run_synthesis(db, {"interest": "  "}, ["fake-model"])
    assert db.written == {}
