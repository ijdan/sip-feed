# Feed personnalisé — Préférences intégrées et authentification requise

## Contexte fonctionnel

Les fonctionnalités personnelles (favoris ⭐, liste de lecture 👓, articles lus ✓, corbeille 🗑️) sont aujourd'hui accessibles à tout utilisateur y compris anonyme, et les préférences sont maintenues dans un état local (`usePreferences`) synchronisé indépendamment du feed. Cette architecture crée deux sources de vérité : les articles chargés via `GET /articles/` (limités par `retention_days`) et les préférences chargées via `GET /users/me/preferences`. Conséquence : un article favori plus ancien que `retention_days` n'apparaît pas dans le filtre ⭐ car le backend l'a exclu du feed.

## Objectif

- Restreindre les fonctionnalités personnelles aux utilisateurs authentifiés (cohérent : les préférences n'ont de sens que persistées).
- Intégrer les préférences dans la réponse de `GET /articles/` pour éliminer la double source de vérité.
- Garantir que le filtre ⭐ retourne **tous** les favoris, sans restriction de rétention.

---

## User Stories

### US-PERS-001 — Restreindre les actions personnelles aux utilisateurs authentifiés

**En tant que** product owner,
**je veux** que favoris, liste de lecture, marquage lu et corbeille ne soient disponibles que pour les utilisateurs connectés,
**afin de** garantir la persistance et la cohérence des données personnelles.

**Description fonctionnelle**
Les boutons ⭐, 👓, ✓ et 🗑️ dans les `NewsCard` sont masqués (ou désactivés avec tooltip "Connectez-vous") si la session est absente. Le feed reste accessible en lecture anonyme. Les swipes tactiles déclenchant ces actions sont également désactivés pour les anonymes.

**Règles métier**
- Lecture anonyme : `GET /articles/` sans token → feed normal avec rétention, sans flags personnels.
- Écriture des préférences (`PUT /users/me/preferences`) requiert déjà un JWT — pas de changement backend sur ce point.
- Un utilisateur qui se déconnecte ne voit plus les boutons d'action mais continue à voir le feed.

**Critères d'acceptation**
1. En session anonyme, les boutons ⭐, 👓, ✓, 🗑️ sont absents des `NewsCard`.
2. Les swipes gauche/droite sur mobile ne déclenchent aucune action sans session.
3. En session authentifiée, le comportement existant est inchangé.
4. Aucune requête vers `/users/me/preferences` n'est émise sans token.

---

### US-PERS-002 — Enrichir `GET /articles/` avec les flags personnels quand authentifié

**En tant que** lecteur connecté,
**je veux** recevoir mes flags personnels (`is_favorite`, `is_in_reading_list`, `is_read`, `is_dismissed`) directement dans chaque article du feed,
**afin d'** éliminer l'appel séparé à `/users/me/preferences` et d'avoir une source de vérité unique.

**Description fonctionnelle**
Quand `GET /articles/` reçoit un JWT valide, le backend :
1. Lit `user_preferences/{email}` dans Firestore (une lecture par appel, avec mise en cache courte).
2. Ajoute à chaque `Article` les champs booléens : `is_favorite`, `is_in_reading_list`, `is_read`, `is_dismissed`.
3. Construit l'**union** : articles dans la fenêtre de rétention **OU** dans `favorites[]` ou `reading_list[]` de l'utilisateur — pour que les articles anciens favorisés restent visibles.

Sans JWT, les champs booléens sont absents (ou `false`) et la rétention seule s'applique.

**Règles métier**
- Les flags sont calculés côté backend à partir des listes Firestore — le frontend n'a plus besoin de maintenir ces sets localement pour l'affichage.
- L'union rétention ∪ favoris ∪ reading_list est calculée sur les IDs stockés dans `user_preferences`, **indépendamment de leur date**.
- Les articles hors-rétention et hors-préférences ne sont toujours pas renvoyés.
- Le tri reste `published_at` décroissant sur l'ensemble résultant.
- La mise en cache de `user_preferences` côté backend doit être courte (≤ 30 s) pour refléter les changements rapides (ajout/retrait favori).

**Critères d'acceptation**
1. Un article favori collecté il y a 90 jours (hors `retention_days=30`) apparaît dans le feed quand le filtre ⭐ est actif.
2. Chaque article de la réponse authentifiée contient `is_favorite: true/false`.
3. Le filtre ⭐ côté frontend utilise `is_favorite` du payload — plus de lookup dans un Set local.
4. En session anonyme, la réponse est identique à aujourd'hui (pas de régression).
5. La suppression d'un favori (`PUT /users/me/preferences`) suivie d'un refresh du feed retire l'article si celui-ci est hors-rétention.

---

### US-PERS-003 — Supprimer la double source de vérité dans le frontend

**En tant que** développeur,
**je veux** que `usePreferences` ne serve plus qu'aux **écritures** (toggle favori, etc.),
**afin de** supprimer la synchronisation parallèle et simplifier l'état du composant.

**Description fonctionnelle**
Le hook `usePreferences` conserve uniquement :
- Les fonctions de mutation : `toggleFavorite`, `toggleReadingList`, `toggleRead`, `dismiss`, `restoreArticle`.
- L'état local optimiste (mise à jour immédiate avant confirmation backend).

La lecture des listes (`favorites`, `readingList`, `readArticles`, `dismissedSet`) est abandonnée en faveur des flags portés par les articles (`is_favorite`, etc.) retournés par `GET /articles/`.

**Règles métier**
- Les mutations restent optimistes : l'UI reflète le changement immédiatement, le backend confirme en arrière-plan.
- En cas d'erreur backend sur une mutation, l'état optimiste est annulé (rollback).
- `usePreferences` ne déclenche plus `GET /users/me/preferences` au montage si l'utilisateur est authentifié (les données arrivent via le feed).

**Critères d'acceptation**
1. Cliquer ⭐ met à jour visuellement la card instantanément (optimiste).
2. Un refresh complet de la page montre l'état réel (persisté backend).
3. Aucun appel `GET /users/me/preferences` n'est émis au chargement de la page.
4. Le filtre ⭐ actif continue à fonctionner correctement après un toggle favori sans refresh.
5. La corbeille (vue 🗑️) affiche les articles `is_dismissed: true` du dernier feed chargé.

---

## Dépendances

- `backend/app/routers/articles.py` : ajout auth optionnelle + lecture `user_preferences` + calcul union + flags dans `Article`.
- `backend/app/models/article.py` : ajout champs optionnels `is_favorite`, `is_in_reading_list`, `is_read`, `is_dismissed`.
- `frontend/src/lib/usePreferences.ts` : refactoring pour ne garder que les mutations.
- `frontend/src/app/page.tsx` : utiliser les flags du payload au lieu des Sets locaux.
- `frontend/src/components/NewsCard.tsx` : masquer les boutons d'action si pas de session.

## Contraintes

- **Rétrocompatibilité** : les champs booléens étant optionnels dans le modèle `Article`, les clients sans token (ou anciens) ne cassent pas.
- **Performance** : la lecture `user_preferences` par requête `GET /articles/` ajoute une lecture Firestore supplémentaire pour les utilisateurs authentifiés. Un cache TTL 30 s côté backend est acceptable ; au-delà, envisager un cache Redis.
- **Cohérence** : après un `PUT /users/me/preferences`, le cache backend doit être invalidé ou expiré pour que le prochain `GET /articles/` reflète le changement.
- **Sécurité** : `is_dismissed` ne doit apparaître que dans la réponse de l'utilisateur propriétaire — jamais croiser les préférences entre utilisateurs.
