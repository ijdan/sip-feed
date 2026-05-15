# Console admin — Statistiques

## Contexte fonctionnel

La page `/admin/stats` affiche des indicateurs d'usage : nombre d'utilisateurs enregistrés, volume d'appels API par identifiant (email ou IP), et statistiques par utilisateur (favoris, reading list, lus, dismissed). Les compteurs API sont incrémentés par un middleware non-bloquant à chaque `GET /articles/*`.

## Objectif

- Donner à l'admin une vue de la fréquentation et de l'engagement.
- Identifier les "power users" et les pics de trafic.
- Comprendre l'usage des fonctionnalités (favoris, reading list, etc.).

## User Stories

### US-STA-001 — Tracker les appels API par utilisateur

**En tant que** système,
**je veux** compter le nombre d'appels GET /articles/* par utilisateur authentifié (ou IP si anonyme),
**afin de** alimenter le tableau de bord admin.

**Description fonctionnelle**
Middleware `StatsMiddleware` (FastAPI BaseHTTPMiddleware) intercepte chaque requête. Pour les `GET /articles/*` uniquement :
1. Extrait l'`email` du JWT (Authorization Bearer) ou `ip:{X-Forwarded-For}` si anonyme.
2. Incrémente `api_stats/{YYYY-MM-DD}.{identifier}` en background via `asyncio.create_task` (fire-and-forget).
3. Erreurs réseau silencieusement ignorées (les stats ne doivent jamais faire échouer une requête).

**Règles métier**
- Granularité journalière (clé = `date.today().isoformat()`).
- Pas d'incrément natif Firestore en Python SDK → read + write (acceptable pour stats approximatives, race conditions possibles).
- Anonyme = pas de JWT ou JWT invalide → fallback sur IP via header `X-Forwarded-For` (Cloud Run le set automatiquement).

**Critères d'acceptation**
1. Chaque `GET /articles/` réussi incrémente `api_stats/{today}.{email or ip:X}`.
2. Les autres routes (admin, sources, users) ne sont pas trackées.
3. Une erreur du middleware ne fait pas échouer la requête originale.
4. Les requêtes simultanées du même user peuvent perdre quelques incréments (race condition acceptée).

---

### US-STA-002 — Afficher le nombre d'utilisateurs enregistrés

**En tant qu'** admin,
**je veux** voir combien d'utilisateurs distincts se sont déjà connectés,
**afin de** suivre la croissance.

**Description fonctionnelle**
`GET /admin/stats` (require_admin) renvoie `users_count = len(list(db.collection("users").stream()))`.

**Critères d'acceptation**
1. `/admin/stats` affiche un compteur "X utilisateurs enregistrés".
2. La valeur reflète exactement le nombre de documents dans `users`.

**Limites**
- Coûteux pour 10k+ users (charge tous les docs). Optimisation possible : `query.count().get()`.

---

### US-STA-003 — Afficher les appels API agrégés (today / 7j / 30j)

**En tant qu'** admin,
**je veux** voir le top des utilisateurs par volume d'appels sur 1 jour, 7 jours, 30 jours,
**afin de** identifier les power users ou détecter des comportements anormaux.

**Description fonctionnelle**
Le backend agrège les 30 derniers documents `api_stats/{date}` et calcule pour chaque identifier : `today` (J), `last_7` (J-6 à J), `last_30` (J-29 à J). Trié par `last_30` décroissant.

**Règles métier**
- Si un identifier disparaît (user supprimé), il reste dans les stats jusqu'à expiration des docs `api_stats`.
- Pas de TTL automatique sur les docs `api_stats` (croissance illimitée).

**Critères d'acceptation**
1. La page affiche un tableau : `identifier | today | last_7 | last_30`.
2. Tri par `last_30` desc.
3. Le `today` est ≤ `last_7` ≤ `last_30`.
4. Un identifier sans activité aujourd'hui mais actif hier apparaît avec `today=0`.

**Cas limites**
- 30 jours sans collecte → tableau vide.
- IPs derrière un même réseau corporate → toutes agrégées sous la même IP.

---

### US-STA-004 — Afficher les stats d'usage par utilisateur

**En tant qu'** admin,
**je veux** voir pour chaque utilisateur le nombre d'articles favoris, reading list, lus, supprimés,
**afin de** comprendre quelles fonctionnalités sont utilisées.

**Description fonctionnelle**
Le backend lit `user_preferences` et calcule pour chaque doc : `{email, favorites: N, reading_list: N, read_articles: N, dismissed: N}`. Trié par `favorites` desc.

**Critères d'acceptation**
1. Le tableau affiche : `email | favoris | reading list | lus | supprimés`.
2. Tri par favoris desc.
3. Inclut tous les users qui ont au moins une préférence.

**Cas limites**
- User connecté mais sans préférence → pas dans la liste.
- 1000+ users → charge full de `user_preferences` (coûteux).

---

### US-STA-005 — Accès admin uniquement

**En tant que** système,
**je veux** que `/admin/stats` soit inaccessible aux non-admins,
**afin de** protéger des données potentiellement sensibles (emails, IPs, comportements).

**Critères d'acceptation**
1. Sans JWT → 401.
2. JWT `role: reader` → 403.
3. JWT `role: admin` → 200 + JSON complet.
4. Le frontend redirige vers `/` si role != admin.

---

## Dépendances

- Backend : middleware `StatsMiddleware`, route `GET /admin/stats`.
- Firestore collections : `api_stats`, `users`, `user_preferences`.
- Frontend : page `/admin/stats`.

## Contraintes

- **Performance** : la page recharge tous les documents — devient lente à grande échelle. Optimisations possibles : cache TTL, aggregations Firestore.
- **Vie privée** : afficher des emails en clair dans une UI admin est OK pour un admin du même org. Si exposé externalement, anonymiser.
- **Coût Firestore** : 30 reads/jour pour `api_stats` + N reads pour `user_preferences`. Croît avec le nombre d'users.
