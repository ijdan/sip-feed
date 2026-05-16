# Console admin — Gestion des sources

## Contexte fonctionnel

Une **source** est un point de collecte du contenu : soit un site web scrapé (`type: "web"`, avec `url`), soit un expéditeur Gmail dont les newsletters sont parsées (`type: "gmail"`, avec `gmail_sender`). L'admin gère le CRUD complet et peut activer/désactiver une source ou déclencher une collecte ciblée.

## Objectif

- Permettre à l'admin d'ajouter, modifier, supprimer et activer/désactiver les sources de contenu.
- Tester une nouvelle source en déclenchant une collecte ponctuelle.
- Valider la qualité des URLs (anti-SSRF basique).

## User Stories

### US-SRC-001 — Lister les sources

**En tant qu'** admin (ou tout user authentifié),
**je veux** voir la liste de toutes les sources configurées,
**afin de** comprendre d'où vient le contenu du feed.

**Description fonctionnelle**
`GET /sources/` (require auth). Renvoie un tableau de `Source` avec `id`, `name`, `type`, `url`/`gmail_sender`, `active`, `created_by`, `created_at`. Visible dans `/admin` via le composant `SourceManager`.

**Règles métier**
- Tout utilisateur authentifié peut **lire** la liste (utile pour les filtres du feed).
- Seuls les admins peuvent créer/modifier/supprimer.

