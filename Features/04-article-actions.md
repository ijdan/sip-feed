# Actions sur un article — Favoris, lecture, suppression

## Contexte fonctionnel

Chaque `NewsCard` propose plusieurs actions sur l'article : ouvrir l'URL externe, marquer comme favori (⭐), ajouter à la liste de lecture (👓), marquer comme lu (✓), dismisser (corbeille 🗑️). Ces actions sont **personnelles** : elles sont stockées par utilisateur dans `user_preferences/{email}` (Firestore) et synchronisées entre appareils. Sur mobile, certaines actions sont accessibles via des **swipes** (gauche→droite pour lu, droite→gauche pour suppression).

## Objectif

- Permettre à l'utilisateur de gérer sa lecture (mise de côté, marquage, suppression).
- Garantir la persistance et la synchronisation entre appareils.
- Offrir une expérience tactile fluide sur mobile (swipe).

## User Stories

### US-ACT-001 — Marquer un article comme favori

**En tant que** lecteur,
**je veux** marquer un article comme favori,
**afin de** le retrouver facilement plus tard via le filtre ⭐.

**Description fonctionnelle**
Bouton ⭐ dans le menu `•••` de la `NewsCard`. Toggle : un clic ajoute l'`id` de l'article à `favorites` (Set), un second le retire. La modification est immédiatement persistée via `PUT /users/me/preferences`.

**Règles métier**
- L'`id` de l'article est l'identifiant Firestore (UUID).
- `favorites` est un tableau côté Firestore, converti en Set côté frontend pour les lookups O(1).
- Aucune limite de nombre de favoris.
- Un article supprimé de la base (par retention ou purge) n'est PAS automatiquement retiré de la liste de favoris.

**Critères d'acceptation**
1. Le menu `•••` est visible au hover sur desktop, accessible au tap sur mobile.
2. Cliquer ⭐ change visuellement le bouton (opacity de 0.3 à 1).
3. La modification est persistée même après un refresh (sync backend).
4. Le filtre "afficher uniquement favoris" (US-FLT-003) retrouve les favoris marqués.
5. Le compteur de la corbeille n'est pas affecté.

---

### US-ACT-002 — Ajouter un article à la liste de lecture

**En tant que** lecteur,
**je veux** ajouter un article à ma "liste de lecture" pour le consulter plus tard,
**afin de** ne pas l'oublier sans pour autant l'archiver comme favori.

**Description fonctionnelle**
Bouton 👓 dans le menu `•••` de la `NewsCard`. Comportement identique à ⭐ mais dans `reading_list` (Set distinct).

**Règles métier**
- Indépendant de favoris : un article peut être à la fois favori ET dans la reading list.
- Pas de notion de "lu" liée : marquer comme lu ne retire pas de la reading list (à voir selon retour utilisateur).

**Critères d'acceptation**
1. Cliquer 👓 toggle l'état (visuel + backend).
2. Le filtre "👓" (US-FLT-003) affiche uniquement la reading list.
3. Persisté entre appareils.
4. Peut être combiné avec favori sans conflit.

---

### US-ACT-003 — Marquer comme lu / non lu (swipe ou clic)

**En tant que** lecteur,
**je veux** marquer un article comme lu après l'avoir consulté,
**afin de** le distinguer visuellement et le masquer si je le souhaite (filtre `✓`).

**Description fonctionnelle**
Deux moyens :
- **Swipe gauche→droite** sur la card (mobile/touch). Progression visuelle : fond vert (lu) ou gris (non-lu si déjà lu) en fonction de la distance.
- **Bouton invisible/programmable** dans le menu (`onMarkRead` est exposé).

Un article marqué lu voit son opacité tomber à 0.45.

**Règles métier**
- Re-swiper un article déjà lu le repasse en non-lu (toggle).
- L'`id` est ajouté/retiré de `read_articles[]` côté backend.

**Critères d'acceptation**
1. Sur mobile, swiper droit→gauche → fond rouge "Suppression ✕". Swiper gauche→droite → fond vert "✓ Lu".
2. Au lâcher (assez de progression), l'article est marqué lu/non lu en backend.
3. L'opacité passe à 0.45 sans masquer l'article (sauf si filtre "hide_read" actif).
4. Le swipe est désactivé pendant que l'article est en cours d'animation de suppression.
5. Une animation fluide (`transition: transform 0.25s ease`) ramène la card à sa position au lâcher.

**Cas limites**
- Swipe partiel (pas assez de distance) → l'animation ramène la card sans déclencher l'action.
- Multi-touch ou interruption → l'état est reset proprement.

---

### US-ACT-004 — Supprimer un article (corbeille)

