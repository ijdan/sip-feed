"""Tests fonctionnels — scrapers web et TLDR."""
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collector"))


# ─── Scraper Web ─────────────────────────────────────────────────────────────

def test_web_scraper_returns_articles():
    from scrapers.web_scraper import scrape_source
    source = {"name": "Hacker News", "id": "test_hn",
              "type": "web", "url": "https://news.ycombinator.com"}
    articles = scrape_source(source)
    assert len(articles) >= 5, f"Trop peu d'articles : {len(articles)}"


def test_web_scraper_article_structure():
    from scrapers.web_scraper import scrape_source
    source = {"name": "Hacker News", "id": "test_hn",
              "type": "web", "url": "https://news.ycombinator.com"}
    articles = scrape_source(source)
    assert articles, "Aucun article extrait"
    for a in articles[:3]:
        assert a["article_url"].startswith("http"), f"URL invalide : {a['article_url']}"
        assert len(a["title"]) > 5, f"Titre trop court : {a['title']}"
        assert a["source_name"] == "Hacker News"
        assert a["source_id"] == "test_hn"


# ─── Parser TLDR ─────────────────────────────────────────────────────────────

# Format TLDR exact : titre seul sur un paragraphe, description sur le paragraphe suivant
TLDR_BODY = """TLDR AI 2026-05-14

Kubernetes Reaches 1B Downloads (5 MINUTE READ) [1]

Kubernetes, the container orchestration platform, has surpassed one billion pulls.
This milestone comes as cloud adoption continues to accelerate globally.

OpenAI Launches GPT-5 (3 MINUTE READ) [2]

OpenAI has released GPT-5 with improved reasoning capabilities and lower latency.
The model outperforms previous versions on standard benchmarks.

Buy My Merch (SPONSOR) [3]

Limited edition tech t-shirts. Use code TLDR for 20% off.

Links:
[1] https://kubernetes.io/blog/one-billion
[2] https://openai.com/gpt-5
[3] https://merch.example.com
"""

TLDR_BODY_WITH_JUNK = """TLDR SECURITY 2026-05-14

New Exploit Found (2 MINUTE READ) [1]

Researchers discovered a critical vulnerability in OpenSSL 3.x affecting most Linux systems.
The patch is available and should be applied immediately.

Unsubscribe From This Newsletter [2]

Click here to unsubscribe from TLDR Security.

Short (1 MINUTE READ) [3]

Too.

Links:
[1] https://security.example.com/openssl
[2] https://tldrnewsletter.com/unsubscribe
[3] https://example.com/short
"""


def test_tldr_parser_extracts_articles():
    from scrapers.gmail_reader import _parse_tldr_articles
    articles = _parse_tldr_articles(TLDR_BODY)
    assert len(articles) == 2, f"Attendu 2, obtenu {len(articles)}"


def test_tldr_parser_correct_fields():
    from scrapers.gmail_reader import _parse_tldr_articles
    articles = _parse_tldr_articles(TLDR_BODY)
    a = articles[0]
    assert a["title"] == "Kubernetes Reaches 1B Downloads"
    assert a["article_url"] == "https://kubernetes.io/blog/one-billion"
    assert "billion" in a["raw_content"].lower() or "kubernetes" in a["raw_content"].lower()


def test_tldr_parser_filters_sponsor():
    from scrapers.gmail_reader import _parse_tldr_articles
    articles = _parse_tldr_articles(TLDR_BODY)
    titles = [a["title"] for a in articles]
    assert not any("merch" in t.lower() or "sponsor" in t.lower() for t in titles)


def test_tldr_parser_filters_short_descriptions():
    from scrapers.gmail_reader import _parse_tldr_articles
    articles = _parse_tldr_articles(TLDR_BODY_WITH_JUNK)
    titles = [a["title"] for a in articles]
    assert "Short" not in titles, "Article avec description trop courte retenu"


def test_tldr_parser_filters_unsubscribe():
    from scrapers.gmail_reader import _parse_tldr_articles
    articles = _parse_tldr_articles(TLDR_BODY_WITH_JUNK)
    urls = [a["article_url"] for a in articles]
    assert not any("unsubscribe" in u for u in urls)


def test_tldr_parser_detects_category():
    from scrapers.gmail_reader import _detect_tldr_category
    assert _detect_tldr_category(TLDR_BODY) == "AI"
    assert _detect_tldr_category(TLDR_BODY_WITH_JUNK) == "Security"
    assert _detect_tldr_category("random body without header") is None
