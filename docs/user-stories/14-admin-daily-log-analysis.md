# Console admin — Analyse quotidienne des logs GCP

## Contexte fonctionnel

Chaque nuit, un **job d'analyse de logs** interroge Cloud Logging pour récupérer l'intégralité des logs applicatifs des 24 dernières heures (backend Cloud Run service, collector Cloud Run Job, frontend Cloud Run service). Il soumet ces logs à Gemini, qui produit un **rapport structuré et actionnable** : liste de points notables, chacun accompagné d'un prompt de correction à destination d'une IA, d'une date et d'un niveau de priorité. Le rapport est stocké dans Firestore (`log_analyses/{date}`) et consultable par les admins depuis une nouvelle page dédiée.

Ce rapport complète les deux outils existants :
- **US-RPT-001/002** (`reports/latest`) : rapport d'exécution du collector, généré en fin de run, limité aux logs internes du collector.
- **US-LOG-001** (`GET /admin/logs`) : logs bruts Cloud Run du collector, non analysés.

La nouveauté ici : périmètre élargi à **tous les services**, cadence indépendante (nocturne), et output **actionnable** (prompt de correction, sévérité).

## Objectif

- Identifier proactivement les anomalies sans surveiller la GCP Console.
- Fournir pour chaque anomalie un prompt prêt à l'emploi, utilisable directement dans Claude Code ou Gemini pour guider la correction.
- Constituer un historique consultable par date.

---

## User Stories

### US-DLA-001 — Déclenchement nocturne du job d'analyse

**En tant que** système,
**je veux** exécuter automatiquement le job d'analyse chaque nuit à 02h00 CET,
**afin de** disposer d'un rapport frais au matin sans intervention manuelle.

**Description fonctionnelle**
Un nouveau **Cloud Run Job** `log-analyzer` (script Python dans `log-analyzer/main.py`) est déclenché par **Cloud Scheduler** (cron `0 5 * * *`, timezone `Europe/Paris`). Il est indépendant du collector. Son Dockerfile est distinct ; le CI/CD le déploie comme un Cloud Run Job séparé via `gcloud run jobs update log-analyzer` (chemin `log-analyzer/**` dans `dorny/paths-filter`).

**Règles métier**
- Le job tourne même si le collector n'a pas tourné dans la journée.
- Si une exécution échoue (quota LLM, Cloud Logging indisponible), Cloud Scheduler effectue un retry selon sa politique par défaut (1 tentative, délai 5 min). Les erreurs sont loguées dans Cloud Logging.
- Le job n'écrase pas un rapport existant du même jour s'il a déjà réussi (`generated_at` présent en Firestore).

**Critères d'acceptation**
1. Le job `log-analyzer` apparaît dans Cloud Run > Jobs avec un historique d'exécutions.
2. Cloud Scheduler montre un run quotidien réussi à 05h00.
3. Si le job est relancé manuellement le même jour et qu'un rapport existe déjà, il s'arrête avec log "Rapport du jour déjà généré — skip."
4. Un échec du job ne produit pas d'entrée Firestore partielle (atomicité).

**Cas limites**
- Quota Gemini épuisé → voir US-DLA-003.
- Cloud Logging API en erreur → job s'arrête en erreur, aucune entrée Firestore créée.

---

### US-DLA-002 — Collecte des logs GCP des dernières 24h

**En tant que** job d'analyse,
**je veux** récupérer tous les logs applicatifs des 24 dernières heures depuis Cloud Logging,
**afin de** couvrir l'intégralité de l'activité de la plateforme.

**Description fonctionnelle**
Appel à l'API Cloud Logging (`logging.googleapis.com/v2/entries:list`) avec le filtre :

```
resource.type=("cloud_run_revision" OR "cloud_run_job")
AND resource.labels.project_id="tech-news-aggregator-001"
AND timestamp >= "{now - 24h}"
AND severity >= "WARNING"
```

Services couverts : `backend` (Cloud Run revision), `collector` (Cloud Run job), `frontend` (Cloud Run revision). Les logs `INFO` et `DEBUG` sont exclus par défaut pour limiter le volume et le bruit LLM. Les logs récupérés sont triés par `timestamp` asc. Authentification via les credentials par défaut du service account du job.

