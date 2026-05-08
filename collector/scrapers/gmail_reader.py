import os
import base64
import json
from datetime import datetime
from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Mots-clés à exclure pour filtrer les liens parasites (désabo, pub)
EXCLUDED_URL_PATTERNS = ["unsubscribe", "optout", "mailto:", "click.", "track.", "utm_"]


def _get_gmail_service():
    token_json = os.environ.get("GMAIL_TOKEN")
    if token_json:
        import json
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    else:
        creds = Credentials.from_authorized_user_file("gmail_token.json", SCOPES)
    return build("gmail", "v1", credentials=creds)


def _decode_body(payload: dict) -> str:
    """Décode le corps HTML ou texte d'un email."""
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/html":
                data = part["body"].get("data", "")
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    data = payload.get("body", {}).get("data", "")
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore") if data else ""


def _extract_article_links(html: str) -> list[dict]:
    """Extrait les liens principaux d'une newsletter HTML en filtrant les liens parasites."""
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    results = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)

        if not text or len(text) < 10:
            continue
        if any(p in href.lower() for p in EXCLUDED_URL_PATTERNS):
            continue
        if href in seen:
            continue

        seen.add(href)
        results.append({"title": text, "article_url": href})

    return results[:10]  # max 10 articles par newsletter


def read_gmail_source(source: dict) -> list[dict]:
    """Lit les emails d'un expéditeur donné et extrait les articles."""
    service = _get_gmail_service()
    sender = source.get("gmail_sender", "")

    results = service.users().messages().list(
        userId="me",
        q=f"from:{sender} newer_than:1d",
        maxResults=5,
    ).execute()

    messages = results.get("messages", [])
    articles = []

    for msg_ref in messages:
        msg = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="full"
        ).execute()

        html_body = _decode_body(msg["payload"])
        links = _extract_article_links(html_body)

        for link in links:
            articles.append({
                **link,
                "raw_content": link["title"],
                "source_name": source["name"],
                "source_id": source["id"],
                "published_at": datetime.utcnow().isoformat(),
            })

    return articles
