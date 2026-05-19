"""Tests fonctionnels API — endpoints publics et authentifiés."""
import httpx
import pytest
from conftest import BASE_URL

ARTICLE_FIELDS = {"id", "title", "title_fr", "title_en", "short_description",
                  "long_description", "article_url", "source_name", "category",
                  "published_at", "collected_at", "keywords_fr", "keywords_en"}

# ─── Santé ──────────────────────────────────────────────────────────────────

def test_health():
    r = httpx.get(f"{BASE_URL}/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ─── Articles publics ───────────────────────────────────────────────────────

def test_articles_list():
    r = httpx.get(f"{BASE_URL}/articles/")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_articles_list_has_bilingual_fields():
    r = httpx.get(f"{BASE_URL}/articles/")
    assert r.status_code == 200
    items = r.json()["items"]
    if items:
        a = items[0]
        for field in ARTICLE_FIELDS:
            assert field in a, f"Champ manquant : {field}"


def test_articles_list_keywords_are_lists():
    r = httpx.get(f"{BASE_URL}/articles/")
    assert r.status_code == 200
    for a in r.json()["items"]:
        assert isinstance(a["keywords_fr"], list)
        assert isinstance(a["keywords_en"], list)


def test_articles_filter_by_category():
    r = httpx.get(f"{BASE_URL}/articles/?category=IA")
    assert r.status_code == 200
    items = r.json()["items"]
    for a in items:
        assert a["category"] == "IA", f"Catégorie inattendue : {a['category']}"


def test_articles_stats():
    r = httpx.get(f"{BASE_URL}/articles/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total" in data
    assert "by_category" in data
    expected_cats = {"IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"}
    assert set(data["by_category"].keys()) == expected_cats


def test_article_not_found():
    r = httpx.get(f"{BASE_URL}/articles/id-inexistant-xyz")
    assert r.status_code == 404


# ─── Contrôle d'accès ───────────────────────────────────────────────────────

def test_admin_settings_requires_auth():
    r = httpx.get(f"{BASE_URL}/admin/settings")
    assert r.status_code in (401, 403)


def test_users_me_requires_auth():
    r = httpx.get(f"{BASE_URL}/users/me")
    assert r.status_code in (401, 403)


def test_users_preferences_requires_auth():
    r = httpx.get(f"{BASE_URL}/users/me/preferences")
    assert r.status_code in (401, 403)


def test_admin_stats_requires_auth():
    r = httpx.get(f"{BASE_URL}/admin/stats")
    assert r.status_code in (401, 403)


def test_invalid_token_rejected():
    r = httpx.get(f"{BASE_URL}/users/me",
                  headers={"Authorization": "Bearer token_invalide"})
    assert r.status_code in (401, 403)


# ─── API authentifiée — Admin ────────────────────────────────────────────────

def test_admin_settings_get(admin_token):
    r = httpx.get(f"{BASE_URL}/admin/settings",
                  headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    data = r.json()
    assert "llm_enabled" in data
    assert "model_priority" in data
    assert isinstance(data["model_priority"], list)
    assert len(data["model_priority"]) > 0
    assert "interest" in data


def test_admin_settings_put_interest(admin_token):
    r = httpx.get(f"{BASE_URL}/admin/settings",
                  headers={"Authorization": f"Bearer {admin_token}"})
    current = r.json()
    current["interest"] = "TEST_INTEREST_PYTEST"
    r2 = httpx.put(f"{BASE_URL}/admin/settings",
                   headers={"Authorization": f"Bearer {admin_token}"},
                   json=current)
    assert r2.status_code == 200
    assert r2.json()["interest"] == "TEST_INTEREST_PYTEST"
    # Restaurer
    current["interest"] = r.json().get("interest", "")
    httpx.put(f"{BASE_URL}/admin/settings",
              headers={"Authorization": f"Bearer {admin_token}"}, json=current)


def test_admin_syntheses_get(admin_token):
    r = httpx.get(f"{BASE_URL}/admin/syntheses",
                  headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert "syntheses" in r.json()
    assert isinstance(r.json()["syntheses"], list)


def test_admin_report_get(admin_token):
    r = httpx.get(f"{BASE_URL}/admin/report",
                  headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    data = r.json()
    assert "generated_at" in data or "content" in data


def test_admin_stats_get(admin_token):
    r = httpx.get(f"{BASE_URL}/admin/stats",
                  headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    data = r.json()
    assert "users_count" in data
    assert "api_calls" in data
    assert "user_article_stats" in data


def test_sources_list(admin_token):
    r = httpx.get(f"{BASE_URL}/sources/",
                  headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_sources_crud(admin_token):
    # Créer
    payload = {"name": "Test Source PYTEST", "type": "web",
               "url": "https://example.com", "active": True}
    r = httpx.post(f"{BASE_URL}/sources/",
                   headers={"Authorization": f"Bearer {admin_token}"}, json=payload)
    assert r.status_code == 200
    source_id = r.json()["id"]
    # Toggle
    r2 = httpx.patch(f"{BASE_URL}/sources/{source_id}/toggle",
                     headers={"Authorization": f"Bearer {admin_token}"})
    assert r2.status_code == 200
    # Supprimer
    r3 = httpx.delete(f"{BASE_URL}/sources/{source_id}",
                      headers={"Authorization": f"Bearer {admin_token}"})
    assert r3.status_code == 204


# ─── API authentifiée — User ─────────────────────────────────────────────────

def test_user_preferences_get(admin_token):
    r = httpx.get(f"{BASE_URL}/users/me/preferences",
                  headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    data = r.json()
    assert "favorites" in data
    assert "reading_list" in data
    assert "read_articles" in data
    assert "dismissed" in data


def test_user_settings_get(admin_token):
    r = httpx.get(f"{BASE_URL}/users/me/settings",
                  headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    data = r.json()
    assert "theme" in data
    assert "columns" in data
    assert "font_size" in data
    assert "excluded_categories" in data
    assert "excluded_sources" in data
    assert "hide_read" in data


def test_reader_cannot_access_admin(reader_token):
    r = httpx.get(f"{BASE_URL}/admin/settings",
                  headers={"Authorization": f"Bearer {reader_token}"})
    assert r.status_code == 403