**Règles métier**
- Limite de récupération : `MAX_LOG_ENTRIES = 2000` entrées (protection coût + taille de prompt LLM).
- Si le volume dépasse 2000 entrées sur la fenêtre 24h, priorité aux `ERROR` et `CRITICAL` d'abord, puis `WARNING` jusqu'à la limite.
- Chaque entrée est normalisée en `{timestamp, severity, service, message}` avant envoi au LLM.
- Le service account doit avoir le rôle `roles/logging.viewer` sur le projet.

**Critères d'acceptation**
1. Les logs des trois services (backend, collector, frontend) sont bien représentés dans les entrées collectées.
2. Si 0 log `WARNING+` dans les 24h → le rapport indique "Aucune anomalie détectée sur la période."
3. Si > 2000 entrées → les `ERROR`/`CRITICAL` sont priorisés, le rapport mentionne "Volume tronqué à 2000 entrées."
4. La collecte se termine en moins de 60 secondes pour un volume normal.

**Cas limites**
- Service account sans `logging.viewer` → erreur HTTP 403, job s'arrête sans Firestore write.
- Region `europe-west1` : le filtre inclut le label `resource.labels.location="europe-west1"` pour ne pas récupérer des logs d'autres projets en cas de ressources partagées.

---

### US-DLA-003 — Analyse LLM et génération du rapport structuré

**En tant que** job d'analyse,
**je veux** soumettre les logs collectés à Gemini pour en extraire les points notables,
**afin de** produire un rapport actionnable sans lecture manuelle.

**Description fonctionnelle**
Les logs normalisés sont assemblés en un prompt envoyé à Gemini (cascade de fallback sur `model_priority` lue depuis `settings/global`, identique au collector). Le LLM retourne un JSON structuré.

**Format attendu en sortie LLM :**
```json
{
  "items": [
    {
      "point_notable": "Texte décrivant l'anomalie ou l'événement significatif observé dans les logs.",
      "prompt_correction": "Prompt rédigé à la première personne, prêt à copier dans Claude Code : contexte + instruction de correction.",
      "date": "2026-05-16T14:23:00Z",
      "priorite": "CRITIQUE|HAUTE|MOYENNE|BASSE"
    }
  ],
  "resume": "Synthèse globale de la période en 2-3 phrases."
}
```

**Règles métier**
- Niveaux de priorité : `CRITIQUE` (erreur bloquante / perte de données), `HAUTE` (dégradation service), `MOYENNE` (anomalie non bloquante), `BASSE` (avertissement ou tendance à surveiller).
- Le prompt LLM demande au moins `items` avec : ① les erreurs répétées (≥ 3 occurrences) ; ② les erreurs uniques de sévérité ERROR/CRITICAL ; ③ les tendances inhabituelles (pic de 4xx, latence anormale si détectable dans les logs).
- Les items sont triés par priorité décroissante (`CRITIQUE` en premier).
- Maximum 20 items par rapport (écrêtage côté LLM dans le prompt).
- Si tous les modèles Gemini échouent → `items: []`, `resume: "⚠️ Analyse indisponible — tous les modèles LLM sont hors quota."`.
- Le `prompt_correction` doit inclure le nom du service concerné, l'heure de l'événement, et une instruction concrète ("Recherche dans `backend/app/routers/articles.py` pourquoi…").

**Critères d'acceptation**
1. Le JSON retourné est valide et parseable sans erreur.
2. Chaque item a les 4 champs requis (`point_notable`, `prompt_correction`, `date`, `priorite`).
3. Les items `CRITIQUE` et `HAUTE` ont un `prompt_correction` mentionnant explicitement le service et le fichier/route concerné si détectable.
4. Si 0 anomalie dans les logs → `items: []` et `resume` positif ("Aucune anomalie détectée").
5. Le fallback "quota épuisé" est stocké normalement en Firestore (pas d'exception levée).

**Cas limites**
- LLM retourne un JSON malformé → retry une fois ; si toujours invalide → fallback quota épuisé.
- Logs contenant des données sensibles (tokens, emails) → le prompt LLM précise de ne **pas** reproduire les valeurs sensibles dans les items, seulement décrire le pattern.

---

### US-DLA-004 — Stockage du rapport dans Firestore

**En tant que** job d'analyse,
**je veux** écrire le rapport structuré dans Firestore,
**afin de** le rendre accessible au backend sans couplage direct.

**Description fonctionnelle**
Le rapport est écrit dans la collection `log_analyses` avec pour clé de document la date d'analyse (`YYYY-MM-DD` correspondant à la journée couverte, pas la date d'exécution du job).

