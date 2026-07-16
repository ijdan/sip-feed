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


def test_resolve_article_url_unwraps_tldr_tracking():
    """Un lien de tracking TLDR est déballé vers l'URL réelle de l'article."""
    from processors.synthesis import resolve_article_url
    tracking = ("https://tracking.tldrnewsletter.com/CL0/"
                "https:%2F%2Fexample.com%2Fpost%3Futm_source%3Dtldrnewsletter"
                "/1/010001/abcdef=123")
    assert resolve_article_url(tracking) == "https://example.com/post?utm_source=tldrnewsletter"


def test_resolve_article_url_passthrough():
    """Une URL directe (source web) ou un lien de tracking illisible restent inchangés."""
    from processors.synthesis import resolve_article_url
    assert resolve_article_url("https://example.com/article") == "https://example.com/article"
    assert (resolve_article_url("https://tracking.tldrnewsletter.com/CL0/pas-une-url/1/x")
            == "https://tracking.tldrnewsletter.com/CL0/pas-une-url/1/x")


def test_fetch_article_text_uses_real_url(monkeypatch):
    """Le téléchargement du contenu interroge l'URL réelle, pas le redirecteur."""
    import processors.synthesis as synthesis

    requested = {}

    def fake_get(url, **kwargs):
        requested["url"] = url
        class R:
            headers = {"content-type": "text/html"}
            text = "<p>" + "Contenu réel de l'article. " * 20 + "</p>"
            def raise_for_status(self):
                pass
        return R()

    monkeypatch.setattr(synthesis.httpx, "get", fake_get)
    tracking = "https://tracking.tldrnewsletter.com/CL0/https:%2F%2Fexample.com%2Fpost/1/010001/abc=1"
    text = synthesis.fetch_article_text(tracking)

    assert requested["url"] == "https://example.com/post"
    assert text and "Contenu réel de l'article." in text


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


def test_build_corpus_respects_configurable_max_input(monkeypatch):
    """Le plafond configuré dans l'admin borne le budget par article."""
    import processors.synthesis as synthesis

    monkeypatch.setattr(synthesis, "fetch_article_text", lambda url: "x" * 50_000)
    articles = [dict(a) for a in ARTICLES]
    corpus = synthesis.build_corpus(articles, max_input_chars=3_000)

    for a in corpus:
        assert len(a["synthesis_content"]) <= 1_000  # 3 000 / 3 articles


# ---------------------------------------------------------------------------
# Prompt de synthèse (US-SYN-104)
# ---------------------------------------------------------------------------

class _FakeUsage:
    prompt_token_count = 1000
    candidates_token_count = 200
    total_token_count = 1200


def _fake_model(captured: dict, payload: dict):
    """Fabrique un faux genai.GenerativeModel qui capture le prompt et renvoie payload."""
    class FakeModel:
        def __init__(self, model_name, generation_config=None):
            pass
        def generate_content(self, prompt):
            captured["prompt"] = prompt
            class R:
                text = json.dumps(payload)
                usage_metadata = _FakeUsage()
            return R()
    return FakeModel


def test_generate_synthesis_uses_full_content(monkeypatch):
    """Le prompt contient le centre d'intérêt, le texte intégral quand présent,
    et le résumé stocké en fallback. La consommation de tokens est mesurée."""
    import processors.gemini_processor as gp

    captured = {}
    monkeypatch.setattr(gp.genai, "GenerativeModel",
                        _fake_model(captured, {"synthesis": "**🔭 Vue d'ensemble** ok", "cited_ids": ["a1"]}))

    articles = [dict(a) for a in ARTICLES[:2]]
    articles[0]["synthesis_content"] = "TEXTE_INTEGRAL_NETTOYE_A1"
    result = gp.generate_synthesis(articles, "SDLC à l'aune de l'IA", ["fake-model"])

    assert result["cited_ids"] == ["a1"]
    assert "SDLC à l'aune de l'IA" in captured["prompt"]
    assert "TEXTE_INTEGRAL_NETTOYE_A1" in captured["prompt"]      # texte intégral utilisé
    assert "Résumé stocké de a2." in captured["prompt"]           # fallback résumé
    assert result["usage"] == {"prompt_tokens": 1000, "output_tokens": 200, "total_tokens": 1200}


def test_generate_synthesis_respects_max_input_chars(monkeypatch):
    """Le plafond configurable tronque le corpus dans le prompt."""
    import processors.gemini_processor as gp

    captured = {}
    monkeypatch.setattr(gp.genai, "GenerativeModel",
                        _fake_model(captured, {"synthesis": "ok", "cited_ids": []}))

    articles = [{"id": "a1", "title_fr": "T", "synthesis_content": "y" * 100_000}]
    gp.generate_synthesis(articles, "IA", ["fake-model"], max_input_chars=5_000)

    assert captured["prompt"].count("y") <= 5_000


