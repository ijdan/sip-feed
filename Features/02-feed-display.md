# Feed des articles — Affichage, pagination, bilingue

## Contexte fonctionnel

Le feed (`/`) est la page d'accueil de Sip-feed. Il liste les articles tech collectés par le collector, triés par date de publication décroissante. L'affichage supporte 1, 2 ou 3 colonnes, langue FR ou EN, et une **pagination "Afficher plus"** qui garantit toujours X articles post-filtres (X étant `articles_per_page` dans les préférences user).

## Objectif

- Donner accès rapidement à une vue lisible des derniers articles.
- Adapter la mise en page à la préférence de chaque utilisateur (colonnes, langue).
- Permettre la consultation au-delà des X premiers articles via "Afficher plus".

## User Stories

### US-FEED-001 — Affichage du feed à l'ouverture

**En tant que** lecteur (authentifié ou non),
**je veux** voir les X articles les plus récents en ouvrant la page d'accueil,
**afin de** consulter rapidement l'actualité tech sans configuration préalable.

**Description fonctionnelle**
À l'ouverture de `/`, le frontend déclenche `useSWRInfinite` avec la première page (`?page=1&page_size=X`) où X = `settings.articles_per_page` (défaut 20). Les articles sont triés par `published_at` décroissant côté backend. Chaque article est rendu en `NewsCard` (titre, description courte, source, catégorie, date, bouton "Lire l'article").

