"""Tests fonctionnels — enrichissement articles (Gemini processor)."""
import os
import sys
import pytest
from pathlib import Path
from dotenv import load_dotenv

# Charger le .env du collector pour GEMINI_API_KEY
COLLECTOR_DIR = Path(__file__).resolve().parents[1] / "collector"
load_dotenv(COLLECTOR_DIR / ".env")

# Fournir une clé factice si absente (pour les tests avec mock)
if not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = "AIza_TEST_KEY_FOR_UNIT_TESTS"

sys.path.insert(0, str(COLLECTOR_DIR))

CATEGORIES = ["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"]

SAMPLE_ARTICLES = [
    {
        "title": "Rust reaches 99% compatibility with Node.js",
        "raw_content": "The Bun JavaScript runtime has rewritten its core in Rust, achieving near-complete Node.js API compatibility.",
        "article_url": "https://example.com/rust-node",
        "source_name": "Hacker News",
        "source_id": "hn_test",
    },
    {
        "title": "Kubernetes v1.36 ships server-side sharding",
        "raw_content": "Kubernetes v1.36 introduces server-side sharded list and watch for improved scalability in large clusters.",
        "article_url": "https://example.com/k8s-136",
        "source_name": "TDLR",
        "source_id": "tldr_test",
    },
]


def test_save_raw_articles_structure():
    """Vérifie que save_raw_articles produit la bonne structure."""
    from processors.gemini_processor import save_raw_articles
    results = save_raw_articles(SAMPLE_ARTICLES)
    assert len(results) == 2
    for a in results:
        assert "id" in a
        assert "title" in a
        assert "article_url" in a
        assert "source_name" in a
        assert "category" in a
        assert a["category"] == "Autre"  # fallback sans LLM
        assert "keywords_fr" in a
        assert "keywords_en" in a
        assert "title_fr" in a
        assert "title_en" in a


def test_save_raw_articles_unique_ids():
    """Chaque article reçoit un ID unique."""
    from processors.gemini_processor import save_raw_articles
    results = save_raw_articles(SAMPLE_ARTICLES)
    ids = [a["id"] for a in results]
    assert len(ids) == len(set(ids)), "IDs dupliqués détectés"


def test_save_raw_articles_preserves_url():
    """L'URL de l'article est bien conservée."""
    from processors.gemini_processor import save_raw_articles
    results = save_raw_articles(SAMPLE_ARTICLES)
    assert results[0]["article_url"] == "https://example.com/rust-node"
    assert results[1]["article_url"] == "https://example.com/k8s-136"


def test_enrich_articles_batch_structure(monkeypatch):
    """Vérifie la structure de sortie d'enrich_articles_batch (mock LLM)."""
    from processors import gemini_processor

    # Mock du LLM pour ne pas consommer de quota
    mock_response = [
        {
            "title_fr": "Rust atteint 99% de compatibilité Node.js",
            "title_en": "Rust reaches 99% Node.js compatibility",
            "short_description_fr": "Bun réécrit son cœur en Rust.",
            "short_description_en": "Bun rewrites its core in Rust.",
            "long_description_fr": "Le runtime JavaScript Bun a réécrit son cœur en Rust.",
            "long_description_en": "The Bun JavaScript runtime has rewritten its core in Rust.",
            "keywords_fr": ["Rust", "Node.js", "JavaScript", "runtime", "Dev"],
            "keywords_en": ["Rust", "Node.js", "JavaScript", "runtime", "Dev"],
            "category": "Dev",
        },
        {
            "title_fr": "Kubernetes v1.36 : sharding côté serveur",
            "title_en": "Kubernetes v1.36 ships server-side sharding",
            "short_description_fr": "Kubernetes améliore la scalabilité.",
            "short_description_en": "Kubernetes improves scalability.",
            "long_description_fr": "Kubernetes v1.36 introduit le sharding.",
            "long_description_en": "Kubernetes v1.36 introduces sharding.",
            "keywords_fr": ["Kubernetes", "DevOps", "Cloud", "k8s"],
            "keywords_en": ["Kubernetes", "DevOps", "Cloud", "k8s"],
            "category": "DevOps",
        },
    ]

    import json
    monkeypatch.setattr(gemini_processor, "_call_llm",
                        lambda prompt, models, thinking=True: json.dumps(mock_response))

    results = gemini_processor.enrich_articles_batch(SAMPLE_ARTICLES)
    assert len(results) == 2

    for a in results:
        assert a["title_fr"], "title_fr vide"
        assert a["title_en"], "title_en vide"
        assert a["short_description_fr"], "short_description_fr vide"
        assert a["short_description_en"], "short_description_en vide"
        assert a["long_description_fr"], "long_description_fr vide"
        assert a["long_description_en"], "long_description_en vide"
        assert a["category"] in CATEGORIES, f"Catégorie invalide : {a['category']}"
        assert isinstance(a["keywords_fr"], list), "keywords_fr doit être une liste"
        assert isinstance(a["keywords_en"], list), "keywords_en doit être une liste"
        assert len(a["keywords_fr"]) > 0, "keywords_fr vide"


