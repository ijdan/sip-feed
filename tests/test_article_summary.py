"""Tests fonctionnels — endpoint POST /articles/{article_id}/summary."""
import json
import os
import sys
import pytest
import httpx
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

from conftest import BASE_URL

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))


def _backend_available() -> bool:
    try:
        httpx.get(f"{BASE_URL}/health", timeout=2)
        return True
    except Exception:
        return False


requires_backend = pytest.mark.skipif(
    not _backend_available(),
    reason="Backend non disponible — test d'intégration ignoré",
)


# ─── Contrôle d'accès ────────────────────────────────────────────────────────

@requires_backend
def test_summary_no_auth():
    """Sans token, l'endpoint retourne 401 ou 403."""
    r = httpx.post(f"{BASE_URL}/articles/any-id/summary")
    assert r.status_code in (401, 403)


@requires_backend
def test_summary_reader_forbidden(reader_token):
    """Un reader n'a pas accès à l'endpoint."""
    r = httpx.post(
        f"{BASE_URL}/articles/any-id/summary",
        headers={"Authorization": f"Bearer {reader_token}"},
    )
    assert r.status_code == 403


# ─── Article introuvable ─────────────────────────────────────────────────────

@requires_backend
def test_summary_article_not_found(admin_token):
    """Un article inexistant émet un événement SSE d'erreur 404 (HTTP reste 200)."""
    events = []
    with httpx.stream(
        "POST",
        f"{BASE_URL}/articles/article-inexistant-xyz-12345/summary",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30,
    ) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    assert any(e["type"] == "error" and e.get("status") == 404 for e in events)


# ─── Régénération forcée (?force=true) ───────────────────────────────────────

def _import_articles_router():
    """Importe app.routers.articles — app.config.Settings exige ces variables
    d'environnement au premier import ; on fournit des valeurs factices si absentes."""
    for key in (
        "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET",
        "JWT_SECRET", "FIRESTORE_PROJECT_ID", "GEMINI_API_KEY",
    ):
        os.environ.setdefault(key, "test")
    from app.routers import articles
    return articles


def _mock_summary_db(cached_summary: dict, article: dict):
    """Base Firestore mockée : un résumé en cache + l'article correspondant."""
    summary_doc = MagicMock()
    summary_doc.exists = True
    summary_doc.to_dict = MagicMock(return_value=cached_summary)
    summary_ref = MagicMock()
    summary_ref.get = MagicMock(return_value=summary_doc)

    article_doc = MagicMock()
    article_doc.exists = True
    article_doc.to_dict = MagicMock(return_value=article)
    article_ref = MagicMock()
    article_ref.get = MagicMock(return_value=article_doc)

    def collection(name):
        col = MagicMock()
        col.document = MagicMock(
            return_value=summary_ref if name == "article_summaries" else article_ref
        )
        return col

    mock_db = MagicMock()
    mock_db.collection = MagicMock(side_effect=collection)
    return mock_db, summary_ref


def _collect_stream_events(article_id: str, force: bool):
    """Exécute _summary_event_stream et retourne les événements SSE parsés."""
    import asyncio
    articles_router = _import_articles_router()

    async def run():
        events = []
        async for chunk in articles_router._summary_event_stream(article_id, "test", force=force):
            events.append(json.loads(chunk[6:].strip()))
        return events

    return asyncio.run(run())


_CACHED_SUMMARY = {
    "article_id": "art-1",
    "article_url": "https://example.com/a",
    "summary_fr": "Ancien résumé FR",
    "summary_en": "Old EN summary",
    "model_used": "gemini-old",
    "generated_at": "2026-01-01T00:00:00+00:00",
    "word_count_fr": 3,
    "word_count_en": 3,
    "prompt_version": "linkedin-v-test",
}

_ARTICLE = {"article_url": "https://example.com/a", "title": "T", "source_name": "S"}


def test_summary_stream_returns_cache_without_force():
    """Sans force, un résumé en cache est restitué tel quel (cached=True), sans LLM."""
    _import_articles_router()
    mock_db, _ = _mock_summary_db(_CACHED_SUMMARY, _ARTICLE)

    with patch("app.routers.articles.get_db", return_value=mock_db), \
         patch("app.routers.articles.get_summary_prompt", return_value=("prompt", "linkedin-v-test")), \
         patch("app.routers.articles.fetch_article_text", new=AsyncMock()) as mock_fetch:
        events = _collect_stream_events("art-1", force=False)

    result = next(e for e in events if e["type"] == "result")
    assert result["data"]["cached"] is True
    assert result["data"]["summary_fr"] == "Ancien résumé FR"
    mock_fetch.assert_not_called()