**Structure du document Firestore :**
```json
{
  "date": "2026-05-16",
  "generated_at": "2026-05-17T05:03:47Z",
  "period_start": "2026-05-16T00:00:00Z",
  "period_end": "2026-05-17T00:00:00Z",
  "logs_count": 342,
  "resume": "...",
  "items": [
    {
      "point_notable": "...",
      "prompt_correction": "...",
      "date": "2026-05-16T14:23:00Z",
      "priorite": "HAUTE"
    }
  ]
}
```

**Règles métier**
- Clé = date couverte (ex. `2026-05-16`), pas la date d'exécution (le job tourne à 02h00 le lendemain).
- L'écriture est atomique : le document n'est créé qu'une fois le JSON LLM validé.
- Pas de purge automatique des anciens rapports (politique de rétention à définir — suggestion : 30 jours, via la même logique que `retention_days` des articles).
- Les règles Firestore : `allow write: if false` (écriture backend/job uniquement), `allow read: if request.auth.token.role == "admin"` (accès restreint admin).

**Critères d'acceptation**
1. Après un run réussi, `log_analyses/2026-05-16` existe avec tous les champs.
2. `logs_count` reflète le nombre d'entrées effectivement récupérées depuis Cloud Logging.
3. Un second run le même jour ne crée pas de doublon (clé idempotente, US-DLA-001 rule #3 s'applique).
4. Les règles Firestore bloquent un accès non-admin en lecture.

**Cas limites**
- Firestore indisponible → job s'arrête en erreur, Cloud Scheduler retente.
- Document déjà existant avec `generated_at` → skip (idempotence).

---

### US-DLA-005 — Endpoint backend pour servir le rapport

**En tant qu'** admin (via le frontend),
**je veux** accéder au rapport d'analyse de logs via une API REST sécurisée,
**afin de** le charger dans l'UI sans accès direct à Firestore.

**Description fonctionnelle**
Deux nouvelles routes dans `backend/app/routers/admin.py` (require_admin) :

- `GET /admin/log-analysis` → renvoie le rapport d'aujourd'hui (`log_analyses/{today}`).
- `GET /admin/log-analysis/{date}` → renvoie le rapport d'une date précise (format `YYYY-MM-DD`).

**Structure de la réponse :**
```json
{
  "date": "2026-05-16",
  "generated_at": "2026-05-17T05:03:47Z",
  "logs_count": 342,
  "resume": "...",
  "items": [ { "point_notable": "...", "prompt_correction": "...", "date": "...", "priorite": "HAUTE" } ]
}
```

**Règles métier**
- Si le document n'existe pas encore pour aujourd'hui (job pas encore tourné ou en échec) → `404` avec `{"detail": "Rapport non disponible pour cette date."}`.
- Accès restreint admin (`require_admin`), identique aux autres routes admin.
- Pas de pagination : le nombre d'items est plafonné à 20 côté LLM (US-DLA-003).

**Critères d'acceptation**
1. `GET /admin/log-analysis` retourne 200 avec le rapport du jour si disponible.
2. `GET /admin/log-analysis/2026-05-15` retourne le rapport du 15 mai si disponible.
3. `GET /admin/log-analysis/2099-01-01` retourne 404.
4. Un reader (non-admin) reçoit 403.
5. Format date invalide (`/admin/log-analysis/foo`) → 422.

**Cas limites**
- Firestore indisponible → 503 (comportement existant du backend sur les erreurs Firestore).

---

### US-DLA-006 — UI admin : page de consultation du rapport d'analyse

**En tant qu'** admin,
**je veux** consulter le rapport d'analyse des logs du jour depuis l'interface admin,
**afin de** identifier rapidement les points d'attention sans ouvrir GCP Console.

**Description fonctionnelle**
Nouvelle page `/admin/log-analysis` dans le frontend. Elle charge `GET /admin/log-analysis` via SWR. Elle affiche :
- Un résumé global (`resume`) en haut.
- Une liste de cards triées par priorité décroissante, chacune affichant : badge de priorité coloré (rouge/orange/jaune/gris selon `priorite`), date/heure de l'événement, `point_notable`, et un bouton "Copier le prompt" pour mettre `prompt_correction` dans le presse-papier.
- Un sélecteur de date (input `date`, max = aujourd'hui) pour charger un rapport antérieur via `GET /admin/log-analysis/{date}`.
- Un bouton "Rafraîchir" pour re-fetch sans reload.

**Règles métier**
- La page est accessible uniquement au rôle `admin` (redirect `/` si reader, identique aux autres pages admin).
- L'icône de priorité suit la convention : `CRITIQUE` = rouge, `HAUTE` = orange, `MOYENNE` = jaune, `BASSE` = gris.
- Le bouton "Copier le prompt" utilise `navigator.clipboard.writeText` et affiche "✓ Copié !" pendant 2s.
- Si aucun rapport disponible pour la date sélectionnée → message "Aucun rapport disponible pour cette date."
- Le résumé est du texte brut (pas de markdown rendu — le LLM doit produire du texte simple pour ce champ).

**Critères d'acceptation**
1. La page `/admin/log-analysis` est accessible et protégée (reader → redirect).
2. Les items s'affichent triés par priorité : CRITIQUE > HAUTE > MOYENNE > BASSE.
3. Cliquer "Copier le prompt" sur un item CRITIQUE copie le `prompt_correction` exact dans le presse-papier.
4. Changer la date dans le sélecteur recharge le rapport correspondant (ou affiche le message 404).
5. Si 0 item et `resume` positif → "Aucune anomalie détectée" est affiché de façon distincte (pas une liste vide silencieuse).
6. Le bouton "Rafraîchir" déclenche un refetch visible dans l'onglet Network.
7. La page figure dans la navigation admin (lien "Analyse logs" dans la sidebar ou onglet, selon l'UX existante).

**Cas limites**
- Backend renvoie 503 (Firestore down) → message d'erreur "Service temporairement indisponible".
- `prompt_correction` très long → zone de texte scrollable dans la card, pas de troncature.

---

## Dépendances

- **Nouveau service** : `log-analyzer/` (Cloud Run Job Python), Dockerfile, déploiement CI/CD.
- **Cloud Scheduler** : nouvelle règle cron sur `log-analyzer`.
- **IAM** : service account du job avec `roles/logging.viewer` + `roles/datastore.user`.
- **Backend** : 2 nouvelles routes `GET /admin/log-analysis` et `GET /admin/log-analysis/{date}` dans `admin.py`.
- **Firestore** : nouvelle collection `log_analyses`, règle de sécurité à ajouter dans `infrastructure/firestore.rules`.
- **Frontend** : nouvelle page `/admin/log-analysis/page.tsx`, composant `LogAnalysisCard.tsx`.
- **Gemini** : même cascade `model_priority` que le collector (lue depuis `settings/global`).
- **CI/CD** : `dorny/paths-filter` étendu avec le path `log-analyzer/**` → job `deploy-log-analyzer`.

## Contraintes

- **Coût Cloud Logging** : `entries.list` est facturé au volume de données lues. Le filtre `severity >= WARNING` est essentiel pour limiter la facture. Surveiller la métrique de coût après déploiement.
- **Coût LLM** : 1 appel Gemini par nuit, plafonné à 2000 lignes de logs. Coût marginal.
- **Sécurité** : les logs peuvent contenir des tokens, emails, IPs. La collection `log_analyses` est en lecture `admin` uniquement. Le prompt LLM demande explicitement de ne pas reproduire les valeurs sensibles.
- **Pas d'historique infini** : suggérer une politique de rétention de 30 jours (à configurer dans `settings/global` ou en dur dans le job). À affiner selon usage.
- **Séparation collector / log-analyzer** : le job d'analyse des logs est délibérément séparé du collector pour éviter qu'une panne de l'un n'impacte l'autre.
