# Console admin — Rapport d'exécution & logs Cloud Run

## Contexte fonctionnel

À la fin de chaque run, le collector génère via le LLM un **rapport d'exécution** structuré (sources sollicitées, collecte Gmail, modèle LLM utilisé, anomalies). Ce rapport est stocké dans `reports/latest` et visible dans la console admin. En parallèle, l'admin peut consulter les **logs bruts Cloud Run** du job collector via l'API Cloud Logging.

## Objectif

- Donner une visibilité instantanée sur l'état du dernier run sans aller dans GCP Console.
- Diagnostiquer rapidement les anomalies (quota LLM, source indisponible, etc.).

## User Stories

### US-RPT-001 — Génération automatique du rapport d'exécution

**En tant que** système,
**je veux** générer un rapport LLM concis après chaque run,
**afin de** que l'admin comprenne en 30 secondes ce qui s'est passé.

**Description fonctionnelle**
À la fin de `run()`, le collector récupère tous les logs en mémoire (via un `_MemoryHandler` attaché au logger) et appelle `generate_run_report(logs, model_priority)`. Le LLM produit un markdown structuré : Sources sollicitées, Collecte emails, Traitement LLM, Résultat, Anomalies, Recommandations. Écrit dans `reports/latest`.

**Règles métier**
- Toujours généré (peu importe la valeur de `interest` ou autres settings).
- Les logs sont tronqués à 8000 caractères (constante `MAX_REPORT_LOGS`, réellement appliquée).
- Le rapport est **nettoyé avant publication** : certains modèles restituent leur brouillon (consignes reformulées, auto-corrections) avant la réponse finale. `_clean_report_output()` repart de la dernière occurrence de « **Sources sollicitées** » et exige au moins 3 des 5 sections attendues ; sinon la réponse est traitée comme un échec du modèle et la cascade monte d'un cran.
- Génération bornée : température 0,2 et 4000 tokens de sortie max — c'est une mise en forme, pas une création.
- Si tous les modèles LLM échouent → message "⚠️ Rapport indisponible — tous les modèles LLM ont échoué :" suivi de la cause réelle par modèle (code HTTP + message de l'API). Ne jamais annoncer un quota sans un 429 effectivement reçu.
- Le doc `reports/latest` écrase à chaque run (pas d'historique).

**Critères d'acceptation**
1. Après chaque run, `reports/latest.content` contient un markdown structuré.
2. Le champ `generated_at` est mis à jour.
3. Sections présentes : Sources, Collecte emails (si Gmail), Traitement LLM, Résultat, Anomalies.
4. Si aucune anomalie, la section "Anomalies" l'indique explicitement.

**Cas limites**
- Run sans aucune source active → le rapport mentionne "0 sources actives".
- Quota LLM épuisé → message warning explicite.

---

### US-RPT-002 — Afficher le dernier rapport d'exécution

**En tant qu'** admin,
**je veux** consulter le rapport du dernier run depuis l'UI,
**afin de** valider que la collecte s'est bien passée.

**Description fonctionnelle**
`GET /admin/report` (require_admin) renvoie le doc `reports/latest`. Le frontend rend le markdown (via la même lib `markdownToHtml` que la synthèse, donc XSS-safe).

**Critères d'acceptation**
1. La section "Rapport" affiche le contenu markdown rendu en HTML.
2. La date `generated_at` est visible (heure de génération).
3. Si aucun rapport (premier déploiement) → "Aucun rapport disponible".
4. Le bouton "Rafraîchir" permet de re-fetch.

**Cas limites**
- Rapport très long → scroll ou troncature ? À voir selon UX.

---

### US-LOG-001 — Consulter les logs bruts du collector Cloud Run

**En tant qu'** admin,
**je veux** voir les logs récents du collector Cloud Run Job,
**afin de** diagnostiquer un problème non couvert par le rapport LLM.

**Description fonctionnelle**
`GET /admin/logs?limit=100` (require_admin) appelle l'API Cloud Logging (`logging.googleapis.com/v2/entries:list`) avec un filtre `resource.type="cloud_run_job" AND resource.labels.job_name="collector"`. Renvoie une liste `{timestamp, severity, message}` triée par timestamp desc.

**Règles métier**
- Limit par défaut : 100, max : 500.
- Auth via service account (`google_auth_default` du backend).
- Severities incluses : tous niveaux (INFO, WARNING, ERROR).

**Critères d'acceptation**
1. La section "Logs" liste les logs récents avec timestamp + sévérité + message.
2. Filtrer par severity côté UI (optionnel).
3. Refresh manuel possible.
4. En cas d'erreur API Cloud Logging → 502.

**Cas limites**
- Service account sans permission `logging.logEntries.list` → 502.
- Aucun run récent → liste vide avec message "Aucun log disponible".

---

## Dépendances

- Backend : routes `GET /admin/report`, `GET /admin/logs`.
- Collector : `generate_run_report()` dans `gemini_processor.py`, `_MemoryHandler` dans `main.py`.
- Cloud Logging API + service account avec rôle `roles/logging.viewer`.
- Frontend : composant `LogViewer.tsx` dans `/admin`.

## Contraintes

- **Métier** : un seul rapport est conservé (`reports/latest`). Pas d'historique des rapports. Si besoin d'audit, à enrichir.
- **Coût** : 1 appel LLM supplémentaire par run pour le rapport (même si quota épuisé sur les autres, fallback graceful).
- **Sécurité** : les logs peuvent contenir des données sensibles (URLs, IDs). Restreint admin.
