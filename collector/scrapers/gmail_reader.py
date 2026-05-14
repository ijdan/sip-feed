import os
import re
import base64
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _get_gmail_service():
    token_json = os.environ.get("GMAIL_TOKEN")
    if token_json:
        import json
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    else:
        creds = Credentials.from_authorized_user_file("gmail_token.json", SCOPES)
    return build("gmail", "v1", credentials=creds)


def _decode_plain_body(payload: dict) -> str:
    """Extrait le corps texte brut de l'email (priorité text/plain)."""
    def _decode(data: str) -> str:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore") if data else ""

    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                return _decode(part["body"].get("data", ""))
        # Fallback récursif sur les parts imbriquées
        for part in payload["parts"]:
            result = _decode_plain_body(part)
            if result:
                return result
    return _decode(payload.get("body", {}).get("data", ""))


def _detect_tldr_category(body: str) -> str | None:
    """Détecte la catégorie TLDR depuis l'en-tête de la newsletter."""
    m = re.search(r'TLDR\s+([A-Z][A-Z\s]*?)\s+\d{4}-\d{2}-\d{2}', body)
    if not m:
        return None
    raw = m.group(1).strip().upper()
    mapping = {
        "AI": "AI", "INFORMATION SECURITY": "Security", "SECURITY": "Security",
        "FINTECH": "Fintech", "IT": "IT", "DEV": "Dev", "WEB DEV": "Dev",
        "CRYPTO": "Crypto", "FOUNDERS": "Founders", "MARKETING": "Marketing",
        "PRODUCT": "Product", "DESIGN": "Design", "DATA": "Data",
        "ROBOTICS": "Robotics",
    }
    return mapping.get(raw, raw.title())


def _parse_tldr_articles(body: str) -> list[dict]:
    """
    Parse le format texte brut TLDR :
      Article Title (3 MINUTE READ) [N]
      Description in English...

      Links:
      [N] https://url
    """
    links = _extract_numbered_links(body)
    paragraphs = _split_into_paragraphs(body)
    articles = []

    for i, p in enumerate(paragraphs):
        m = re.match(r'^(.+?)\s*\(([^)]+)\)\s*\[(\d+)\]\s*$', p)
        if not m:
            continue
        title, meta, link_num = m.group(1).strip(), m.group(2).strip().upper(), m.group(3)
        if not _is_valid_tldr_entry(title, meta):
            continue
        detail = (paragraphs[i + 1] if i + 1 < len(paragraphs) else '').strip()
        if not detail or len(detail) < 30:
            continue
        url = links.get(link_num, '')
        if not url:
            continue
        articles.append({'title': title, 'raw_content': detail, 'article_url': url})

    return articles


def _extract_numbered_links(body: str) -> dict[str, str]:
    """Extrait le dictionnaire [N] → URL depuis la section Links: du corps TLDR."""
    return {
        m.group(1): m.group(2).rstrip('.')
        for m in re.finditer(r'\[(\d+)\]\s+(https?://\S+)', body)
    }


def _split_into_paragraphs(body: str) -> list[str]:
    """Découpe le corps de l'email en paragraphes (avant la section Links:)."""
    links_idx = body.rfind('Links:')
    content = body[:links_idx] if links_idx > 0 else body
    return [re.sub(r'\s+', ' ', p).strip() for p in re.split(r'\r?\n\s*\r?\n', content)]


def _is_valid_tldr_entry(title: str, meta_upper: str) -> bool:
    """Vérifie qu'une entrée TLDR est un vrai article (pas un sponsor, pas sans durée de lecture)."""
    if 'SPONSOR' in meta_upper or 'SPONSOR' in title.upper():
        return False
    has_read_time = bool(re.search(r'\d+\s+MINUTE\s+READ', meta_upper))
    is_github = 'GITHUB REPO' in meta_upper
    return has_read_time or is_github


def read_gmail_source(source: dict, lookback_days: int = 1) -> list[dict]:
    """Lit les emails d'un expéditeur et extrait les articles."""
    import logging
    logger = logging.getLogger(__name__)

    service = _get_gmail_service()
    sender = source.get("gmail_sender", "")

    results = service.users().messages().list(
        userId="me",
        q=f"from:{sender} newer_than:{lookback_days}d",
        maxResults=50,
    ).execute()

    messages = results.get("messages", [])
    logger.info(f"  Gmail : {len(messages)} email(s) trouvé(s) de {sender}")

    all_articles = []
    for i, msg_ref in enumerate(messages, 1):
        msg = service.users().messages().get(
            userId="me", id=msg_ref["id"], format="full"
        ).execute()

        # Date réelle de réception de l'email (internalDate en ms)
        email_date = datetime.utcfromtimestamp(
            int(msg.get("internalDate", 0)) / 1000
        ).isoformat()

        body = _decode_plain_body(msg["payload"])
        category = _detect_tldr_category(body)

        if category:
            articles = _parse_tldr_articles(body)
            logger.info(f"  Email {i}/{len(messages)} [TLDR {category}] du {email_date[:10]} : {len(articles)} article(s)")
        else:
            articles = []
            logger.info(f"  Email {i}/{len(messages)} : format non reconnu, ignoré")

        for art in articles:
            all_articles.append({
                **art,
                "source_name": source["name"],
                "source_id": source["id"],
                "published_at": email_date,
            })

    logger.info(f"  Total extrait : {len(all_articles)} article(s)")
    return all_articles
