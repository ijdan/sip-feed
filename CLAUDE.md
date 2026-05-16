# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Tech news aggregator (codename **Sip-feed**) déployé sur GCP. Trois services indépendants partagent une seule base Firestore :

- **backend/** — API FastAPI (Cloud Run service), expose `/articles`, `/sources`, `/users`, `/admin`, `/auth`.
- **frontend/** — Next.js 14 App Router + NextAuth (Cloud Run service). NextAuth gère le SSO Google/GitHub côté front, puis échange le token avec le backend qui émet le JWT applicatif.
- **collector/** — script Python (Cloud Run **Job**, déclenché par Cloud Scheduler). Scrape des sites web + lit des newsletters Gmail (TLDR), enrichit via Gemini (FR + EN en un seul appel), écrit dans Firestore.

Projet GCP : `tech-news-aggregator-001` / région `europe-west1`. Voir `docs/Schema.mmd` pour le diagramme d'architecture.

## Commandes courantes

### Démarrage local (toujours via l'émulateur Firestore — la prod n'est jamais touchée)

```bash
./start-emulator.sh        # Firestore emulator sur :8080, UI sur :4000 (restore auto depuis .firestore-emulator-data/)
./start-local.sh           # backend (:8000) + frontend (:3000) en parallèle, APP_ENV=local
./save-emulator.sh         # snapshot des données de l'émulateur vers .firestore-emulator-data/
./test-collector.sh        # exécute le collector contre l'émulateur local
```

`APP_ENV=local` active dans le backend (`app/routers/admin.py`) un garde-fou qui refuse les opérations destructives si l'émulateur n'est pas joignable — il est essentiel pour que `/admin/purge` etc. ne touchent pas la prod.

### Tests

```bash
./tests/run-tests.sh                                 # suite complète backend (API + scraper + collector) avec rapport
cd tests && pytest test_collector.py -v              # un seul fichier
cd tests && pytest test_collector.py::test_save_raw_articles_unique_ids -v   # un seul test
./install-hooks.sh                                   # installe le hook pre-push qui bloque le push si les tests échouent
```

`tests/conftest.py` lit `backend/.env` pour signer des JWT de test (fixtures `admin_token`, `reader_token`). Les tests fonctionnels du collector mockent `_call_llm` pour ne pas consommer de quota Gemini.

### Frontend

```bash
cd frontend && npm run dev       # dev server
cd frontend && npm run build     # build prod (utilisé par le Dockerfile multi-stage)
cd frontend && node_modules/.bin/tsc --noEmit   # type-check (utilisé par la CI)
```

Aucun linter, ni framework de test unitaire JS configuré — la CI ne fait que `tsc --noEmit`.

### Tests E2E Playwright

```bash
cd frontend && npm run e2e:install   # 1ère fois seulement : télécharge Chromium (~150 MB)
cd frontend && npm run e2e           # lance les 5 scénarios E2E en headless
cd frontend && npm run e2e:ui        # mode UI interactif (debug)
```

Pré-requis : émulateur Firestore + backend + frontend démarrés (cf. `start-emulator.sh` + `start-local.sh`). Les tests sont dans `frontend/e2e/`, nommés `US-XXX-NNN — description` pour traçabilité avec les fichiers `docs/user-stories/*.md`. La CI exécute aussi ces tests via `.github/workflows/e2e.yml`.

### Tests d'acceptance Gherkin (pytest-bdd)

```bash
pip install -r tests/requirements.txt          # installe pytest + pytest-bdd
cd tests && pytest acceptance/ -v               # lance toutes les acceptance tests
cd tests && pytest acceptance/test_hello.py -v  # un fichier
```

Organisation :
- `features/*.feature` : scénarios Gherkin lisibles par l'humain (rédigés par toi, ou demain par Claude depuis un MCP/CLI).
- `tests/acceptance/*.py` : step definitions pytest-bdd (générées par le **Workflow 1** de la pipeline d'automatisation, cf. ci-dessous).
- `backend/app/features/` : code applicatif Python qui satisfait les scénarios (implémenté par le **Workflow 2**).

### Déploiement

**Le déploiement passe exclusivement par la CI** (`.github/workflows/ci-cd.yml`) — `git push` vers `main` rebuild + déploie automatiquement avec `dorny/paths-filter` : seul ce qui a changé est rebuild. Il n'y a pas de script de déploiement manuel : le workflow GitHub Actions est la source de vérité unique. Le déploiement collector met à jour un **Cloud Run Job** (pas un service) via `gcloud run jobs update`.

## Architecture — points qui demandent de lire plusieurs fichiers

### Authentification à deux niveaux

NextAuth (`frontend/src/lib/auth.ts`) gère le flow OAuth Google/GitHub côté front, **puis** envoie le token au backend (`/auth/google` ou `/auth/github` dans `backend/app/auth/google_oauth.py`). Le backend vérifie l'identité auprès du provider, upsert l'utilisateur dans Firestore (clé = email), et renvoie un **JWT applicatif** (HS256, signé avec `JWT_SECRET`). Ce JWT est stocké dans la session NextAuth (`session.accessToken`) et utilisé pour tous les appels API. Les rôles `admin` / `reader` sont portés par le JWT (`require_admin` dans `google_oauth.py`).

### Pipeline de collecte (`collector/main.py`)

Une exécution = 4 étapes orchestrées dans `run()` :
1. Lit `settings/global` depuis Firestore (liste de modèles Gemini priorisée, `llm_enabled`, `thinking_enabled`, `gmail_lookback_days`, `retention_days`, `interest`).
2. Scrape toutes les sources actives — Gmail traité **en premier** pour que les newsletters l'emportent sur l'attribution d'URL. Plafonné à `MAX_ARTICLES_PER_RUN = 20`. Dédup contre Firestore par `article_url`.
3. Enrichit via Gemini en un seul appel batch bilingue (`enrich_articles_batch` dans `processors/gemini_processor.py`) → titres/descriptions/keywords FR + EN simultanés. Cascade de fallback sur la `model_priority`. Si tous les modèles échouent : `save_raw_articles` écrit les articles bruts.
4. Si `settings.interest` est renseigné : `generate_synthesis` produit une synthèse markdown ciblée sur les 100 derniers articles, écrite dans `syntheses/{date}`. Toujours en fin de run : `generate_run_report` produit un rapport LLM des logs (via un `_MemoryHandler` qui capture tous les logs en mémoire), écrit dans `reports/latest`.

`COLLECTOR_SOURCE_ID` permet de cibler une source unique — utilisé par le bouton "collecter cette source" de l'admin.

### Déclenchement du collector depuis le backend (`admin.py`)

Deux chemins selon `APP_ENV` :
- **local** : `_trigger_local` lance `python main.py` en sous-processus avec le venv du collector, vers l'émulateur.
- **prod** : `_trigger_job` appelle l'API Cloud Run Jobs (`POST .../jobs/collector:run`) avec un token OAuth2 récupéré via les credentials par défaut. Les `containerOverrides.env` injectent `COLLECTOR_SOURCE_ID` quand on cible une source.

### Articles bilingues — compatibilité

`Article` (`backend/app/models/article.py`) garde des champs `title`, `short_description`, `long_description` **sans suffixe** pour rétrocompat. Le collector remplit toujours les deux (`title_fr` + `title`). Le frontend bascule entre FR/EN par état local (`lang` dans `page.tsx`), avec valeur initiale lue depuis `user_settings/{email}.default_lang`.

### Stats API (middleware non-bloquant)

`StatsMiddleware` (`backend/app/middleware.py`) intercepte uniquement les `GET /articles/*`, extrait l'identifiant (email du JWT ou IP), et incrémente `api_stats/{YYYY-MM-DD}.{identifier}` via `asyncio.create_task` (fire-and-forget). Les erreurs réseau sont silencieusement ignorées — les stats ne doivent jamais faire échouer une requête.

### Règles Firestore (`infrastructure/firestore.rules`)

Les `articles` sont **publics en lecture** (feed anonyme), mais toutes les écritures passent **exclusivement par le backend** (`allow write: if false` partout sauf `user_preferences`). Quand tu ajoutes une collection, pense à la règle correspondante.

## Pipeline d'automatisation Claude (.feature → tests → code → PR)

Trois workflows GitHub Actions s'enchaînent quand tu pousses un `.feature` Gherkin sur une branche `feature/**` :

1. **`generate-acceptance-tests.yml`** (Sonnet 4.6) — lit les `.feature` modifiés, génère les step definitions pytest-bdd dans `tests/acceptance/`, commit avec `[skip ci]`.
2. **`implement-feature.yml`** (Opus 4.7, max 15 turns) — implémente le code applicatif dans `backend/app/features/`, boucle test → fix → test jusqu'au vert ou épuisement du budget de turns, puis ouvre une **PR draft** vers `main`.
3. **`ci-cd.yml`** (existant) — sur merge de la PR vers `main`, build + déploie sur Cloud Run.

### Règles strictes pour le bot Claude dans la CI

- **Tout commit du bot a comme auteur `claude-bot@users.noreply.github.com`**. Les workflows filtrent sur cet email pour éviter les boucles bot → bot. On **n'utilise pas** `[skip ci]` dans le message car un squash merge en hériterait et bloquerait `ci-cd.yml` à tort.
- **Jamais de push direct sur `main`**. Le bot ouvre toujours une PR en **draft** (`gh pr create --draft`). La validation reste humaine.
- **Le bot ne modifie pas `main`** : il pousse sur la branche `feature/**` d'origine et y ouvre la PR.
- **Workflow 2 a un cap de 15 turns** : si épuisé sans succès, la PR est créée quand même avec un label `needs-human-review`.

### Convention de nommage

- Branche : `feature/<slug-court>` (ex. `feature/article-tagging`).
- Fichier Gherkin : `features/<slug-court>.feature`.
- Step definitions : `tests/acceptance/test_<slug>.py`.
- Code applicatif : `backend/app/features/<slug>/` (1 dossier par feature, contient les modules Python).

> **Important — déclenchement du pipeline** : les workflows `generate-acceptance-tests.yml` et `implement-feature.yml` ne se déclenchent **que** sur les branches `feature/**`. Les branches de travail Claude (`claude/**`) n'activent pas le pipeline. Quand une session Claude rédige un `.feature` sur une branche `claude/**`, il faut créer une branche `feature/<slug>` et y pousser le fichier pour lancer l'automatisation.

## Conventions implicites

- **Tout est en français** dans le code, les logs, les commentaires, les messages d'erreur API. Garde cette convention.
- Pas de tests automatisés côté frontend — la CI ne fait que `tsc --noEmit`.
- Pas de linter Python configuré — pas de `ruff`/`flake8`/`black` à invoquer.
- Catégories d'articles canoniques : `["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"]`. Définies en doublon dans `backend/app/routers/articles.py`, `backend/app/models/article.py`, et `collector/processors/gemini_processor.py` — modifier les trois ensemble.
- `DEFAULT_MODEL_PRIORITY` (liste de modèles Gemini) est dupliquée dans `collector/main.py`, `collector/processors/gemini_processor.py`, et `backend/app/routers/admin.py`. Quand un nouveau modèle est ajouté en tête de cette liste, le backend nettoie automatiquement les modèles inconnus stockés en Firestore et insère les nouveaux.
- Secrets en prod via Secret Manager (montés en env vars par `--set-secrets` dans `.github/workflows/ci-cd.yml`). En local : `backend/.env` et `collector/.env`, jamais commités (`.gitignore` les bloque).
- `gmail_token.json` est généré une seule fois via `collector/auth_gmail.py` et monté en env var `GMAIL_TOKEN` en prod.
