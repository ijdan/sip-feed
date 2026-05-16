# GitHub Actions — Pipeline Sip-feed

Ce dossier contient les workflows GitHub Actions de Sip-feed. Deux familles :

## A. Pipeline qualité & déploiement classique (déjà en place)

| Fichier | Trigger | Rôle |
|---|---|---|
| `ci-cd.yml` | push `main` ou PR vers `main`, paths `backend/**`, `frontend/**`, `collector/**` | Build + déploiement Cloud Run (backend, frontend, collector) avec `dorny/paths-filter` (rebuild ciblé). Inclut un health-check post-deploy. **Fait office de "Workflow 3 deploy"** dans le diagramme de la pipeline Gherkin. |
| `e2e.yml` | push `main` / PR, paths `frontend/**` ou `backend/app/**` | Playwright contre une stack complète montée en CI (émulateur Firestore + backend uvicorn + frontend Next dev). |
| `security-scan.yml` | push `main` / PR, paths `backend/app/**` | Scanner statique custom (`agents/security_scanner.py`) avec 6 catégories de vulnérabilités. Fail si CRITIQUE détectée. |

## B. Pipeline d'automatisation Claude (Gherkin → tests → code → PR)

### Schéma global

```
┌───────────────────────────────────────────────────────────────────────────┐
│ Dev local                                                                 │
│   └─ écrit features/<slug>.feature → git push origin feature/<slug>       │
└───────────────────────────────────┬───────────────────────────────────────┘
                                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Workflow 1 : generate-acceptance-tests.yml          (Sonnet 4.6, 1 turn)  │
│   • Détecte les .feature modifiés                                         │
│   • Génère tests/acceptance/test_<slug>.py via Claude API                 │
│   • Commit "[skip ci] ..." + push sur feature/<slug>                      │
└───────────────────────────────────┬───────────────────────────────────────┘
                                    │ workflow_run
                                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Workflow 2 : implement-feature.yml             (Opus 4.7, ≤15 turns)      │
│   • Détecte la feature avec test mais sans implémentation                 │
│   • Boucle agentique avec tools read/write/edit/pytest/ls                 │
│   • Périmètre d'écriture : backend/app/features/ + tests/acceptance/      │
│   • Commit "[skip ci] ..." + push                                         │
│   • Ouvre PR DRAFT vers main :                                            │
│       ▸ 🟢 si tests verts                                                  │
│       ▸ 🔴 + label `needs-human-review` si max-turns atteint              │
└───────────────────────────────────┬───────────────────────────────────────┘
                                    │ humain review + merge PR
                                    ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Workflow 3 : ci-cd.yml                                                    │
│   • Build + deploy Cloud Run (paths-filter cible seulement ce qui change) │
└───────────────────────────────────────────────────────────────────────────┘
```

### Workflows

| Fichier | Modèle | Trigger | Permissions |
|---|---|---|---|
| `generate-acceptance-tests.yml` | `claude-sonnet-4-6` | push `feature/**` + paths `features/**/*.feature` | `contents: write` |
| `implement-feature.yml` | `claude-opus-4-7` | `workflow_run` après wf1, ou push direct `tests/acceptance/**` sans `[skip ci]` | `contents: write`, `pull-requests: write` |
| `guard-bot-loops.yml` | — | push toutes branches | `contents: read` |

### Garde-fous

- **`[skip ci]` obligatoire** sur les commits du bot (les deux workflows l'appliquent automatiquement).
- **Filtre `if: !contains(...head_commit.message, '[skip ci]')`** au niveau job pour éviter les re-déclenchements.
- **`guard-bot-loops.yml`** : abort tout workflow si les 5 derniers commits consécutifs proviennent de `claude-bot`.
- **Périmètre d'écriture** dans `scripts/implement_feature.py` : restreint à `backend/app/features/` + `tests/acceptance/`. Toute tentative ailleurs renvoie "Erreur : écriture refusée".
- **Timeout** : 5 min sur wf1, 30 min sur wf2. Pytest timeout 90s par test. Agent loop max 15 turns.
- **Aucun push direct sur main** : le bot push sur la branche `feature/**` et ouvre une **PR draft**.

### Pré-requis côté GitHub

#### Secrets (Settings → Secrets and variables → Actions)

| Secret | Usage | Statut |
|---|---|---|
| `ANTHROPIC_API_KEY` | Workflows 1 & 2 — appel Claude API | À créer |
| `GCP_SA_KEY` | Workflow `ci-cd.yml` — déploiement Cloud Run | Déjà en place |

#### Workflow permissions (Settings → Actions → General → Workflow permissions)

- ✅ **Read and write permissions**
- ✅ **Allow GitHub Actions to create and approve pull requests**

Sans ces deux options, les workflows 1 & 2 ne pourront pas push ni créer de PR.

#### Branch protection rules sur `main`

À configurer via UI (Settings → Branches → Add rule) ou via `gh`. Recommandé :

```bash
gh api -X PUT "repos/ijdan/sip-feed/branches/main/protection" -f \
  required_status_checks='{"strict":true,"contexts":["CI/CD — Sip-feed","E2E — Playwright"]}' \
  -F enforce_admins=false \
  -f required_pull_request_reviews='{"required_approving_review_count":0,"dismiss_stale_reviews":true}' \
  -F allow_force_pushes=false \
  -F allow_deletions=false \
  -F required_linear_history=true
```

Effets :
- Tout merge vers `main` passe par PR.
- Force push interdit.
- Suppression de la branche interdite.
- `required_approving_review_count=0` : laisse l'option de merger soi-même ses PR draft sans approbation tierce (utile en solo).

### Coût estimé

| Workflow | Modèle | Coût par exécution (approx.) |
|---|---|---|
| wf1 (1 turn, 1 appel API) | Sonnet 4.6 | **$0.05–0.20** |
| wf2 (jusqu'à 15 turns, tool use) | Opus 4.7 | **$1–5** selon complexité |
| **Total par feature livrée** | | **~$1.50–5** |

GitHub Actions runners sont gratuits sur repos publics (illimité). Sur repo privé, ~5–10 min de runner par feature.

### Débogage rapide

- **Workflow 1 fail** : check secret `ANTHROPIC_API_KEY` présent + l'API key valide (pas expirée ni cap budget atteint).
- **Workflow 2 fail à `gh pr create`** : vérifier "Allow GitHub Actions to create PRs" dans Settings.
- **Workflow 2 atteint max-turns** : c'est OK, PR créée avec label `needs-human-review`. Pas une erreur de pipeline.
- **Boucle suspectée** : `guard-bot-loops.yml` doit bloquer. Sinon, vérifier que tes commits manuels n'ont pas un email contenant "claude-bot".
