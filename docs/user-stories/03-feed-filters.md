# Feed des articles — Filtres et recherche

## Contexte fonctionnel

Le feed propose plusieurs filtres pour réduire la liste affichée : catégories (mono), sources (multi-exclusion), favoris/reading list/lus (toggles), recherche par mots-clés. Tous les filtres opèrent **côté frontend** sur les articles déjà chargés ; la pagination auto-fetche des pages supplémentaires si nécessaire pour atteindre X articles post-filtres.

## Objectif

- Permettre à l'utilisateur de réduire la quantité d'information selon ses centres d'intérêt.
- Combiner librement plusieurs filtres (AND logique).
- Garder l'expérience prévisible (cf. US pagination : toujours X articles post-filtres).

## User Stories

### US-FLT-001 — Filtrer par catégorie

**En tant que** lecteur,
**je veux** filtrer le feed par catégorie (IA, DevOps, Cloud, Sécurité, Dev, IT, Autre),
**afin de** ne voir que les articles d'un domaine qui m'intéresse à un instant T.

**Description fonctionnelle**
Composant `RadioFilter` affichant les 7 catégories avec un compteur pour chacune (nombre d'articles correspondants dans le set chargé). Sélection unique. Option "Toutes" pour désactiver. Le choix est persisté dans `localStorage` (`feed-selected-category`).

**Règles métier**
- Liste canonique : `["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"]` (définie en doublon dans 3 fichiers — cf. CLAUDE.md).
- Tout article dont la catégorie n'est pas dans la liste est forcé sur "Autre" (validation Pydantic `Article.normalize_category`).
- Les labels affichés varient selon la langue active (`categoryLabel(cat, lang)`).
- Le compteur affiché par catégorie est calculé **sur les articles déjà chargés**, pas sur la base totale.

**Critères d'acceptation**
1. Le sélecteur "Catégories" affiche les 7 valeurs + "Toutes".
2. Sélectionner "Sécurité" filtre instantanément la liste à la catégorie correspondante.
3. Le compteur de chaque catégorie reflète les articles chargés à l'instant T.
4. Le choix persiste après un rechargement de page.
5. Sélectionner "Toutes" affiche tous les articles à nouveau.

**Cas limites**
- Catégorie "Sécurité" très peu peuplée → auto-fetch des pages suivantes jusqu'à X (cf. US-FEED-002).

---

### US-FLT-002 — Exclure des sources

**En tant que** lecteur,
**je veux** masquer une ou plusieurs sources spécifiques,
**afin de** ne pas voir des articles d'une newsletter ou d'un site qui ne m'intéresse pas.

**Description fonctionnelle**
Composant `DropdownFilter` listant toutes les sources distinctes des articles chargés, avec compteur. L'utilisateur **décoche** (multi-sélection) les sources à exclure. Persisté dans `localStorage` (`feed-excluded-sources`) **et** dans `user_settings.excluded_sources` côté backend.

**Règles métier**
- Filtre multi-exclusion (toutes les sources sont visibles par défaut).
- Une source décochée masque tous ses articles, immédiatement.
- La synchronisation backend permet de retrouver ses choix sur un autre appareil.

**Critères d'acceptation**
1. Toutes les sources distinctes des articles chargés apparaissent dans le dropdown.
2. Décocher "TLDR AI" masque immédiatement ses articles du feed.
3. Le filtre persiste après reconnexion sur un autre appareil (sync backend).
4. Le compteur en haut du feed reflète la liste post-filtre.
5. Décocher toutes les sources affiche un message "Aucun article — ajuste les filtres".

---

### US-FLT-003 — Afficher uniquement favoris / reading list

**En tant que** lecteur,
**je veux** activer un mode "afficher uniquement mes favoris" ou "afficher uniquement ma liste de lecture",
**afin de** retrouver rapidement les articles que j'ai mis de côté.

**Description fonctionnelle**
Deux boutons toggles dans la barre de filtres (⭐ et 👓). Quand actifs, seuls les articles dans `favorites` ou `readingList` (respectivement) sont affichés. Combinables avec les autres filtres (catégorie, sources, recherche).

**Règles métier**
- Toggles indépendants (les deux peuvent être actifs simultanément → intersection : articles **à la fois** favoris ET dans la reading list).
- Si le mode est actif et qu'aucun article ne match : afficher "Aucun article…".

**Critères d'acceptation**
1. Cliquer sur ⭐ active visuellement le bouton (couleur d'accent).
2. La liste se réduit aux favoris instantanément.
3. Cliquer à nouveau désactive le filtre.
4. Le filtre s'applique en plus des autres filtres actifs (AND).
5. Si on dé-favorise un article en mode favori actif, l'article disparaît immédiatement de la liste.

---

### US-FLT-004 — Masquer les articles déjà lus

**En tant que** lecteur,
**je veux** masquer les articles que j'ai déjà marqués comme lus,
**afin de** me concentrer sur les nouveautés non encore consultées.

**Description fonctionnelle**
Toggle "✓" dans la barre de filtres. Quand actif, tout article dont l'`id` est dans `readArticles` est masqué. Persisté dans `user_settings.hide_read` côté backend.

**Règles métier**
- Le statut "lu" est porté par `user_preferences.read_articles[]` côté backend.
- L'utilisateur peut marquer un article lu via la card (swipe gauche→droite) ou via le menu (`✓`).
- "Marquer comme lu" rend l'article visuellement atténué (`opacity: 0.45`) avant de le masquer si le filtre est actif.

**Critères d'acceptation**
1. Le toggle "✓" est visible et changeable d'état.
2. Quand actif, les articles lus sont absents du feed.
3. Marquer un article comme lu en mode "✓ actif" → l'article disparaît immédiatement.
4. Désactiver le toggle → tous les articles (y compris lus) réapparaissent.
5. Le réglage est persisté entre sessions.

---

### US-FLT-005 — Rechercher par mots-clés

**En tant que** lecteur,
**je veux** taper un ou plusieurs mots-clés pour ne voir que les articles correspondants,
**afin de** retrouver un sujet précis.

**Description fonctionnelle**
Icône loupe ouvre une `SearchBar` qui propose des suggestions contextuelles (basées sur `keywords_fr` ou `keywords_en` des articles déjà chargés selon la langue active). L'utilisateur peut **ajouter plusieurs termes** ; le filtre est cumulatif (AND : un article doit matcher tous les termes).

**Règles métier**
- Le matching est `keyword.toLowerCase().includes(term.toLowerCase())` sur les keywords de l'article (donc partial match).
- Les suggestions se réduisent au fur et à mesure que des termes sont ajoutés.
- La langue active détermine quel champ keywords est utilisé (`keywords_fr` ou `keywords_en`).

**Critères d'acceptation**
1. La loupe ouvre/ferme la barre de recherche.
2. La barre propose des suggestions tirées des articles affichés.
3. Ajouter "Kubernetes" filtre la liste aux articles dont les keywords contiennent ce terme.
4. Ajouter un second terme ("Sécurité") réduit encore (intersection).
5. Fermer la barre vide tous les termes.

**Cas limites**
- L'utilisateur tape un terme qui n'existe nulle part → liste vide → auto-fetch pour vérifier les pages suivantes → au pire, message "Pas plus de résultats…".
- Termes avec espaces ou caractères spéciaux → matching tel quel, peut produire 0 résultat.

---

## Dépendances

- `usePreferences` (favorites, readingList, readArticles, dismissedSet).
- `useSettings` (excluded_sources, hide_read, default_lang).
- Pagination auto-fetch (US-FEED-002) pour atteindre X articles post-filtres.

## Contraintes

- **Métier** : tous les filtres opèrent côté frontend sur le set chargé. Cela suppose que le backend renvoie suffisamment d'articles pour matcher.
- **Performance** : si un filtre rare nécessite > 10 pages auto-chargées, on s'arrête avec un message explicite.
- **Futur** : on pourrait pousser `category` et `source_id` côté backend (API supporte déjà) pour réduire les fetchs et le payload. Non fait aujourd'hui.
