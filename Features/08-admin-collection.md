# Console admin — Déclencher la collecte

## Contexte fonctionnel

Le collector tourne en arrière-plan via **Cloud Scheduler** sur un rythme configuré (typiquement quotidien). L'admin peut le déclencher manuellement à tout moment depuis `/admin` (bouton "▶ Lancer la collecte") ou via l'API. Le mode local (APP_ENV=local) lance le collector en sous-processus contre l'émulateur Firestore.

## Objectif

- Permettre un déclenchement manuel pour test ou rattrapage.
- Garantir que les opérations destructives (purge, purge-and-collect) ne touchent jamais la prod par erreur depuis un environnement local.
- Donner un feedback immédiat (status 202 + message UI).

## User Stories

### US-COL-001 — Lancer une collecte manuelle

**En tant qu'** admin,
**je veux** déclencher un run complet du collector depuis l'UI,
**afin de** rafraîchir le feed sans attendre le prochain run programmé.

**Description fonctionnelle**
Bouton "▶ Lancer la collecte" dans `AdminSettings`. `POST /admin/collect` (require_admin) :
- En prod (APP_ENV non-local) : appelle l'API Cloud Run Jobs `POST .../jobs/collector:run` avec OAuth token.
- En local : lance `python main.py` en sous-processus depuis le venv collector, vers l'émulateur.

**Règles métier**
- Réponse immédiate `202 Accepted` + body `{status: "triggered" | "triggered_local"}`.
- Le run est **asynchrone** : pas de retour de complétion ni de logs en temps réel ici.
- En local, l'émulateur Firestore doit être joignable (port 8080) sinon 503.
- Aucune limitation de fréquence côté API.

**Critères d'acceptation**
1. Cliquer le bouton → `POST /admin/collect`.
2. UI affiche "Lancement…" puis "✓ Collecte lancée" pendant 4s.
3. En cas d'erreur Cloud Run Jobs → "✗ Erreur" + détail dans la console.
4. En local sans émulateur démarré → 503 + message clair.
5. Pas besoin de rafraîchir la page : le feed récupère les nouveaux articles via SWR au prochain mount.

**Cas limites**
- Run en cours déjà → un nouveau run peut se lancer en parallèle (Cloud Run Jobs autorise plusieurs exécutions simultanées). Pas de garde contre cela. Risque : dédup gère, mais coût LLM doublé.

---

### US-COL-002 — Purger toute la base d'articles

**En tant qu'** admin (et uniquement en local),
**je veux** supprimer tous les articles de la base,
**afin de** repartir d'une base vierge pour des tests.

**Description fonctionnelle**
`POST /admin/purge` (require_admin). Supprime tous les documents de `articles` par batch (500 docs par commit). Pas de bouton UI exposé par défaut — l'opération est accessible uniquement via API (Postman, curl avec JWT admin).

**Règles métier**
- **Garde-fou strict** : en local (APP_ENV=local), l'émulateur doit être joignable. Sinon 503.
- En prod : pas de garde — l'admin a la responsabilité d'appeler en pleine conscience.
- Suppression définitive, pas de soft-delete.

**Critères d'acceptation**
1. `POST /admin/purge` avec JWT admin → 204 No Content.
2. La base `articles` est vide après l'appel.
3. En local sans émulateur joignable → 503 avec message "Émulateur Firestore non disponible".
4. Avec JWT reader → 403.
5. Sans JWT → 401.

**Cas limites**
- Base très grande → la suppression peut durer plusieurs secondes (batchs successifs). Timeout HTTP possible si > 1 min.
- Les `user_preferences.dismissed` et `favorites` gardent des `id` orphans après purge — non nettoyés.

---

### US-COL-003 — Purger puis collecter

**En tant qu'** admin (typiquement en local),
**je veux** purger la base puis lancer immédiatement une collecte,
**afin de** obtenir une base "fraîche" en un appel.

**Description fonctionnelle**
`POST /admin/purge-and-collect` (require_admin). Chaîne les deux opérations.

**Critères d'acceptation**
1. L'appel exécute purge puis trigger_collection.
2. Réponse 202.
3. Mêmes garde-fous que purge en local (503 si pas d'émulateur).

---

### US-COL-004 — Collecter une seule source

Voir US-SRC-007 dans `07-admin-sources.md`. Endpoint dédié : `POST /admin/sources/{id}/collect`.

---

### US-COL-005 — Collecte planifiée par Cloud Scheduler

**En tant qu'** admin,
**je veux** que le collector tourne automatiquement chaque jour,
**afin de** ne pas avoir à déclencher manuellement.

**Description fonctionnelle**
Cloud Scheduler appelle l'endpoint OAuth2 du Cloud Run Job (configuré hors code, dans GCP Console / Terraform / gcloud). Le job tourne sans intervention.

**Règles métier**
- Schedule typique : `0 6 * * *` (tous les jours à 6h UTC).
- Authentification : Scheduler utilise un service account autorisé sur le Job.

**Critères d'acceptation**
1. À l'heure planifiée, le job se lance automatiquement (vérifiable dans Cloud Run Jobs → Historique).
2. Le rapport `reports/latest` est mis à jour après chaque run.
3. Les articles sont visibles dans le feed au plus tard à heure_planifiée + durée_run.

**Notes**
- La configuration du Cloud Scheduler n'est **pas dans le code** du repo. C'est une configuration GCP externe. Documenter dans un futur runbook.

---

## Dépendances

- Backend : `POST /admin/collect`, `POST /admin/purge`, `POST /admin/purge-and-collect`, `POST /admin/sources/{id}/collect`.
- Collector déployé en Cloud Run Job.
- Cloud Scheduler externe (config GCP).
- Émulateur Firestore en local.

## Contraintes

- **Métier** : la purge est destructive. Pas de UI exposée par défaut pour limiter les accidents en prod.
- **Technique** : pas de mécanisme de blocage si un run est déjà en cours.
- **Sécurité** : l'authentification Cloud Run Jobs depuis le backend nécessite un service account avec rôle `roles/run.invoker` sur le job.