def test_select_relevant_articles_parses_and_caps(monkeypatch):
    """La pré-sélection renvoie les IDs retenus (plafonnés) et la consommation."""
    import processors.gemini_processor as gp

    captured = {}
    monkeypatch.setattr(gp.genai, "GenerativeModel",
                        _fake_model(captured, {"selected_ids": ["a1", "a3", "a2"]}))

    result = gp.select_relevant_articles(ARTICLES, "IA", ["fake-model"], max_selected=2)

    assert result["selected_ids"] == ["a1", "a3"]  # plafonné à 2
    assert result["usage"]["total_tokens"] == 1200
    assert "IA" in captured["prompt"]
    assert "Résumé stocké de a1." in captured["prompt"]  # sélection sur résumés seulement


# ---------------------------------------------------------------------------
# Orchestration run_synthesis (US-SYN-102/104)
# ---------------------------------------------------------------------------

class _FakeDoc:
    def __init__(self, data):
        self._data = data
    def to_dict(self):
        return self._data


class _FakeSnapshot:
    def __init__(self, data):
        self._data = data
    @property
    def exists(self):
        return self._data is not None
    def to_dict(self):
        return self._data


class _FakeDb:
    """Simule le strict nécessaire de Firestore pour run_synthesis."""
    def __init__(self, articles, existing_syntheses: dict | None = None):
        self._articles = articles
        self._existing = existing_syntheses or {}
        self.written: dict = {}
        self.where_calls: list = []

    def collection(self, name):
        self._collection = name
        return self

    def where(self, field, op, value):
        self.where_calls.append((field, op, value))
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

    def get(self):
        return _FakeSnapshot(self._existing.get(self._doc_id))

    def set(self, data):
        self.written[self._doc_id] = data


_USAGE_STUB = {"prompt_tokens": 10, "output_tokens": 5, "total_tokens": 15}


def _stub_synthesis(monkeypatch, synthesis, cited=None):
    """Mock generate_synthesis + build_corpus avec les signatures actuelles."""
    monkeypatch.setattr(synthesis, "build_corpus",
                        lambda articles, max_input_chars=None: articles)
    monkeypatch.setattr(
        synthesis, "generate_synthesis",
        lambda articles, interest, model_priority, max_input_chars=None:
            {"synthesis": "ok", "cited_ids": cited or ["a1"], "usage": dict(_USAGE_STUB)},
    )


def test_run_synthesis_empty_perimeter_skips_llm(monkeypatch):
    """Corpus vide → document écrit avec warning explicite, aucun appel LLM."""
    import processors.synthesis as synthesis

    def _fail(*args, **kwargs):
        raise AssertionError("le LLM ne doit pas être appelé sur un corpus vide")

    monkeypatch.setattr(synthesis, "generate_synthesis", _fail)
    monkeypatch.setattr(synthesis, "select_relevant_articles", _fail)
    db = _FakeDb(ARTICLES)
    settings = {"interest": "IA", "synthesis_source_ids": ["source-inconnue"], "synthesis_categories": []}

    synthesis.run_synthesis(db, settings, ["fake-model"])

    doc = next(iter(db.written.values()))
    assert "Aucun article dans le périmètre" in doc["content"]
    assert doc["articles_count"] == 0
    assert doc["cited_ids"] == []
    assert doc["usage"]["total_tokens"] == 0


def test_run_synthesis_writes_perimeter(monkeypatch):
    """Le document syntheses/{date} trace le périmètre et la consommation."""
    import processors.synthesis as synthesis

    _stub_synthesis(monkeypatch, synthesis)
    db = _FakeDb(ARTICLES)
    settings = {"interest": "IA", "synthesis_source_ids": ["tldr"], "synthesis_categories": ["IA", "Cloud"]}

    synthesis.run_synthesis(db, settings, ["fake-model"])

    doc = next(iter(db.written.values()))
    assert doc["source_ids"] == ["tldr"]
    assert doc["categories"] == ["IA", "Cloud"]
    assert doc["articles_count"] == 2  # a1 (IA) + a3 (Cloud), tous deux tldr
    assert doc["perimeter_count"] == 2
    assert doc["content"] == "ok"
    assert doc["usage"] == _USAGE_STUB  # corpus ≤ SELECTION_MIN_CORPUS : un seul appel


def test_run_synthesis_no_interest_writes_nothing():
    """Centre d'intérêt vide → synthèse désactivée, aucune écriture."""
    from processors.synthesis import run_synthesis
    db = _FakeDb(ARTICLES)
    run_synthesis(db, {"interest": "  "}, ["fake-model"])
    assert db.written == {}


# ---------------------------------------------------------------------------
# Économie de tokens — skip si rien de nouveau (levier 1)
# ---------------------------------------------------------------------------

