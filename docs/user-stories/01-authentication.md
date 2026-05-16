# Authentification — Connexion OAuth & JWT applicatif

## Contexte fonctionnel

Sip-feed n'a pas de gestion de mots de passe propre : l'authentification repose sur OAuth Google et GitHub via NextAuth côté frontend. Le backend FastAPI vérifie ensuite le token du provider (id_token Google ou access_token GitHub) et émet **son propre JWT applicatif** (HS256, durée 1440 minutes = 24h). Ce JWT est utilisé pour toutes les requêtes API ultérieures. Les utilisateurs sont **clés par email** dans Firestore et reçoivent un rôle `reader` à la création, modifiable manuellement en `admin`.

## Objectif

- Permettre à un lecteur de se connecter sans créer de mot de passe.
- Permettre à un administrateur d'accéder aux fonctionnalités sensibles uniquement après vérification d'identité.
- Garantir qu'un faux token provider ne donne aucun accès (vérification systématique côté backend).

## User Stories

### US-AUTH-001 — Connexion via Google

**En tant que** lecteur,
**je veux** me connecter avec mon compte Google,
**afin de** accéder à mes préférences personnelles synchronisées entre mes appareils.

**Description fonctionnelle**
Le bouton "Se connecter avec Google" sur `/login` déclenche le flow OAuth Google via NextAuth. NextAuth récupère un `id_token`, l'envoie au backend (`POST /auth/google`), qui le vérifie via `google.oauth2.id_token.verify_oauth2_token` avec le `GOOGLE_CLIENT_ID`. Si OK, l'utilisateur est upserté dans Firestore (`users/{email}`) et un JWT applicatif est renvoyé.

**Règles métier**
- L'identifiant unique d'un user est son **email vérifié par Google** (clé du document Firestore).
- Tout nouveau user reçoit `role: "reader"` à la création.
- Le `name` et `avatar` sont mis à jour à chaque login s'ils ont changé.
- Le JWT applicatif a une durée de vie de 24h (configurable via `JWT_EXPIRE_MINUTES`).

**Critères d'acceptation**
1. Sur `/login`, le bouton "Se connecter avec Google" est visible et fonctionnel.
2. Après le flow OAuth, l'utilisateur est redirigé vers `/` et voit le feed avec son menu utilisateur (nom, avatar).
3. Le JWT applicatif est stocké dans la session NextAuth et envoyé en `Authorization: Bearer ...` pour tous les appels API protégés.
4. Si Google rejette le token (révoqué, signature invalide), le backend renvoie `401 Token Google invalide` et l'utilisateur reste sur `/login`.
5. À la **deuxième connexion**, l'utilisateur retrouve ses préférences (favoris, reading list, etc.) intactes.

**Cas limites / erreurs**
- Backend indisponible pendant le login → NextAuth marque `authError: backend_unreachable` ; l'UI doit afficher un message clair.
- Email Google non vérifié → cas non géré explicitement aujourd'hui (Google ne renvoie pas ce token normalement).
- Concurrence : deux logins simultanés du même user → un seul `internal_id` est généré et conservé.

**Given / When / Then**
```gherkin
Given je suis un nouvel utilisateur sur /login
When je clique sur "Se connecter avec Google" et que j'accepte le consentement
Then un document users/{mon_email} est créé dans Firestore avec role="reader"
And je suis redirigé vers le feed avec une session active de 24h
```

---

### US-AUTH-002 — Connexion via GitHub

**En tant que** lecteur,
**je veux** me connecter avec mon compte GitHub,
**afin de** avoir une alternative à Google si je préfère.

**Description fonctionnelle**
Bouton "Se connecter avec GitHub" sur `/login`. NextAuth récupère un `access_token` GitHub opaque, l'envoie au backend (`POST /auth/github`). Le backend interroge `api.github.com/user` et `api.github.com/user/emails` pour récupérer le profil et l'email primaire **vérifié**, puis émet le JWT applicatif.

