# Features — User Stories de Sip-feed

Ce dossier contient les user stories de l'application Sip-feed, organisées par fonctionnalité. Chaque fichier est exploitable directement par les équipes Produit, Dev et QA : il décrit le contexte, les US au format **En tant que / Je veux / Afin de**, les critères d'acceptation testables, les cas limites, les dépendances et les contraintes.

## Index

### Côté utilisateur final

| # | Fichier | Périmètre |
|---|---|---|
| 01 | [01-authentication.md](./01-authentication.md) | Connexion OAuth Google/GitHub, JWT applicatif, rôles |
| 02 | [02-feed-display.md](./02-feed-display.md) | Affichage du feed, pagination "Afficher plus", bilingue FR/EN, colonnes |
| 03 | [03-feed-filters.md](./03-feed-filters.md) | Filtres : catégorie, sources, favoris/reading/lus, recherche par mots-clés |
| 04 | [04-article-actions.md](./04-article-actions.md) | Actions sur article : favoris, reading list, marquer lu, dismiss, restaurer |
| 05 | [05-user-settings.md](./05-user-settings.md) | Préférences user : thème, langue, colonnes, font_size, articles_per_page |

### Côté administrateur

| # | Fichier | Périmètre |
|---|---|---|
| 06 | [06-admin-global-settings.md](./06-admin-global-settings.md) | Paramètres globaux LLM (enabled, thinking, model_priority, lookback, retention) |
| 07 | [07-admin-sources.md](./07-admin-sources.md) | CRUD sources (web/Gmail), toggle actif, collecte ciblée |
| 08 | [08-admin-collection.md](./08-admin-collection.md) | Déclenchement collecte (manuelle/programmée), purge |
| 09 | [09-admin-synthesis.md](./09-admin-synthesis.md) | Synthèse LLM ciblée sur centre d'intérêt |
| 10 | [10-admin-stats.md](./10-admin-stats.md) | Statistiques d'usage (API calls, users, préférences) |
| 11 | [11-admin-reports-logs.md](./11-admin-reports-logs.md) | Rapport d'exécution LLM + logs Cloud Run |

### Côté système / backend

| # | Fichier | Périmètre |
|---|---|---|
| 12 | [12-collector-pipeline.md](./12-collector-pipeline.md) | Pipeline du collector : scraping, parsing, enrichissement, retention |
| 13 | [13-security-scan-ci.md](./13-security-scan-ci.md) | Scanner sécurité statique + workflow CI |
| 14 | [14-admin-daily-log-analysis.md](./14-admin-daily-log-analysis.md) | Analyse quotidienne des logs GCP par LLM + UI admin |

## Format type de chaque fichier

```
# Nom de la fonctionnalité

## Contexte fonctionnel
## Objectif

## User Stories

### US-XXX-NNN — Titre

**En tant que** ...
**Je veux** ...
**Afin de** ...

**Description fonctionnelle**
**Règles métier**
**Critères d'acceptation** (3 à 5, testables)
**Cas limites / erreurs**
**Given / When / Then** (si pertinent)

## Dépendances
## Contraintes (métier + technique)
```

## Conventions de nommage

- **Préfixes US** :
  - `US-AUTH-*` : authentification
  - `US-FEED-*` : feed display
  - `US-FLT-*` : filtres feed
  - `US-ACT-*` : actions sur article
  - `US-SET-*` : préférences user
  - `US-ADM-*` : paramètres admin globaux
  - `US-SRC-*` : sources admin
  - `US-COL-*` : déclenchement collecte
  - `US-SYN-*` : synthèse
  - `US-STA-*` : stats admin
  - `US-RPT-*` / `US-LOG-*` : rapport + logs
  - `US-COL-PIPE-*` : pipeline collector interne
  - `US-SEC-*` : scanner sécurité
  - `US-DLA-*` : analyse quotidienne des logs GCP

## Sources d'analyse

Ces user stories ont été dérivées de l'analyse :
- Du code backend (`backend/app/**`) — routes, modèles, middleware.
- Du code frontend (`frontend/src/**`) — pages, composants, hooks.
- Du code collector (`collector/**`) — pipeline scraping + LLM.
- Du workflow CI (`.github/workflows/`).
- Du document architecture (`docs/Schema.mmd`) et du CLAUDE.md.

Si une fonctionnalité majeure manque ou si une US doit être affinée, ajouter une ligne ici + créer/éditer le fichier dédié.