def _today():
    from datetime import date
    return date.today().isoformat()


def test_run_synthesis_skips_when_up_to_date(monkeypatch):
    """Synthèse du jour existante + même périmètre + aucun nouvel article
    dans le périmètre → aucun appel LLM, aucune réécriture."""
    import processors.synthesis as synthesis

    def _fail(*args, **kwargs):
        raise AssertionError("aucun appel LLM attendu quand la synthèse est à jour")

    monkeypatch.setattr(synthesis, "generate_synthesis", _fail)
    monkeypatch.setattr(synthesis, "select_relevant_articles", _fail)

    existing = {_today(): {"interest": "IA", "source_ids": ["tldr"], "categories": []}}
    db = _FakeDb(ARTICLES, existing_syntheses=existing)
    settings = {"interest": "IA", "synthesis_source_ids": ["tldr"], "synthesis_categories": []}
    hors_perimetre = [{"id": "n1", "source_id": "hn", "category": "Dev"}]

    synthesis.run_synthesis(db, settings, ["fake-model"], new_articles=hors_perimetre)

    assert db.written == {}


def test_run_synthesis_regenerates_on_new_article_in_perimeter(monkeypatch):
    """Un nouvel article dans le périmètre force la régénération."""
    import processors.synthesis as synthesis

    _stub_synthesis(monkeypatch, synthesis)
    existing = {_today(): {"interest": "IA", "source_ids": ["tldr"], "categories": []}}
    db = _FakeDb(ARTICLES, existing_syntheses=existing)
    settings = {"interest": "IA", "synthesis_source_ids": ["tldr"], "synthesis_categories": []}
    dans_perimetre = [{"id": "n1", "source_id": "tldr", "category": "IA"}]

    synthesis.run_synthesis(db, settings, ["fake-model"], new_articles=dans_perimetre)

    assert db.written  # régénérée


def test_run_synthesis_manual_trigger_bypasses_skip(monkeypatch):
    """Déclenchement manuel (new_articles=None) → régénération forcée,
    même si la synthèse du jour est à jour pour le même périmètre."""
    import processors.synthesis as synthesis

    _stub_synthesis(monkeypatch, synthesis)
    existing = {_today(): {"interest": "IA", "source_ids": [], "categories": [],
                           "content": "ancienne synthèse"}}
    db = _FakeDb(ARTICLES, existing_syntheses=existing)
    settings = {"interest": "IA", "synthesis_source_ids": [], "synthesis_categories": []}

    synthesis.run_synthesis(db, settings, ["fake-model"], new_articles=None)

    assert db.written  # régénérée malgré un doc à jour
    assert next(iter(db.written.values()))["content"] == "ok"


def test_run_synthesis_target_date(monkeypatch):
    """Génération pour une date choisie : corpus limité aux articles collectés
    ce jour-là (bornes début ET fin de journée), document écrit dans
    syntheses/{date choisie}."""
    import processors.synthesis as synthesis

    _stub_synthesis(monkeypatch, synthesis)
    db = _FakeDb(ARTICLES)
    settings = {"interest": "IA", "synthesis_source_ids": [], "synthesis_categories": []}

    synthesis.run_synthesis(db, settings, ["fake-model"], target_date="2026-07-10")

    assert list(db.written.keys()) == ["2026-07-10"]
    doc = db.written["2026-07-10"]
    assert doc["target_date"] == "2026-07-10"
    assert ("collected_at", ">=", "2026-07-10T00:00:00") in db.where_calls
    assert ("collected_at", "<=", "2026-07-10T23:59:59.999999") in db.where_calls


def test_run_synthesis_default_date_is_today(monkeypatch):
    """Sans date ciblée : document du jour, aucun filtre de date sur le corpus."""
    import processors.synthesis as synthesis

    _stub_synthesis(monkeypatch, synthesis)
    db = _FakeDb(ARTICLES)

    synthesis.run_synthesis(db, {"interest": "IA"}, ["fake-model"])

    assert list(db.written.keys()) == [_today()]
    assert db.where_calls == []


def test_run_synthesis_retries_after_failed_synthesis(monkeypatch):
    """Une synthèse du jour en échec (⚠️) est retentée même sans nouvel article."""
    import processors.synthesis as synthesis

    _stub_synthesis(monkeypatch, synthesis)
    existing = {_today(): {"interest": "IA", "source_ids": [], "categories": [],
                           "content": "⚠️ Synthèse indisponible — tous les modèles LLM ont échoué"}}
    db = _FakeDb(ARTICLES, existing_syntheses=existing)
    settings = {"interest": "IA", "synthesis_source_ids": [], "synthesis_categories": []}

    synthesis.run_synthesis(db, settings, ["fake-model"], new_articles=[])

    assert db.written  # retry effectué
    assert next(iter(db.written.values()))["content"] == "ok"


