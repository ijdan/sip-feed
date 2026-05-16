# Préférences utilisateur — Thème, langue, mise en page, pagination

## Contexte fonctionnel

La page `/settings` permet à chaque utilisateur authentifié de configurer ses préférences d'affichage. Les valeurs sont persistées à deux niveaux : `localStorage` (rapidité) et `user_settings/{email}` dans Firestore (synchronisation entre appareils). Le hook `useSettings` orchestre la lecture/écriture des deux niveaux.

## Objectif

- Donner un contrôle fin sur la mise en page sans toucher au code.
- Synchroniser les préférences entre appareils du même utilisateur.
- Précharger les préférences locales pour l'affichage instantané, puis synchroniser avec le backend.

## User Stories

### US-SET-001 — Choisir le thème clair / sombre

**En tant que** lecteur,
**je veux** basculer entre thème clair et sombre,
**afin de** réduire la fatigue oculaire selon mon environnement (jour/nuit).

**Description fonctionnelle**
Toggle `☀️ Clair | 🌙 Sombre` dans la section "Affichage" de `/settings`. Le thème actif applique une classe `dark` sur `<html>` qui déclenche les variables CSS sombres (Tailwind dark mode).

**Règles métier**
- Le thème est appliqué immédiatement (`applyToDOM`) sans refresh.
- Persisté dans `localStorage.theme` et `user_settings.theme`.

**Critères d'acceptation**
1. Sur `/settings`, le toggle thème affiche l'état actuel mis en évidence.
2. Cliquer "Sombre" applique le mode sombre à toute l'application immédiatement.
3. Au refresh, le thème reste le dernier choisi (localStorage).
4. À la connexion sur un autre appareil, le thème est restauré depuis le backend.

---

### US-SET-002 — Choisir la langue par défaut

**En tant que** lecteur,
**je veux** définir ma langue par défaut (FR/EN),
**afin de** ne pas avoir à basculer manuellement à chaque ouverture du feed.

**Description fonctionnelle**
Toggle `FR | EN` dans `/settings`. Cette valeur est utilisée au chargement initial du feed pour définir l'état `lang`. Le toggle dans le feed reste indépendant (changement temporaire pour la session).

**Règles métier**
- Persisté dans `localStorage.settings-default-lang` et `user_settings.default_lang`.
- Affecte seulement le **mount initial** du feed (le toggle FR/EN dans le feed reste actif après).

**Critères d'acceptation**
1. Le toggle est visible et changeable dans `/settings`.
2. Recharger `/` après changement → la langue par défaut est appliquée.
3. Sur un autre appareil, la langue est synchronisée.

---

### US-SET-003 — Masquer les articles lus par défaut

**En tant que** lecteur,
**je veux** activer "Masquer les articles lus" par défaut,
**afin de** voir uniquement les nouveautés à chaque ouverture, sans toggle manuel.

**Description fonctionnelle**
Switch dans `/settings`. Si actif, le feed démarre avec le filtre "✓" activé.

**Critères d'acceptation**
1. Le switch est visible.
2. Activer → recharger `/` → filtre "✓" déjà activé visuellement.
3. Désactiver → comportement par défaut (tous les articles visibles).

---

### US-SET-004 — Choisir le nombre de colonnes du feed

**En tant que** lecteur sur grand écran,
**je veux** afficher 1, 2 ou 3 colonnes dans le feed,
**afin de** maximiser la densité d'information.

**Description fonctionnelle**
Toggle `▬ ⊟ ⊞` dans `/settings` (et aussi accessible dans le feed lui-même). Persisté dans `localStorage.feed-columns` et `user_settings.columns`.

**Critères d'acceptation**
1. Le choix est immédiatement effectif sur le feed.
2. Persisté entre sessions et entre appareils.
3. La vue corbeille respecte aussi ce réglage (cohérence visuelle).

---

### US-SET-005 — Choisir la taille de police

**En tant que** lecteur,
**je veux** ajuster la taille de police globale (Petite / Moyenne / Grande),
**afin de** adapter à mon confort de lecture (vue, distance écran).

**Description fonctionnelle**
Toggle `A | A | A` (de taille croissante) dans `/settings`. Application via classe `font-size-{sm|md|lg}` sur `<html>`.

**Critères d'acceptation**
1. Les 3 options sont visibles avec un aperçu de taille réelle (le bouton "A" est rendu en `[12, 15, 19]px`).
2. Le choix est immédiatement appliqué à toute l'app.
3. Persisté localStorage + backend.

---

### US-SET-006 — Choisir le nombre d'articles par page

**En tant que** lecteur,
**je veux** définir combien d'articles s'affichent à chaque "page" (10/20/50/100),
**afin de** adapter la pagination à ma vitesse de lecture.

**Description fonctionnelle**
Toggle `10 | 20 | 50 | 100` dans `/settings`. Affecte la valeur X de la pagination (cf. US-FEED-002). Changer X provoque un reset complet de la pagination (`clicks=1`, `setSize(1)`).

**Règles métier**
- Le cap public du backend est 100 (`page_size` ≤ 100 sur `/articles/`).
- Le défaut est 20.

**Critères d'acceptation**
1. Les 4 options sont visibles.
2. Sélectionner 50 → le feed reload avec 50 articles à la première vue.
3. Persisté.
4. Cohérence : le compteur "X affichés sur Y" reflète le nouveau X.

---

### US-SET-007 — Catégories affichées par défaut

**En tant que** lecteur,
**je veux** décocher certaines catégories pour les masquer par défaut,
**afin de** ne jamais voir certaines thématiques (ex. Crypto) sans avoir à filtrer manuellement.

**Description fonctionnelle**
Liste de checkboxes dans `/settings`, une par catégorie canonique. Décocher → ajout à `excluded_categories[]` côté backend.

**Critères d'acceptation**
1. Toutes les catégories canoniques sont listées, cochées par défaut.
2. Décocher "Crypto" → ses articles sont masqués par défaut sur le feed.
3. Persisté.
4. Modifier ne casse pas la pagination en cours (le filtre s'applique au prochain mount).

**Note** : actuellement non utilisé visiblement dans le feed (à vérifier dans le code). Si le filtre frontend n'utilise pas `excluded_categories`, c'est une dette à corriger.

---

### US-SET-008 — Sources affichées par défaut

**En tant que** lecteur,
**je veux** décocher certaines sources pour les masquer par défaut,
**afin de** éviter les sources qui ne m'intéressent pas (ex. une newsletter trop bruyante).

**Description fonctionnelle**
Identique à US-SET-007 mais pour les sources (liste dynamique récupérée des articles existants). Persisté dans `excluded_sources[]`.

**Critères d'acceptation**
1. La liste affiche toutes les sources distinctes connues à l'instant T.
2. Décocher une source la masque au prochain mount du feed.
3. Synchronisé avec le filtre "Sources" du feed.

---

## Dépendances

- Backend : `GET/PUT /users/me/settings` (modèle `UserSettings`).
- `useSettings` hook : orchestre localStorage + backend.
- `applyToDOM` : applique theme + font_size dans le DOM.

## Contraintes

- **Technique** : le localStorage est utilisé pour la rapidité au mount ; le backend est synchronisé en arrière-plan. Si le backend renvoie une autre valeur après le mount, l'UI re-render avec la valeur backend (peut produire un flicker visuel).
- **UX** : "Sauvegardé ✓" s'affiche brièvement après chaque modification pour rassurer.
- **Sécurité** : `excluded_categories`/`excluded_sources` sont des préférences UI, jamais utilisées comme contrôle d'accès. L'utilisateur peut toujours lire tous les articles publics via l'API si déterminé.