def test_add_articles_no_cap_on_collection():
    """Le collector doit tout récupérer — pas de limite arbitraire de collecte."""
    all_raw: list[dict] = []
    seen_urls: set[str] = set()

    def already_exists_never(_url: str) -> bool:
        return False

    def _add_articles_to_batch(articles: list[dict]) -> None:
        for raw in articles:
            url = raw["article_url"]
            if url in seen_urls or already_exists_never(url):
                continue
            seen_urls.add(url)
            all_raw.append(raw)

    # Gmail : 25 articles uniques
    gmail_articles = [
        {"title": f"Gmail article {i}", "article_url": f"https://gmail.example.com/{i}"}
        for i in range(25)
    ]
    _add_articles_to_batch(gmail_articles)

    # Web : 15 articles uniques supplémentaires
    web_articles = [
        {"title": f"Web article {i}", "article_url": f"https://web.example.com/{i}"}
        for i in range(15)
    ]
    _add_articles_to_batch(web_articles)

    assert len(all_raw) == 40, (
        f"Toutes les sources doivent être collectées sans plafond, attendu 40, obtenu {len(all_raw)}"
    )


def test_add_articles_dedup_only():
    """La déduplication par URL est le seul filtre — pas de limite de volume."""
    all_raw: list[dict] = []
    seen_urls: set[str] = set()
    in_firestore = {"https://already.example.com/1", "https://already.example.com/2"}

    def already_exists(url: str) -> bool:
        return url in in_firestore

    def _add_articles_to_batch(articles: list[dict]) -> None:
        for raw in articles:
            url = raw["article_url"]
            if url in seen_urls or already_exists(url):
                continue
            seen_urls.add(url)
            all_raw.append(raw)

    articles = [
        {"title": "Nouveau", "article_url": "https://new.example.com/1"},
        {"title": "Déjà en base 1", "article_url": "https://already.example.com/1"},
        {"title": "Déjà en base 2", "article_url": "https://already.example.com/2"},
        {"title": "Nouveau 2", "article_url": "https://new.example.com/2"},
        {"title": "Doublon run", "article_url": "https://new.example.com/1"},  # vu dans le run
    ]
    _add_articles_to_batch(articles)

    assert len(all_raw) == 2, f"Seuls les 2 nouveaux doivent passer, obtenu {len(all_raw)}"
    urls = [a["article_url"] for a in all_raw]
    assert "https://new.example.com/1" in urls
    assert "https://new.example.com/2" in urls


def test_enrich_articles_category_injected_in_keywords(monkeypatch):
    """La catégorie doit être en tête des mots-clés."""
    from processors import gemini_processor
    import json

    mock_response = [{
        "title_fr": "Test", "title_en": "Test",
        "short_description_fr": "Test.", "short_description_en": "Test.",
        "long_description_fr": "Test long.", "long_description_en": "Test long.",
        "keywords_fr": ["Kubernetes", "cluster"],
        "keywords_en": ["Kubernetes", "cluster"],
        "category": "DevOps",
    }]

    monkeypatch.setattr(gemini_processor, "_call_llm",
                        lambda prompt, models, thinking=True: json.dumps(mock_response))

    results = gemini_processor.enrich_articles_batch([SAMPLE_ARTICLES[1]])
    assert results[0]["keywords_fr"][0] == "DevOps", "Catégorie absente en tête des keywords_fr"
    assert results[0]["keywords_en"][0] == "DevOps", "Catégorie absente en tête des keywords_en"
