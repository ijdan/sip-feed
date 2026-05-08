import os
import uuid
import time
from datetime import datetime
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.5-flash")

CATEGORIES = ["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"]

PROMPT_TEMPLATE = """
Tu es un assistant spécialisé en veille technologique.

Voici le contenu brut d'un article tech :
---
Titre : {title}
Contenu : {content}
---

Réponds en JSON strict avec ces champs :
{{
  "short_description": "résumé en 2 phrases maximum",
  "long_description": "résumé détaillé en 5 à 8 phrases",
  "category": "une valeur parmi {categories}"
}}
"""


def enrich_article(raw: dict, source: dict) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        title=raw["title"],
        content=raw.get("raw_content", "")[:2000],
        categories=", ".join(CATEGORIES),
    )

    time.sleep(4)  # respect du quota free tier (15 rpm max)
    response = model.generate_content(prompt)
    text = response.text.strip()

    import json
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    enriched = json.loads(text)

    return {
        "id": str(uuid.uuid4()),
        "title": raw["title"],
        "short_description": enriched["short_description"],
        "long_description": enriched["long_description"],
        "article_url": raw["article_url"],
        "source_name": raw["source_name"],
        "source_id": raw["source_id"],
        "category": enriched.get("category", "Autre"),
        "published_at": raw.get("published_at", datetime.utcnow().isoformat()),
        "collected_at": datetime.utcnow().isoformat(),
    }