def test_run_synthesis_regenerates_on_scope_change(monkeypatch):
    """Un changement de centre d'intérêt ou de périmètre force la régénération,
    même sans nouvel article."""
    import processors.synthesis as synthesis

    _stub_synthesis(monkeypatch, synthesis)
    existing = {_today(): {"interest": "Ancien sujet", "source_ids": [], "categories": []}}
    db = _FakeDb(ARTICLES, existing_syntheses=existing)
    settings = {"interest": "IA", "synthesis_source_ids": [], "synthesis_categories": []}

    synthesis.run_synthesis(db, settings, ["fake-model"], new_articles=[])

    assert db.written  # régénérée


# ---------------------------------------------------------------------------
# Économie de tokens — pré-sélection en deux étapes (levier 2)
# ---------------------------------------------------------------------------

def _large_corpus(n=12):
    return [{"id": f"a{i}", "title_fr": f"Article {i}", "source_id": "tldr", "category": "IA",
             "article_url": f"https://example.com/a{i}", "long_description_fr": f"Résumé {i}."}
            for i in range(n)]


def test_run_synthesis_two_stage_selection(monkeypatch):
    """Gros corpus → pré-sélection sur résumés, contenu intégral uniquement
    pour les articles retenus, consommation cumulée des deux appels."""
    import processors.synthesis as synthesis

    fetched = {}

    def fake_build_corpus(articles, max_input_chars=None):
        fetched["ids"] = [a["id"] for a in articles]
        return articles

    monkeypatch.setattr(synthesis, "build_corpus", fake_build_corpus)
    monkeypatch.setattr(
        synthesis, "select_relevant_articles",
        lambda articles, interest, model_priority, max_selected:
            {"selected_ids": ["a2", "a5"], "usage": {"prompt_tokens": 100, "output_tokens": 10, "total_tokens": 110}},
    )
    monkeypatch.setattr(
        synthesis, "generate_synthesis",
        lambda articles, interest, model_priority, max_input_chars=None:
            {"synthesis": "ok", "cited_ids": ["a2"], "usage": {"prompt_tokens": 400, "output_tokens": 50, "total_tokens": 450}},
    )
    db = _FakeDb(_large_corpus())

    synthesis.run_synthesis(db, {"interest": "IA"}, ["fake-model"])

    doc = next(iter(db.written.values()))
    assert fetched["ids"] == ["a2", "a5"]        # contenu intégral seulement pour la sélection
    assert doc["articles_count"] == 2
    assert doc["perimeter_count"] == 12
    assert doc["usage"]["total_tokens"] == 560   # 110 (sélection) + 450 (synthèse)


def test_run_synthesis_selection_failure_falls_back_to_summaries(monkeypatch):
    """Pré-sélection indisponible → synthèse sur les résumés, sans téléchargement
    de contenu intégral (coût borné)."""
    import processors.synthesis as synthesis

    def _no_fetch(*args, **kwargs):
        raise AssertionError("pas de téléchargement de contenu intégral en mode dégradé")

    monkeypatch.setattr(synthesis, "build_corpus", _no_fetch)
    monkeypatch.setattr(synthesis, "select_relevant_articles", lambda *a, **k: None)

    received = {}
    monkeypatch.setattr(
        synthesis, "generate_synthesis",
        lambda articles, interest, model_priority, max_input_chars=None:
            received.update(count=len(articles)) or {"synthesis": "ok", "cited_ids": [], "usage": dict(_USAGE_STUB)},
    )
    db = _FakeDb(_large_corpus())

    synthesis.run_synthesis(db, {"interest": "IA"}, ["fake-model"])

    assert received["count"] == 12  # tout le corpus, mais résumés seulement


def test_run_synthesis_selection_empty_skips_second_call(monkeypatch):
    """Pré-sélection sans article pertinent → pas de second appel LLM."""
    import processors.synthesis as synthesis

    def _fail(*args, **kwargs):
        raise AssertionError("pas de synthèse quand aucun article n'est pertinent")

    monkeypatch.setattr(synthesis, "generate_synthesis", _fail)
    monkeypatch.setattr(synthesis, "build_corpus", _fail)
    monkeypatch.setattr(
        synthesis, "select_relevant_articles",
        lambda *a, **k: {"selected_ids": [], "usage": {"prompt_tokens": 100, "output_tokens": 5, "total_tokens": 105}},
    )
    db = _FakeDb(_large_corpus())

    synthesis.run_synthesis(db, {"interest": "IA"}, ["fake-model"])

    doc = next(iter(db.written.values()))
    assert "Aucun article du périmètre jugé pertinent" in doc["content"]
    assert doc["articles_count"] == 0
    assert doc["usage"]["total_tokens"] == 105  # seule la sélection a consommé