**En tant que** lecteur,
**je veux** "supprimer" un article du feed (l'envoyer dans une corbeille personnelle),
**afin de** masquer un contenu sans intérêt sans toucher à la base.

**Description fonctionnelle**
Swipe droite→gauche sur la card (mobile) déclenche `onDismiss`. L'`id` de l'article est ajouté à `dismissed[]` côté backend. L'article disparaît du feed avec une animation (`translateX(-110%)`). Il reste consultable via la vue corbeille (icône 🗑️).

**Règles métier**
- La "suppression" est **personnelle** : elle ne touche pas la base d'articles, ni les autres utilisateurs.
- Un article dismissed reste dans le set `allItems` (chargé) mais est filtré côté frontend.

**Critères d'acceptation**
1. Swipe droite→gauche déclenche un fond rouge avec "Suppression ✕".
2. Au lâcher (progression suffisante), l'article disparaît du feed.
3. Le compteur de la corbeille (en haut du feed, icône 🗑️) s'incrémente.
4. L'article n'apparaît plus dans le feed même après refresh (persisté backend).
5. Si l'utilisateur a un autre appareil, la suppression y est aussi reflétée.

**Cas limites**
- Article supprimé puis filtre actif (catégorie, etc.) : l'article reste dismissed même si le filtre serait satisfait.

---

### US-ACT-005 — Restaurer un article depuis la corbeille

**En tant que** lecteur,
**je veux** restaurer un article que j'ai supprimé par erreur,
**afin de** le retrouver dans mon feed normal.

**Description fonctionnelle**
Clic sur l'icône 🗑️ → vue corbeille. Chaque `TrashCard` propose un swipe droite→gauche pour restaurer (ou un bouton "Restaurer"). L'`id` est retiré de `dismissed[]` côté backend.

**Règles métier**
- La corbeille respecte le réglage `columns` (cohérence visuelle avec le feed normal).
- La liste est triée par `published_at` décroissant.

**Critères d'acceptation**
1. L'icône 🗑️ affiche un compteur si la corbeille n'est pas vide.
2. Cliquer 🗑️ ouvre la vue corbeille avec un texte d'introduction.
3. La grille respecte le `columns` actuel.
4. Restaurer un article le fait disparaître de la corbeille et réapparaître dans le feed normal.
5. Si la corbeille est vide, un message "La corbeille est vide" s'affiche.

---

### US-ACT-006 — Ouvrir l'article source dans un nouvel onglet

**En tant que** lecteur,
**je veux** ouvrir l'URL originale de l'article dans un nouvel onglet,
**afin de** lire le contenu complet sur le site source sans quitter Sip-feed.

**Description fonctionnelle**
Bouton "Lire l'article →" en bas de chaque `NewsCard`, en couleur d'accent. Lien `<a target="_blank" rel="noopener noreferrer">` vers `article.article_url`.

**Règles métier**
- `target="_blank"` ouvre un nouvel onglet.
- `rel="noopener noreferrer"` (sécurité contre tabnabbing).

**Critères d'acceptation**
1. Le bouton "Lire l'article →" est visible en bas à droite de chaque card.
2. Cliquer dessus ouvre l'URL dans un nouvel onglet.
3. Le clic ne déclenche pas le toggle "expanded" de la card (`e.stopPropagation()`).
4. Sur mobile, le tap fonctionne identiquement.
5. La traduction du label respecte la langue (`Lire l'article →` / `Read article →`).

---

### US-ACT-007 — Étendre/réduire une card pour voir le long_description

**En tant que** lecteur,
**je veux** déplier une card pour voir la description longue (analyse 4-6 phrases),
**afin de** décider si l'article m'intéresse sans ouvrir l'URL source.

**Description fonctionnelle**
Cliquer sur le titre ou la short_description toggle l'état `expanded`. Quand `expanded`, le `long_description` (selon langue) est affiché sous un séparateur.

**Critères d'acceptation**
1. Le clic sur le titre ou la description courte étend la card.
2. Un second clic la réduit.
3. Si `long_description` est vide (article non enrichi), aucun contenu supplémentaire n'apparaît.
4. L'état `expanded` est local (non persisté).
5. Le menu `•••` reste accessible quel que soit l'état.

---

## Dépendances

- Backend : `GET/PUT /users/me/preferences` (modèle `UserPreferences`).
- `usePreferences` hook : centralise favoris, reading_list, read_articles, dismissed.
- `useDragSwipe` hook : gestion des gestes tactiles.

## Contraintes

- **Métier** : les listes peuvent grossir sans limite (pas de cap). Si un utilisateur a 10k favoris, le `Set` reste performant mais la sérialisation backend peut devenir lourde.
- **UX mobile** : les swipes doivent être suffisamment précis pour ne pas déclencher accidentellement une suppression. Tester sur petits écrans.
- **Cohérence** : un article supprimé par retention en backend reste dans les listes user — non nettoyé automatiquement (à surveiller comme dette technique).
