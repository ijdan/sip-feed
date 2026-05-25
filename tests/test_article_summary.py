"""Tests fonctionnels — endpoint POST /articles/{article_id}/summary."""
import json
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
    """Un article inexistant retourne 404."""
    r = httpx.post(
        f"{BASE_URL}/articles/article-inexistant-xyz-12345/summary",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 404


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