def test_summary_stream_force_regenerates_despite_cache():
    """Avec force=True, le cache est ignoré : nouveau scraping + LLM, cached=False."""
    _import_articles_router()
    mock_db, summary_ref = _mock_summary_db(_CACHED_SUMMARY, _ARTICLE)

    with patch("app.routers.articles.get_db", return_value=mock_db), \
         patch("app.routers.articles.get_summary_prompt", return_value=("prompt", "linkedin-v-test")), \
         patch("app.routers.articles.fetch_article_text", new=AsyncMock(return_value="texte article")), \
         patch("app.routers.articles.get_model_priority", return_value=["modele-a"]), \
         patch(
             "app.routers.articles._sync_call_llm_with_progress",
             return_value=("Nouveau résumé FR", "New EN summary", "modele-a"),
         ), \
         patch("app.routers.articles._log_summary_stat", new=AsyncMock()):
        events = _collect_stream_events("art-1", force=True)

    # Le cache n'a jamais été lu
    summary_ref.get.assert_not_called()
    result = next(e for e in events if e["type"] == "result")
    assert result["data"]["cached"] is False
    assert result["data"]["summary_fr"] == "Nouveau résumé FR"
    # Le nouveau résumé écrase l'ancien en Firestore
    summary_ref.set.assert_called_once()


# ─── Modèle ArticleSummary ───────────────────────────────────────────────────

SUMMARY_FIELDS = {
    "article_id", "article_url", "summary_fr", "summary_en",
    "model_used", "generated_at", "word_count_fr", "word_count_en", "cached",
}


def test_summary_model_fields():
    """ArticleSummary contient tous les champs requis."""
    from app.models.summary import ArticleSummary

    s = ArticleSummary(
        article_id="test-id",
        article_url="https://example.com/article",
        summary_fr="Résumé en français.",
        summary_en="Summary in English.",
        model_used="gemini-test",
        generated_at="2026-05-25T00:00:00+00:00",
        word_count_fr=3,
        word_count_en=3,
    )
    data = s.model_dump()
    for field in SUMMARY_FIELDS:
        assert field in data, f"Champ manquant : {field}"
    assert data["cached"] is False


def test_summary_model_cached_default_false():
    """Le champ cached vaut False par défaut."""
    from app.models.summary import ArticleSummary

    s = ArticleSummary(
        article_id="x", article_url="https://x.com", summary_fr="", summary_en="",
        model_used="m", generated_at="2026-01-01T00:00:00+00:00",
        word_count_fr=0, word_count_en=0,
    )
    assert s.cached is False


# ─── Nettoyage HTML ──────────────────────────────────────────────────────────

def test_fetch_article_text_removes_noise():
    """fetch_article_text supprime les balises non souhaitées et conserve le contenu."""
    import asyncio
    from app.services.article_summarizer import fetch_article_text

    html = """
    <html><body>
      <nav>Menu de navigation</nav>
      <script>alert('malicious')</script>
      <style>body { color: red }</style>
      <article>
        <h1>Titre principal</h1>
        <p>Premier paragraphe avec du contenu utile.</p>
        <p>Deuxième paragraphe important.</p>
      </article>
      <footer>Pied de page</footer>
      <aside>Publicité</aside>
    </body></html>
    """

    mock_response = MagicMock()
    mock_response.text = html
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.services.article_summarizer.httpx.AsyncClient", return_value=mock_client):
        text = asyncio.run(fetch_article_text("https://example.com/article"))

    assert "Menu de navigation" not in text
    assert "malicious" not in text
    assert "color: red" not in text
    assert "Pied de page" not in text
    assert "Publicité" not in text
    assert "Premier paragraphe" in text
    assert "Deuxième paragraphe" in text


def test_fetch_article_text_truncates_at_50k():
    """Le texte est plafonné à 50 000 caractères."""
    import asyncio
    from app.services.article_summarizer import fetch_article_text

    long_content = "A" * 60_000
    html = f"<html><body><article><p>{long_content}</p></article></body></html>"

    mock_response = MagicMock()
    mock_response.text = html
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.services.article_summarizer.httpx.AsyncClient", return_value=mock_client):
        text = asyncio.run(fetch_article_text("https://example.com/article"))

    assert len(text) <= 50_000


# ─── Cascade LLM ─────────────────────────────────────────────────────────────