**Règles métier**
- Les articles sont publics (pas besoin d'être authentifié pour les lire).
- L'ordre est strictement chronologique (champ `published_at`).
- Le payload renvoie aussi le total (`total`) pour permettre le calcul du "reste à charger".

**Critères d'acceptation**
1. La page se charge en moins de 2 secondes sur connexion standard.
2. Le compteur en haut affiche `N affichés sur Total` (ex. "20 affichés sur 180").
3. Les articles sont visibles dans une grille respectant le paramètre `columns` (1/2/3).
4. La date est formatée selon la langue (`formatDate(article.published_at, lang)`).
5. Si la base est vide, un message "Aucun article — ajuste les filtres ou réaffiche des sources" est affiché.

**Cas limites / erreurs**
- Backend indisponible → SWR affiche "Chargement…" indéfiniment ; améliorer avec un message d'erreur explicite (TODO).
- Article sans `title_fr`/`title_en` → fallback sur `title` (compat). Idem pour `short_description` / `long_description`.

---

### US-FEED-002 — Pagination "Afficher plus" avec X×Y articles

**En tant que** lecteur,
**je veux** voir exactement X articles post-filtres et X de plus à chaque clic sur "Afficher plus",
**afin de** garder une expérience prévisible quels que soient mes filtres actifs.

**Description fonctionnelle**
Le composant gère un compteur `clicks` (Y, défaut 1). La cible visible est `pageSize × clicks`. Si après filtrage côté frontend on a moins que la cible, un auto-fetch déclenche `setSize(size + 1)` pour charger la page backend suivante. Borne : max 10 pages auto-chargées pour éviter le scan complet sur un filtre rare.

**Règles métier**
- À chaque clic "Afficher plus" : `clicks++`.
- Quand un filtre change : `clicks` revient à 1 (la US AC1 demande Y=1 sur changement de filtre).
- Quand `articles_per_page` change dans les préférences : reset complet (`clicks=1`, `size=1`).
- Dismissed (corbeille) n'est PAS considéré comme un changement de filtre (action item-level).
- Le bouton "Afficher plus" disparaît si toute la base post-filtre est affichée.

**Critères d'acceptation**
1. Avec X=20, aucun filtre, et 100 articles en base : 20 articles s'affichent à l'ouverture, le bouton "Afficher plus" est visible.
2. Un clic sur "Afficher plus" affiche 40 articles, un second 60, etc.
3. Avec un filtre catégorie "Sécurité" qui ne match que 2 articles parmi les 20 premiers : le système auto-charge des pages suivantes jusqu'à atteindre 20 (ou épuiser le backend, max 10 pages).
4. Changer le filtre catégorie réinitialise immédiatement à X articles.
5. Si après 10 pages auto-chargées, on n'a toujours pas atteint X articles : afficher "Pas plus de résultats correspondant à tes critères dans les pages parcourues".

**Cas limites / erreurs**
- Filtre extrêmement restrictif (search avec mot-clé inexistant) : 10 pages parcourues, 0 résultat → message dédié, pas de bouton "Afficher plus".
- L'utilisateur clique sur "Afficher plus" pendant un auto-fetch en cours : le bouton est masqué pendant `loadingMore`, l'indicateur "Chargement…" est affiché.

**Given / When / Then**
```gherkin
Given X = 20, 0 filtre, 50 articles en base
When j'ouvre /
Then je vois 20 articles
When je clique 1 fois sur "Afficher plus"
Then je vois 40 articles et le bouton est toujours là (50 - 40 = 10 restants)
When je clique 1 fois de plus
Then je vois 50 articles et le bouton disparaît
```

---

### US-FEED-003 — Basculer entre français et anglais

**En tant que** lecteur,
**je veux** basculer l'affichage des articles entre français et anglais d'un clic,
**afin de** lire le contenu dans ma langue préférée du moment.

**Description fonctionnelle**
Un toggle `FR | EN` est présent en haut du feed. Il modifie `lang` (état local, non persisté pour cette session). Tous les champs bilingues (`title_fr`/`title_en`, `short_description_fr`/`short_description_en`, etc.) sont affichés selon `lang`. La langue par défaut au mount est `settings.default_lang` (configurable dans `/settings`).

**Règles métier**
- Tous les articles enrichis par Gemini ont une version FR et EN simultanées.
- Pour un article non-enrichi (fallback save_raw), `title_fr == title_en == title` (raw).
- La langue affecte aussi le rendu des dates (`formatDate`) et le label des catégories.

**Critères d'acceptation**
1. Le toggle est visible en haut du feed, à côté du sélecteur de colonnes.
2. Cliquer FR → tous les titres, descriptions, dates passent en français immédiatement (sans refetch).
3. Cliquer EN → idem en anglais.
4. La langue active est mise en évidence visuellement (fond foncé, contraste).
5. Au rechargement de la page, la langue revient à `settings.default_lang`.

---

### US-FEED-004 — Mise en page en colonnes (1/2/3)

**En tant que** lecteur sur grand écran,
**je veux** afficher les articles sur plusieurs colonnes,
**afin de** maximiser la densité d'information sans scroll excessif.

**Description fonctionnelle**
Toggle `▬ ⊟ ⊞` représentant 1, 2, 3 colonnes. La valeur est persistée dans `localStorage` (`feed-columns`) **et** dans `user_settings.columns` côté backend. La grille CSS utilise `grid-cols-1` / `grid-cols-1 sm:grid-cols-2` / `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3` (Tailwind responsive).

**Règles métier**
- Sur mobile (`< sm`), toujours 1 colonne, quel que soit le réglage (responsive automatique).
- Sur tablette (`sm` à `lg`), max 2 colonnes.
- Sur desktop (`>= lg`), 1/2/3 selon le choix.

**Critères d'acceptation**
1. Le toggle est immédiatement effectif (pas de refresh).
2. Le choix est persisté entre les sessions.
3. Sur un écran < 640px, l'affichage est forcé à 1 colonne quoi qu'il arrive.
4. La vue corbeille respecte aussi ce réglage (cohérence).
5. Le `gap` entre cards est constant (`gap-4`).

---

## Dépendances

- Backend : `GET /articles/?page={n}&page_size={X}` (cap public à 100).
- Frontend : `useSWRInfinite` (lib swr), `usePreferences`, `useSettings`.
- Articles enrichis par le collector (US-COL-* dans 12-collector-pipeline.md).

## Contraintes

- **Technique** : `page_size` capé à 100 côté API pour limiter le coût Firestore et le payload.
- **Performance** : la pagination par `offset` côté Firestore devient coûteuse au-delà de plusieurs centaines de pages. À refactorer en cursor pagination si volume > 10k articles.
- **UX** : le bouton "Afficher plus" disparaît dès qu'il n'y a plus rien, pour ne pas leurrer.
