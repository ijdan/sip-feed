import os
import re
import base64
import json
from datetime import datetime
from urllib.parse import unquote, urlparse
from bs4 import BeautifulSoup
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Mots-clés à exclure pour filtrer les liens parasites (désabo, pub)
EXCLUDED_URL_PATTERNS = [
    "unsubscribe", "optout", "mailto:", "utm_",
    "refer.tldr.tech", "referral",
    "linkedin.com/jobs", "ashbyhq.com", "jobs.", "/careers", "greenhouse.io",
    "advertise", "sponsor", "feedback", "survey",
    "manage-preferences", "view-online", "view_online",
    "manage.tldrnewsletter.com", "tldr.tech/infose",
]

EXCLUDED_TITLE_PATTERNS = [
    "manage your", "subscribe", "unsubscribe", "view online",
    "create your own role", "send a friend", "refer a friend",
    "track your referral", "pulling back the curtain",
    "sponsor", "advertise", "click here", "check out the",
    "save your spot", "ship api", "see how ", "learn more",
]

MIN_TITLE_LENGTH = 20
TLDR_ARTICLE_MARKER = "minute read"  # marqueur présent sur tous les vrais articles TLDR


def _decode_tracking_url(href: str) -> str:
    """Extrait l'URL originale d'un lien de tracking TLDR."""
    if "tracking.tldrnewsletter.com/CL0/" in href:
        parts = href.split("/CL0/", 1)
        if len(parts) == 2:
            return unquote(parts[1]).split("/0100")[0].split("?")[0]
    return href


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


def _get_sibling_description(tag) -> str:
    """Récupère le texte descriptif qui suit un lien dans la newsletter."""
    texts = []
    for sibling in tag.next_siblings:
        name = getattr(sibling, "name", None)
        if name in ("a",):
            break
        text = sibling.get_text(strip=True) if name else str(sibling).strip()
        if text and len(text) > 20:
            texts.append(text)
        if len(" ".join(texts)) > 400:
            break
    return " ".join(texts)[:500]


def _extract_article_links(html: str, require_read_marker: bool = False) -> list[dict]:
    """Extrait les liens et descriptions d'une newsletter HTML."""
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    results = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)

        if not text or len(text) < MIN_TITLE_LENGTH:
            continue
        if any(p in href.lower() for p in EXCLUDED_URL_PATTERNS):
            continue
        if any(p in text.lower() for p in EXCLUDED_TITLE_PATTERNS):
            continue
        if require_read_marker and TLDR_ARTICLE_MARKER not in text.lower():
            continue

        # Décoder l'URL originale pour la déduplication
        original_url = _decode_tracking_url(href)
        if original_url in seen:
            continue

        clean_title = re.sub(r'\s*\(\d+\s*minute read\)', '', text, flags=re.IGNORECASE).strip()
        description = _get_sibling_description(a)
        seen.add(original_url)
        results.append({
            "title": clean_title,
            "article_url": original_url,
            "raw_content": f"{clean_title}. {description}".strip() if description else clean_title,
        })

    return results[:10]


def read_gmail_source(source: dict, lookback_days: int = 1) -> list[dict]:
    """Lit les emails d'un expéditeur donné et extrait les articles."""
    import logging
    logger = logging.getLogger(__name__)

    service = _get_gmail_service()
    sender = source.get("gmail_sender", "")

    results = service.users().messages().list(
        userId="me",
        q=f"from:{sender} newer_than:{lookback_days}d",
        maxResults=10,
    ).execute()

    messages = results.get("messages", [])
    logger.info(f"  Gmail : {len(messages)} email(s) trouvé(s) de {sender}")
    articles = []

    for i, msg_ref in enumerate(messages, 1):
        msg = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="full"
        ).execute()

        html_body = _decode_body(msg["payload"])
        is_tldr = "tldr" in sender.lower()
        links = _extract_article_links(html_body, require_read_marker=is_tldr)
        logger.info(f"  Email {i}/{len(messages)} : {len(links)} article(s) extrait(s)")

        for link in links:
            articles.append({
                **link,
                "source_name": source["name"],
                "source_id": source["id"],
                "published_at": datetime.utcnow().isoformat(),
            })

    return articles
