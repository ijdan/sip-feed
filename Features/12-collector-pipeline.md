# Pipeline du collector — Scraping, parsing, enrichissement LLM

## Contexte fonctionnel

Le **collector** est un script Python autonome qui tourne dans un Cloud Run Job. À chaque run, il :
1. Lit les paramètres globaux depuis Firestore.
2. Scrape les sources actives (web + Gmail TLDR).
3. Déduplique contre la base et au sein du batch.
4. Enrichit en bilingue (FR + EN simultanés) via un seul appel batch à Gemini.
5. Sauvegarde dans Firestore.
6. Applique la rétention si configurée.
7. Génère synthèse (si centre d'intérêt) + rapport d'exécution LLM.

## Objectif

- Récolter du contenu tech qualifié de manière automatisée.
- Enrichir chaque article (titre, description, catégorie, keywords) en deux langues.
- Garantir la déduplication et la résilience aux pannes LLM.

## User Stories

### US-COL-PIPE-001 — Lire les paramètres globaux au démarrage

**En tant que** collector,
**je veux** lire à chaque run les paramètres dans `settings/global`,
**afin de** que les modifications admin soient effectives au prochain run.

**Description fonctionnelle**
`get_global_settings()` lit le doc Firestore et applique les défauts (LLM enabled, thinking enabled, model_priority, gmail_lookback_days=1, retention_days=0, interest=""). Nettoie aussi `model_priority` (retire les modèles inconnus, ajoute les nouveaux).

**Critères d'acceptation**
1. Les valeurs lues sont loggées au démarrage du run.
2. Si un settings est manquant, les défauts sont appliqués.
3. La liste `model_priority` est mise à jour si DEFAULT_MODEL_PRIORITY a changé côté code.

---

### US-COL-PIPE-002 — Scraper les sources web (HTML)

**En tant que** collector,
**je veux** extraire les articles d'un site web via BeautifulSoup,
**afin de** récupérer titres et URLs.

**Description fonctionnelle**
`scrape_source(source)` dans `web_scraper.py` :
1. Valide le scheme http/https (anti-SSRF basique).
2. `httpx.get(url, timeout=15, follow_redirects=True)`.
3. Si hostname contient `ycombinator.com` → `_scrape_hacker_news` (sélecteur spécifique `tr.athing`).
4. Sinon → `_scrape_generic` qui tente 3 stratégies : balises `<article>`, puis `<h2>/<h3>` avec lien, puis `<a>` de plus de 30 chars.
5. Max 20 articles par source.

**Règles métier**
- Le `User-Agent` est `Mozilla/5.0 (compatible; TechNewsBot/1.0)`.
- Pas de retry en cas d'erreur réseau (loggé, source ignorée pour ce run).
- Timeout 15s par requête.

**Critères d'acceptation**
1. Hacker News retourne ≥ 5 articles avec URL valide.
2. Un site générique retourne ≥ 5 articles si présents.
3. URL invalide (scheme non http/https) → `ValueError`.
4. Erreur réseau → logged warning, retourne `[]` ou raise (à confirmer impl).
5. Pas de stockage de cookies (chaque run est stateless).

**Cas limites**
- Site qui retourne du JSON ou JavaScript → 0 articles extraits.
- Site avec rate limiting → 403/429 logged.

---

### US-COL-PIPE-003 — Parser les newsletters Gmail (format TLDR)

**En tant que** collector,
**je veux** extraire les articles d'une newsletter TLDR via parsing texte,
**afin de** capter les liens enrichis (titre + description + URL).

**Description fonctionnelle**
`read_gmail_source(source, lookback_days)` dans `gmail_reader.py` :
1. Auth Gmail API via `gmail_token.json` ou env `GMAIL_TOKEN`.
2. Liste les messages `from:{sender} newer_than:{X}d` (max 50).
3. Pour chaque email, décode le corps `text/plain` et détecte le format TLDR via regex `TLDR\s+([A-Z\s]+)\s+\d{4}-\d{2}-\d{2}`.
4. Si format reconnu : extrait les paragraphes type "Article Title (3 MINUTE READ) [N]\nDescription...".
5. Joint avec la section `Links:` pour obtenir l'URL.

**Règles métier**
- Filtre `_is_valid_tldr_entry` : doit avoir "X MINUTE READ" ou être un GitHub repo ; exclu si "SPONSOR".
- Description < 30 chars → ignoré.
- Si format non-TLDR → email ignoré (loggué "format non reconnu").

**Critères d'acceptation**
1. Un email TLDR AI 2025-01-15 produit ~10-20 articles valides.
2. Les sponsors sont exclus.
3. Les liens [N] sont correctement matchés à leur description.
4. La date `published_at` reflète `internalDate` de l'email.

**Cas limites**
- Newsletter Substack ou autre format → 0 articles, log "ignoré".
- Email sans `text/plain` (seulement HTML) → décodage incomplet, fallback récursif sur parts.

---

### US-COL-PIPE-004 — Déduplication intra-run et contre la base

**En tant que** collector,
**je veux** ignorer les articles déjà connus (URL identique),
**afin de** ne pas dupliquer ni gaspiller des appels LLM.

**Description fonctionnelle**
Pour chaque article candidat :
1. Check intra-run : `seen_urls: set[str]` (mémoire RAM).
2. Check contre la base : `already_exists(url)` query Firestore `where article_url == url`.
3. Si nouveau → ajouté au batch `all_raw[]` (jusqu'à `MAX_ARTICLES_PER_RUN = 20`).

**Règles métier**
- L'ordre des sources est : Gmail d'abord (priorité), puis web. Si une URL apparaît dans les deux, c'est Gmail qui gagne.
- Pas de normalisation d'URL (utm_params, trailing slash, http vs https → considérés distincts).

**Critères d'acceptation**
1. Une URL déjà en base ne passe pas dans le batch.
2. Une URL répétée entre deux sources de ce run n'apparaît qu'une fois.
3. Le log indique "Déjà collecté, ignoré" pour chaque dédup.

**Cas limites**
- Doublons sémantiques (mêmes article, deux URLs différentes) → non détecté, à corriger via `dedup_articles.py` manuellement.

---

### US-COL-PIPE-005 — Enrichir bilingue FR/EN en un seul appel batch

**En tant que** collector,
**je veux** envoyer tous les articles candidats en un seul appel à Gemini,
**afin de** minimiser les appels API et garantir la cohérence FR/EN.

**Description fonctionnelle**
`enrich_articles_batch(raw_articles, model_priority, thinking)` envoie un prompt unique contenant tous les articles avec leur titre + raw_content tronqué à 1500 chars. Gemini répond avec un tableau JSON de `{title_fr, title_en, short_description_fr, short_description_en, long_description_fr, long_description_en, category, keywords_fr, keywords_en}`. Cascade de fallback sur model_priority.

**Règles métier**
- Si tous les modèles échouent → `save_raw_articles(raw)` : sauvegarde sans enrichissement (titre = raw, descriptions = troncatures, catégorie = "Autre", keywords = []).
- La catégorie est validée contre `CATEGORIES` ; sinon "Autre".
- La catégorie est injectée en tête des `keywords_fr`/`keywords_en`.
- Génère un `id` UUID4 unique par article.

**Critères d'acceptation**
1. Pour 20 articles en input, 20 articles enrichis en output (même ordre).
2. Chaque article a les 6 champs bilingues + catégorie + 10-15 keywords par langue.
3. La catégorie est en tête des keywords.
4. Si LLM down, fallback save_raw avec champs minimaux.

**Cas limites**
- LLM répond avec un JSON malformé → exception, fallback save_raw.
- LLM répond avec un nombre d'articles différent (rare) → mapping par index, articles excédentaires ignorés.

---

### US-COL-PIPE-006 — Sauvegarder dans Firestore

**En tant que** collector,
**je veux** sauvegarder chaque article enrichi dans `articles/{uuid}`,
**afin de** le rendre disponible dans le feed.

**Description fonctionnelle**
Boucle sur `enriched_articles` : `db.collection("articles").document(article["id"]).set(article)`. Logue chaque sauvegarde.

**Critères d'acceptation**
1. Chaque article a un doc Firestore avec `id`, `title*`, `short_description*`, `long_description*`, `keywords_*`, `article_url`, `source_name`, `source_id`, `category`, `published_at`, `collected_at`.
2. Le doc ID == `article["id"]`.
3. Le feed reflète les nouveaux articles au prochain fetch (SWR revalidation).

---

### US-COL-PIPE-007 — Appliquer la rétention

**En tant que** collector,
**je veux** supprimer les articles trop anciens,
**afin de** maîtriser la taille de la base.

**Description fonctionnelle**
`apply_retention(retention_days)` : si > 0 et **si au moins un nouvel article a été collecté**, supprime tous les `articles` où `collected_at < now - retention_days`. Par batch de 500.

**Règles métier**
- Pas de purge si `retention_days = 0` (illimité).
- Pas de purge si aucun nouvel article (évite suppressions cascade involontaires).

**Critères d'acceptation**
1. Avec retention=7 et 1 nouvel article : tous les articles > 7 jours sont supprimés.
2. Avec retention=7 et 0 nouvel article : aucune purge.
3. Le log indique le nombre supprimé.

---

### US-COL-PIPE-008 — Mode source unique (ciblé)

**En tant qu'** admin,
**je veux** que le collector ne traite qu'une source spécifique,
**afin de** tester rapidement.

**Description fonctionnelle**
Variable d'environnement `COLLECTOR_SOURCE_ID`. Si set, le collector ne lit que `sources/{id}` (peu importe `active`). Sinon, lit toutes les sources `active=True`.

**Critères d'acceptation**
1. Avec `COLLECTOR_SOURCE_ID=xxx` : seule cette source est scrapée.
2. Source ID inexistant → run vide (pas d'erreur).
3. Source désactivée mais ciblée → traitée quand même.

---

## Dépendances

- Firestore (Settings, Sources, Articles, Reports, Syntheses).
- Gmail API + token (`gmail_token.json` ou env `GMAIL_TOKEN`).
- Gemini API (`GEMINI_API_KEY`).
- BeautifulSoup4, lxml, httpx, google-cloud-firestore.

## Contraintes

- **Technique** : `MAX_ARTICLES_PER_RUN = 20` codé en dur. Modification = redéploiement.
- **Métier** : seul le format TLDR est parsé pour Gmail. Autres newsletters → ignorées.
- **Coût** : 1 appel LLM batch + 1 synthèse + 1 rapport = 3 appels Gemini par run.
- **Sécurité** : pas de validation IP avancée des URLs sources (anti-SSRF partielle).