def test_llm_falls_back_on_quota_error():
    """Si le premier modèle échoue (quota), le suivant est essayé."""
    from app.services.article_summarizer import _sync_call_llm

    call_count = [0]

    def mock_generate(prompt):
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("ResourceExhausted: quota exceeded")
        mock_resp = MagicMock()
        mock_resp.text = json.dumps({
            "summary_fr": "Résumé FR du second modèle",
            "summary_en": "EN summary from second model",
        })
        return mock_resp

    mock_model = MagicMock()
    mock_model.generate_content = mock_generate

    with patch("app.services.article_summarizer.genai") as mock_genai:
        mock_genai.configure = MagicMock()
        mock_genai.GenerativeModel = MagicMock(return_value=mock_model)

        fr, en, model = _sync_call_llm("Texte test", ["modele-a", "modele-b"])

    assert fr == "Résumé FR du second modèle"
    assert en == "EN summary from second model"
    assert model == "modele-b"
    assert call_count[0] == 2


def test_llm_all_models_fail_raises():
    """Si tous les modèles échouent, une exception est levée."""
    from app.services.article_summarizer import _sync_call_llm

    mock_model = MagicMock()
    mock_model.generate_content = MagicMock(side_effect=Exception("quota exceeded"))

    with patch("app.services.article_summarizer.genai") as mock_genai:
        mock_genai.configure = MagicMock()
        mock_genai.GenerativeModel = MagicMock(return_value=mock_model)

        with pytest.raises(Exception):
            _sync_call_llm("Texte test", ["modele-a", "modele-b"])


def test_llm_first_model_succeeds():
    """Si le premier modèle réussit, aucun fallback n'est essayé."""
    from app.services.article_summarizer import _sync_call_llm

    call_count = [0]

    def mock_generate(prompt):
        call_count[0] += 1
        mock_resp = MagicMock()
        mock_resp.text = json.dumps({
            "summary_fr": "Résumé FR",
            "summary_en": "EN summary",
        })
        return mock_resp

    mock_model = MagicMock()
    mock_model.generate_content = mock_generate

    with patch("app.services.article_summarizer.genai") as mock_genai:
        mock_genai.configure = MagicMock()
        mock_genai.GenerativeModel = MagicMock(return_value=mock_model)

        fr, en, model = _sync_call_llm("Texte test", ["modele-a", "modele-b"])

    assert model == "modele-a"
    assert call_count[0] == 1


def test_llm_handles_markdown_json_wrapper():
    """Le parser JSON gère les réponses enveloppées dans ```json ... ```."""
    from app.services.article_summarizer import _sync_call_llm

    payload = json.dumps({"summary_fr": "FR", "summary_en": "EN"})
    wrapped = f"```json\n{payload}\n```"

    mock_resp = MagicMock()
    mock_resp.text = wrapped
    mock_model = MagicMock()
    mock_model.generate_content = MagicMock(return_value=mock_resp)

    with patch("app.services.article_summarizer.genai") as mock_genai:
        mock_genai.configure = MagicMock()
        mock_genai.GenerativeModel = MagicMock(return_value=mock_model)

        fr, en, model = _sync_call_llm("Texte test", ["modele-a"])

    assert fr == "FR"
    assert en == "EN"


# ─── Prompt paramétrable (settings/prompts) ──────────────────────────────────

def _mock_db_with_prompt_doc(exists: bool, data: dict | None = None):
    mock_doc = MagicMock()
    mock_doc.exists = exists
    mock_doc.to_dict = MagicMock(return_value=data or {})
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
    return mock_db


def test_get_summary_prompt_default_when_doc_missing():
    """Sans document settings/prompts, le prompt par défaut du code est utilisé."""
    from app.services.article_summarizer import get_summary_prompt, SUMMARY_PROMPT, PROMPT_VERSION

    prompt, version = get_summary_prompt(_mock_db_with_prompt_doc(exists=False))
    assert prompt == SUMMARY_PROMPT
    assert version == PROMPT_VERSION


def test_get_summary_prompt_default_when_field_empty():
    """Un champ summary_prompt vide équivaut au prompt par défaut."""
    from app.services.article_summarizer import get_summary_prompt, SUMMARY_PROMPT, PROMPT_VERSION

    prompt, version = get_summary_prompt(
        _mock_db_with_prompt_doc(exists=True, data={"summary_prompt": "   "})
    )
    assert prompt == SUMMARY_PROMPT
    assert version == PROMPT_VERSION


def test_get_summary_prompt_custom_with_hashed_version():
    """Un prompt personnalisé est retourné avec une version dérivée de son hash."""
    from app.services.article_summarizer import get_summary_prompt

    custom = "Résume {text} en un post."
    prompt, version = get_summary_prompt(
        _mock_db_with_prompt_doc(exists=True, data={"summary_prompt": custom})
    )
    assert prompt == custom
    assert version.startswith("linkedin-custom-")

    # La version change quand le prompt change (invalidation du cache)
    _, version2 = get_summary_prompt(
        _mock_db_with_prompt_doc(exists=True, data={"summary_prompt": custom + " Différent."})
    )
    assert version2 != version


