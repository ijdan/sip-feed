import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse


def _absolute_url(href: str, base_url: str) -> str:
    if href.startswith("http"):
        return href
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}{href}"


def _scrape_hacker_news(soup: BeautifulSoup, source: dict) -> list[dict]:
    articles = []
    for row in soup.select("tr.athing")[:20]:
        title_span = row.select_one("span.titleline > a")
        if not title_span:
            continue
        href = title_span.get("href", "")
        if not href or href.startswith("item?"):
            item_id = row.get("id", "")
            href = f"https://news.ycombinator.com/item?id={item_id}"
        articles.append({
            "title": title_span.get_text(strip=True),
            "article_url": href,
            "raw_content": title_span.get_text(strip=True),
            "source_name": source["name"],
            "source_id": source["id"],
            "published_at": datetime.utcnow().isoformat(),
        })
    return articles


def _scrape_generic(soup: BeautifulSoup, base_url: str, source: dict) -> list[dict]:
    articles = []
    seen = set()

    # Stratégie 1 : balises <article>
    candidates = soup.find_all("article")

    # Stratégie 2 : balises h2/h3 avec lien
    if not candidates:
        for tag in soup.find_all(["h2", "h3"]):
            a = tag.find("a", href=True)
            if a and a["href"] not in seen:
                seen.add(a["href"])
                candidates.append(tag)

    # Stratégie 3 : liens contenant des mots-clés tech
    if not candidates:
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if len(text) > 30 and a["href"] not in seen:
                seen.add(a["href"])
                candidates.append(a)

    for item in candidates[:20]:
        link_tag = item if item.name == "a" else item.find("a", href=True)
        title_tag = item if item.name in ["h2", "h3"] else item.find(["h1", "h2", "h3"])

        if not link_tag:
            continue
        title = (title_tag or link_tag).get_text(strip=True)
        href = _absolute_url(link_tag["href"], base_url)

        if not title or len(title) < 15 or href in seen:
            continue
        seen.add(href)

        articles.append({
            "title": title,
            "article_url": href,
            "raw_content": item.get_text(separator=" ", strip=True)[:1000],
            "source_name": source["name"],
            "source_id": source["id"],
            "published_at": datetime.utcnow().isoformat(),
        })

    return articles


def scrape_source(source: dict) -> list[dict]:
    url = source.get("url", "")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(
            f"URL invalide pour la source {source.get('name', '?')!r} : "
            f"scheme={parsed.scheme or 'absent'}, host={parsed.netloc or 'absent'}"
        )

    response = httpx.get(
        url,
        timeout=15,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; TechNewsBot/1.0)"},
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    hostname = urlparse(source["url"]).hostname or ""
    if "ycombinator.com" in hostname:
        return _scrape_hacker_news(soup, source)

    return _scrape_generic(soup, source["url"], source)