**Critères d'acceptation**
1. La liste affiche le nom, type (icône 🌐 web ou 📧 gmail), URL/sender, et un toggle actif.
2. Triée par ordre de création (ou alphabétique selon implémentation).
3. La requête réussit pour reader et admin (le contrôle d'accès est sur le write).

---

### US-SRC-002 — Créer une source web

**En tant qu'** admin,
**je veux** ajouter un nouveau site à scraper,
**afin d'** enrichir la diversité du contenu collecté.

**Description fonctionnelle**
Formulaire dans `SourceManager` : champs `name`, `type=web`, `url`. Submit → `POST /sources/` (require_admin). Le backend valide via Pydantic `SourceCreate` : `url` doit être en `http://` ou `https://` et avoir un hostname (validator anti-SSRF basique).

**Règles métier**
- `type=web` exige `url` non vide.
- `url` doit avoir un scheme `http`/`https` et un hostname. Sinon → 422.
- Au scraping, l'URL est re-validée côté collector (defense-in-depth).
- À la création, `active: true` par défaut.

**Critères d'acceptation**
1. Le formulaire est visible quand "Ajouter une source" est cliqué.
2. Renseigner name + URL valide + submit → 200 + nouvelle ligne dans la liste.
3. URL `file:///etc/passwd` → 422 "L'URL doit utiliser le scheme http ou https".
4. URL `not-a-url` → 422 "URL invalide : hostname manquant".
5. Sans le champ url → 400 "URL requise pour une source web".

**Cas limites**
- URL pointant vers `http://localhost` ou IP privée : actuellement **accepté** par le validator (juste scheme/hostname). La validation IP avancée est documentée comme limite à fixer (cf. audit sécu).

---

### US-SRC-003 — Créer une source Gmail

**En tant qu'** admin,
**je veux** ajouter un expéditeur Gmail à surveiller (ex. TLDR newsletter),
**afin de** récupérer les liens et descriptions de chaque newsletter.

**Description fonctionnelle**
Formulaire : `name`, `type=gmail`, `gmail_sender`. Submit → `POST /sources/`. Le `gmail_sender` est l'email de l'expéditeur (ex. `dan@tldrnewsletter.com`).

**Règles métier**
- `type=gmail` exige `gmail_sender` non vide.
- Le format de `gmail_sender` n'est pas validé strictement (peut contenir un nom + email).
- Au scraping, le collector utilise `from:{sender}` dans la query Gmail API.
- Aujourd'hui seuls les newsletters au **format TLDR** sont parsées (cf. 12-collector-pipeline.md).

**Critères d'acceptation**
1. Le formulaire affiche le champ `gmail_sender` quand type=gmail.
2. Sans `gmail_sender` → 400 "gmail_sender requis pour une source Gmail".
3. La source est créée et apparaît dans la liste.
4. Le format TLDR est détecté automatiquement au prochain run du collector.

**Cas limites**
- Newsletter non-TLDR : le collector loggue "format non reconnu, ignoré" mais ne crashe pas.

---

### US-SRC-004 — Modifier une source

**En tant qu'** admin,
**je veux** modifier le nom, l'URL ou le sender d'une source existante,
**afin de** corriger une faute de frappe ou suivre un changement de domaine.

**Description fonctionnelle**
`PUT /sources/{id}` (require_admin). Body : `SourceCreate` complet (name, type, url/gmail_sender, active). Validations identiques à la création.

**Critères d'acceptation**
1. Cliquer "Modifier" sur une source ouvre un formulaire pré-rempli.
2. Modifier puis sauvegarder → 200 + ligne mise à jour.
3. Source inexistante → 404.
4. Validation URL appliquée.
5. Le changement de type (web ↔ gmail) est possible mais nécessite de fournir le bon champ.

---

### US-SRC-005 — Activer / désactiver une source

**En tant qu'** admin,
**je veux** désactiver temporairement une source qui produit du contenu de mauvaise qualité,
**afin de** ne plus la voir dans les runs sans la supprimer définitivement.

**Description fonctionnelle**
Toggle switch sur chaque ligne. `PATCH /sources/{id}/toggle` inverse le booléen `active`.

**Règles métier**
- Le collector ne traite **que** les sources `active=True` (sauf si `COLLECTOR_SOURCE_ID` env override).
- Désactiver ne supprime pas les articles déjà collectés.

**Critères d'acceptation**
1. Le toggle est visible sur chaque ligne.
2. Cliquer désactive immédiatement (UI + backend).
3. Au prochain run, la source est ignorée.
4. Source inexistante → 404.

---

### US-SRC-006 — Supprimer une source

**En tant qu'** admin,
**je veux** supprimer définitivement une source,
**afin de** nettoyer la liste des sources obsolètes.

**Description fonctionnelle**
Bouton "Supprimer" avec confirmation. `DELETE /sources/{id}` (require_admin).

**Règles métier**
- La suppression de la source **ne supprime pas** les articles déjà collectés (orphans).
- Pas de suppression en cascade.

**Critères d'acceptation**
1. Le bouton demande confirmation (ex. modal "Êtes-vous sûr ?").
2. Confirmer → 204 + ligne disparait.
3. Source inexistante → 404.

**Cas limites**
- Source supprimée → articles existants restent avec `source_name` figé. Pas de mise à jour rétroactive.

---

### US-SRC-007 — Déclencher la collecte d'une seule source

**En tant qu'** admin,
**je veux** lancer un run du collector ciblé sur une source unique,
**afin de** tester rapidement une nouvelle source ou re-collecter après une erreur.

**Description fonctionnelle**
Bouton "▶" sur chaque ligne. `POST /admin/sources/{id}/collect` (require_admin) déclenche un run du Cloud Run Job avec `COLLECTOR_SOURCE_ID={id}` en env override. En local (APP_ENV=local), lance le collector en sous-processus.

**Règles métier**
- En local, l'émulateur Firestore doit être joignable (sinon 503).
- Le collector traite uniquement la source ciblée (ignore les autres).
- Le run est asynchrone : la réponse est 202 immédiatement.

**Critères d'acceptation**
1. Cliquer "▶" envoie `POST /admin/sources/{id}/collect`.
2. Réponse 202 avec `{"status": "triggered", "source_id": "..."}` ou `triggered_local`.
3. Source inexistante → 404.
4. Cloud Run Jobs API en erreur → 502.

---

## Dépendances

- Backend : `Source`, `SourceCreate` models, routes `/sources/*` et `/admin/sources/{id}/collect`.
- Collector : lit `sources` collection à chaque run.
- `SourceManager.tsx` component (frontend).

## Contraintes

- **Métier** : seuls les admins peuvent modifier les sources.
- **Technique** : validation URL minimale (scheme + hostname), ne protège pas contre SSRF avancé (IP privées, redirects). Cf. priorité 4 de l'audit sécu.
- **UX** : pas d'historique de modifications (pas de versioning).