def test_get_summary_prompt_default_on_firestore_error():
    """Une erreur Firestore retombe silencieusement sur le prompt par défaut."""
    from app.services.article_summarizer import get_summary_prompt, SUMMARY_PROMPT, PROMPT_VERSION

    mock_db = MagicMock()
    mock_db.collection.side_effect = Exception("Firestore indisponible")
    prompt, version = get_summary_prompt(mock_db)
    assert prompt == SUMMARY_PROMPT
    assert version == PROMPT_VERSION


def test_render_prompt_substitutes_placeholders():
    """render_prompt remplace {title}, {source} et {text}."""
    from app.services.article_summarizer import render_prompt

    result = render_prompt(
        "Titre : {title} / Source : {source}\n{text}",
        title="Mon titre", source="Ma source", text="Le corps.",
    )
    assert result == "Titre : Mon titre / Source : Ma source\nLe corps."


def test_render_prompt_keeps_literal_braces():
    """Les accolades littérales (ex. exemple JSON) ne cassent pas la substitution."""
    from app.services.article_summarizer import render_prompt

    template = 'Réponds en JSON : {"summary_fr": "..."}\nArticle : {text}'
    result = render_prompt(template, title="t", source="s", text="corps")
    assert '{"summary_fr": "..."}' in result
    assert "corps" in result


def test_default_prompt_contains_placeholders():
    """Le prompt par défaut contient bien les trois placeholders attendus."""
    from app.services.article_summarizer import SUMMARY_PROMPT, PROMPT_PLACEHOLDERS

    for placeholder in PROMPT_PLACEHOLDERS:
        assert placeholder in SUMMARY_PROMPT


# ─── Endpoints admin /admin/summary-prompt ───────────────────────────────────

@requires_backend
def test_summary_prompt_no_auth():
    """Sans token, l'endpoint admin retourne 401 ou 403."""
    r = httpx.get(f"{BASE_URL}/admin/summary-prompt")
    assert r.status_code in (401, 403)


@requires_backend
def test_summary_prompt_reader_forbidden(reader_token):
    """Un reader n'a pas accès au prompt."""
    r = httpx.get(
        f"{BASE_URL}/admin/summary-prompt",
        headers={"Authorization": f"Bearer {reader_token}"},
    )
    assert r.status_code == 403


@requires_backend
def test_summary_prompt_requires_text_placeholder(admin_token):
    """Un prompt sans {text} est rejeté en 422."""
    r = httpx.put(
        f"{BASE_URL}/admin/summary-prompt",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"prompt": "Prompt sans le placeholder obligatoire."},
    )
    assert r.status_code == 422


@requires_backend
def test_summary_prompt_roundtrip_and_reset(admin_token):
    """PUT personnalise le prompt, PUT vide réinitialise au défaut."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    custom = "Prompt de test : résume {text} pour LinkedIn."
    try:
        r = httpx.put(f"{BASE_URL}/admin/summary-prompt", headers=headers, json={"prompt": custom})
        assert r.status_code == 200
        body = r.json()
        assert body["prompt"] == custom
        assert body["is_custom"] is True
        assert body["prompt_version"].startswith("linkedin-custom-")

        r = httpx.get(f"{BASE_URL}/admin/summary-prompt", headers=headers)
        assert r.status_code == 200
        assert r.json()["prompt"] == custom
    finally:
        r = httpx.put(f"{BASE_URL}/admin/summary-prompt", headers=headers, json={"prompt": ""})
        assert r.status_code == 200
        body = r.json()
        assert body["is_custom"] is False
        assert body["prompt"] == body["default_prompt"]


# ─── get_model_priority ───────────────────────────────────────────────────────

def test_get_model_priority_uses_firestore_value():
    """get_model_priority retourne la valeur Firestore si elle existe."""
    from app.services.article_summarizer import get_model_priority

    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict = MagicMock(return_value={"model_priority": ["modele-x", "modele-y"]})

    mock_collection = MagicMock()
    mock_collection.document.return_value.get.return_value = mock_doc

    mock_db = MagicMock()
    mock_db.collection.return_value = mock_collection

    result = get_model_priority(mock_db)
    assert result == ["modele-x", "modele-y"]


def test_get_model_priority_uses_default_when_missing():
    """get_model_priority retourne DEFAULT_MODEL_PRIORITY si Firestore ne contient rien."""
    from app.services.article_summarizer import get_model_priority, DEFAULT_MODEL_PRIORITY

    mock_doc = MagicMock()
    mock_doc.exists = False

    mock_collection = MagicMock()
    mock_collection.document.return_value.get.return_value = mock_doc

    mock_db = MagicMock()
    mock_db.collection.return_value = mock_collection

    result = get_model_priority(mock_db)
    assert result == DEFAULT_MODEL_PRIORITY