**Règles métier**
- L'email **doit être vérifié et primary** sur GitHub. Si aucun email vérifié n'est trouvé, le backend renvoie `401 Email GitHub vérifié requis`.
- Si GitHub renvoie un nom (`profile.name`), il est utilisé. Sinon, le `login` GitHub fait office de nom.
- L'avatar est `profile.avatar_url`.
- L'utilisateur est mergé avec un éventuel compte Google existant **s'ils partagent le même email** (la clé Firestore reste l'email).

**Critères d'acceptation**
1. Le bouton "Se connecter avec GitHub" est présent sur `/login`.
2. Si GitHub API renvoie `200` pour `/user` et `/user/emails`, l'authentification réussit.
3. Si GitHub est indisponible (`httpx.RequestError`), le backend renvoie `502 GitHub indisponible`.
4. Si le token est invalide ou révoqué (`401` de GitHub), le backend renvoie `401 Token GitHub invalide`.
5. Un utilisateur qui se connecte d'abord avec Google puis avec GitHub (même email) garde ses préférences (pas de doublon).

**Cas limites / erreurs**
- Compte GitHub sans email primaire vérifié → 401, l'utilisateur doit aller vérifier son email sur GitHub.
- L'utilisateur révoque l'autorisation GitHub dans ses settings GitHub → le `access_token` devient invalide ; ses JWT applicatifs restent valides jusqu'à expiration.

---

### US-AUTH-003 — Vérification du JWT à chaque appel API protégé

**En tant que** système,
**je veux** vérifier le JWT applicatif à chaque appel d'une route protégée,
**afin de** garantir que seuls les utilisateurs authentifiés accèdent à leurs données.

**Description fonctionnelle**
La dépendance FastAPI `verify_jwt` décode le JWT (`jwt.decode` avec `JWT_SECRET` + algorithme HS256). Elle renvoie le payload (`sub`, `email`, `role`, `exp`). Une seconde dépendance `require_admin` vérifie en plus `role == "admin"` et renvoie `403` sinon.

**Règles métier**
- Toute route sous `/admin/*` requiert `require_admin`.
- Routes sous `/users/me/*`, `/sources/*` (sauf list public ?), `/articles/{id}` requièrent `verify_jwt`.
- `/articles/` (list public) et `/articles/stats` sont **publics** (pas de JWT requis).

**Critères d'acceptation**
1. Une requête sans header `Authorization` sur une route protégée renvoie `401 Not authenticated`.
2. Une requête avec un JWT expiré renvoie `401 Token expiré`.
3. Une requête avec un JWT malformé renvoie `401 Token invalide`.
4. Une requête avec un JWT `role: reader` sur une route admin renvoie `403 Accès admin requis`.
5. Une requête avec un JWT valide et le bon rôle accède à la ressource.

**Cas limites / erreurs**
- JWT signé avec un autre `JWT_SECRET` (rotation de clé) → 401, l'utilisateur doit se reconnecter.
- Token avec un email qui n'existe plus dans Firestore (compte supprimé) → l'appel API peut quand même réussir car la vérification se fait sur la signature du JWT, pas sur la DB. À surveiller comme défaut potentiel.

---

## Dépendances

- **Frontend** : `next-auth` (Google + GitHub providers).
- **Backend** : `google-auth`, `google-auth-oauthlib`, `httpx`, `PyJWT`.
- **Secrets** : `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `JWT_SECRET`, `NEXTAUTH_SECRET` (montés via Secret Manager en prod).

## Contraintes

- **Métier** : tout nouvel utilisateur est `reader`. La promotion en `admin` est manuelle (édition Firestore directe ou script).
- **Technique** : JWT HS256, secret partagé entre instances backend ; pas de RS256 envisagé pour l'instant. Pas de refresh token — l'utilisateur doit se reconnecter au bout de 24h.
- **Sécurité** : le backend ne fait jamais confiance aux fields envoyés par le frontend pour l'identité ; il revérifie systématiquement auprès du provider (Google ou GitHub).
