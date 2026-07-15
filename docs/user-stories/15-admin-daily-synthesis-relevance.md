# Console admin — Synthèse du jour : pertinence accrue (sources + thèmes + contenu intégral)

## Contexte fonctionnel

Aujourd'hui, la synthèse quotidienne (cf. `09-admin-synthesis.md`) est générée à partir des **résumés** (titres + descriptions longues FR) des 100 derniers articles, toutes sources et catégories confondues. La pertinence est limitée : le LLM ne voit qu'un condensé, et le corpus n'est pas filtrable.

Cette évolution rend la synthèse plus pertinente sur trois axes :

1. **Configuration dédiée dans l'IHM admin** : une nouvelle section « Synthèse du jour » regroupe le choix des **sources** à considérer (choix multiple, ex. TLDR), le choix des **thèmes** / catégories (choix multiple, ex. IA, Dev), et la zone de saisie **« Centre d'intérêt »** (déplacée depuis la page `/admin/synthesis`).
2. **Corpus enrichi** : le traitement de synthèse récupère le **contenu intégral** des articles correspondant aux sources et thèmes sélectionnés (téléchargement de chaque `article_url`), puis **nettoie** ce contenu (suppression du HTML, images, CSS, scripts) pour ne conserver que le texte utile et réduire la taille envoyée au LLM.
3. **Prompt** : le traitement envoie au LLM l'ensemble du texte nettoyé, accompagné du prompt de synthèse et du texte « centre d'intérêt ».

> ⚠️ Point d'architecture : les documents `articles` en Firestore ne stockent **pas** le contenu complet des pages (seulement les titres/descriptions produits à l'enrichissement). La récupération du contenu intégral se fait donc **au moment de la génération de la synthèse**, par re-téléchargement des URLs.

## Objectif

- Cibler la synthèse sur un sous-ensemble maîtrisé du flux (sources + thèmes choisis par l'admin).
- Donner au LLM la matière brute complète des articles (et non leurs résumés) pour une analyse plus fine.
- Centraliser toute la configuration de la synthèse dans une section unique de l'IHM admin.

## User Stories

### US-SYN-101 — Section « Synthèse du jour » dans l'IHM admin

**En tant qu'** admin,
**je veux** disposer d'une section « Synthèse du jour » regroupant sources, thèmes et centre d'intérêt,
**afin de** configurer en un seul endroit le périmètre et le sujet de la synthèse quotidienne.

**Description fonctionnelle**
Nouvelle section « 📰 Synthèse du jour » dans la console admin (`/admin`), contenant :
- **Sources à considérer** : choix multiple parmi les sources actives (checkboxes ou chips, ex. TLDR, blogs scrapés). La liste provient de `GET /admin/sources`.
- **Thèmes** : choix multiple parmi les catégories canoniques `["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"]`.
- **Centre d'intérêt** : champ texte libre, identique à l'existant (placeholder « Ex: SDLC à l'aune de l'IA »), **déplacé** depuis `/admin/synthesis` (il disparaît de cette page, qui devient consultation pure).
- Bouton « Sauvegarder » unique pour la section, avec feedback « ✓ Sauvegardé » 3s / « ✗ Erreur ».

**Règles métier**
- Persistance dans `settings/global` : nouveaux champs `synthesis_source_ids: string[]` et `synthesis_categories: string[]`, champ `interest` inchangé (rétrocompat).
- Sélection vide de sources = **toutes les sources** ; sélection vide de thèmes = **tous les thèmes** (comportement actuel conservé par défaut).
- `interest` vide = synthèse désactivée (règle existante inchangée).
- L'effet n'est visible qu'au **prochain run** du collector.

**Critères d'acceptation**
1. La section « Synthèse du jour » est visible dans `/admin` (admins uniquement).
2. Les sources actives s'affichent en choix multiple ; les 7 catégories canoniques aussi.
3. Sauvegarder persiste `synthesis_source_ids`, `synthesis_categories` et `interest` dans `settings/global` (via `PUT /admin/settings`).
4. Les valeurs persistent entre sessions et se rechargent à l'ouverture de la page.
5. Le champ « Centre d'intérêt » n'apparaît plus sur `/admin/synthesis`.

**Cas limites**
- Une source sélectionnée puis supprimée/désactivée ensuite → ignorée silencieusement au run suivant (pas d'erreur).
- Un `synthesis_source_ids` référençant une source inconnue n'empêche pas la sauvegarde ni la synthèse.

---

### US-SYN-102 — Constitution du corpus : filtrage par sources et thèmes

**En tant que** système (collector),
**je veux** restreindre le corpus de la synthèse aux articles des sources et thèmes sélectionnés,
**afin de** générer une synthèse ciblée sur le périmètre choisi par l'admin.

**Description fonctionnelle**
Dans `run()` du collector, à l'étape synthèse : lecture de `synthesis_source_ids` et `synthesis_categories` depuis `settings/global`. La requête Firestore des articles récents (tri `collected_at` desc, plafond 100) est filtrée sur `source_id ∈ synthesis_source_ids` et `category ∈ synthesis_categories`.

**Règles métier**
- Liste vide ou absente = pas de filtre sur cette dimension (rétrocompat : settings existants sans ces champs → comportement actuel).
- Le plafond de 100 articles s'applique **après** filtrage (les 100 plus récents du périmètre).
- Le document `syntheses/{date}` mémorise le périmètre utilisé : champs `source_ids` et `categories` ajoutés (traçabilité affichable dans l'IHM).

**Critères d'acceptation**
1. Avec TLDR + IA sélectionnés, seuls les articles `source_id = tldr` et `category = IA` entrent dans le corpus.
2. Avec sélections vides, le corpus est identique à l'existant (100 derniers articles toutes sources/catégories).
3. Si le corpus filtré est vide, la synthèse indique explicitement « Aucun article dans le périmètre sélectionné » (pas d'appel LLM).
4. `syntheses/{date}` contient le périmètre (`source_ids`, `categories`) et `articles_count` reflète le corpus filtré.

---

### US-SYN-103 — Récupération et nettoyage du contenu intégral

**En tant que** système (collector),
**je veux** télécharger le contenu complet de chaque article du corpus et le réduire à du texte brut,
**afin de** fournir au LLM la matière intégrale des articles tout en maîtrisant la taille du prompt.

**Description fonctionnelle**
Pour chaque article du corpus (US-SYN-102), le collector télécharge la page `article_url` (HTTP GET, timeout court), puis extrait le texte utile :
- Suppression des balises `<script>`, `<style>`, `<img>`, `<svg>`, `<iframe>`, `<nav>`, `<header>`, `<footer>`, commentaires HTML, attributs et CSS inline.
- Extraction du texte (type `BeautifulSoup.get_text()`), normalisation des espaces/retours à la ligne.
- Troncature par article à un plafond configurable en constante (ex. `SYNTHESIS_MAX_CHARS_PER_ARTICLE`), pour que le corpus total tienne dans la limite existante du prompt (180 000 caractères).

**Règles métier**
- Échec de téléchargement (timeout, 4xx/5xx, paywall) → **fallback** sur les données déjà stockées (titre + description longue FR), l'article n'est pas exclu ; l'échec est loggé (visible dans le rapport de run).
- Les articles Gmail/TLDR pointent vers des URLs externes : même traitement (téléchargement de l'URL cible).
- Téléchargements séquentiels ou faiblement parallélisés avec timeout unitaire (ex. 10 s) pour borner la durée du run.
- Aucun contenu téléchargé n'est persisté en Firestore (usage éphémère pour le prompt uniquement).

**Critères d'acceptation**
1. Le texte envoyé au LLM ne contient ni balise HTML, ni CSS, ni contenu de script, ni référence d'image.
2. Un article dont l'URL est injoignable apparaît quand même dans le corpus via son titre + description (fallback), avec un warning en log.
3. La taille du corpus total envoyé au LLM respecte le plafond de 180 000 caractères (troncature équitable par article).
4. Le run du collector se termine même si toutes les URLs sont injoignables (synthèse sur les résumés, comportement actuel).

**Cas limites**
- Pages très volumineuses (> plafond par article) → tronquées, jamais bloquantes.
- Contenu non-HTML (PDF, redirection binaire) → fallback résumé.
- Site lent → timeout unitaire, fallback résumé.

---

### US-SYN-104 — Génération de la synthèse sur le contenu intégral

**En tant que** système (collector),
**je veux** envoyer au LLM le texte nettoyé de tous les articles, le prompt de synthèse et le centre d'intérêt,
**afin de** produire une synthèse quotidienne plus pertinente que celle basée sur les résumés.

**Description fonctionnelle**
`generate_synthesis` (dans `processors/gemini_processor.py`) est adapté pour recevoir le corpus au format texte intégral : chaque article y figure sous la forme `[ID:{id}] {titre}` suivi de son texte nettoyé (ou du fallback résumé). Le prompt conserve la structure de sortie existante (`{synthesis, cited_ids}`, sections « 🔭 Vue d'ensemble » / « 🔑 Points clés » / « 📈 Tendances » / « ❓ Ce qui manque »), avec le centre d'intérêt injecté comme aujourd'hui.

**Règles métier**
- Cascade de fallback sur `model_priority` inchangée ; si tous les modèles échouent → message « ⚠️ Synthèse indisponible » (comportement existant).
- Écriture dans `syntheses/{date}` inchangée (écrasement si re-run le même jour), enrichie du périmètre (cf. US-SYN-102).
- L'affichage `/admin/synthesis` existant (cards, articles cités, modal) fonctionne sans modification de structure de données autre que les champs additifs.

**Critères d'acceptation**
1. Le prompt envoyé au LLM contient : le prompt de synthèse + le centre d'intérêt + le texte intégral nettoyé des articles du périmètre.
2. `cited_ids` ne référence que des IDs du corpus filtré.
3. La synthèse s'affiche dans `/admin/synthesis` comme aujourd'hui, avec mention du périmètre (sources/thèmes) dans l'en-tête de la card.
4. Les tests fonctionnels mockent `_call_llm` / le téléchargement HTTP (pas de quota Gemini ni de réseau consommés).

---

### US-SYN-105 — Générer manuellement la synthèse du jour

**En tant qu'** admin,
**je veux** déclencher la génération de la synthèse depuis la page `/admin/synthesis`,
**afin de** voir immédiatement l'effet d'un changement de centre d'intérêt ou de périmètre, sans attendre le prochain run planifié.

**Description fonctionnelle**
Bouton « ⚡ Générer la synthèse maintenant » en bas de la section « Synthèse du jour » de la console admin (`/admin`) — au même endroit que la configuration du périmètre. Le clic **sauvegarde d'abord le périmètre affiché** (sources, thèmes, centre d'intérêt, volume max), puis appelle `POST /admin/synthesis/generate` (admin uniquement, 202), qui déclenche le Cloud Run Job collector avec `COLLECTOR_SYNTHESIS_ONLY=1` (en local : sous-processus vers l'émulateur). Dans ce mode, le collector saute entièrement la collecte (scraping, enrichissement) et régénère uniquement la synthèse. Le front re-interroge `GET /admin/syntheses` toutes les 10 s jusqu'à voir un `generated_at` plus récent (abandon avec message après 5 min), puis affiche un lien « Voir la synthèse → » vers `/admin/synthesis`.

**Règles métier**
- Le mode manuel **contourne le skip « rien de nouveau »** : un clic régénère toujours (`new_articles=None` dans `run_synthesis`).
- Le clic persiste le périmètre en cours d'édition avant de générer — ce qu'on voit est ce qui est généré.
- Centre d'intérêt vide → bloqué côté front avec message explicite ; l'endpoint répond de toute façon 400, aucun job lancé.
- **Date de la synthèse** : champ date dans l'encart, défaut = aujourd'hui, futur interdit (contrôle front `max` + 400 backend). Une date passée applique la même logique **comme si le run avait eu lieu ce jour-là** : corpus = articles collectés jusqu'à la fin du jour choisi (`collected_at <= date T23:59:59`), document écrit dans `syntheses/{date}` (champ `target_date` persisté). La page Synthèse accepte `?date=YYYY-MM-DD` pour consulter cette date (bandeau explicite) et affiche « générée a posteriori le … » quand la génération est postérieure au jour de la synthèse.
- Le bouton est désactivé pendant la génération (anti double-clic).
- Le rapport de run (`reports/latest`) est aussi généré en mode manuel (traçabilité).
- Chaque clic consomme un cycle LLM complet (sélection + synthèse) — mentionné dans le tooltip du bouton.

**Critères d'acceptation**
1. Le bouton est visible dans la section « Synthèse du jour » de `/admin` et déclenche l'endpoint.
2. Pendant la génération : bouton désactivé, message « Génération en cours… ».
3. À l'arrivée de la nouvelle synthèse : « ✓ Synthèse générée » + lien « Voir la synthèse → » vers `/admin/synthesis`.
4. Sans centre d'intérêt : message d'erreur explicite, pas de job lancé.
5. Le périmètre modifié mais non sauvegardé est persisté par le clic avant la génération.
6. Après 5 min sans nouvelle synthèse : message renvoyant vers le rapport de run.

---

## Dépendances

- Backend : `GET/PUT /admin/settings` (champs additifs `synthesis_source_ids`, `synthesis_categories`), `GET /admin/sources`, `GET /admin/syntheses`.
- Collector : `run()` (étape 4), `generate_synthesis()` dans `gemini_processor.py`, nouveau module de récupération/nettoyage de contenu (réutilise `requests` + `BeautifulSoup` déjà présents dans les scrapers).
- Frontend : `/admin` (nouvelle section « Synthèse du jour »), `/admin/synthesis` (retrait du champ centre d'intérêt, affichage du périmètre).
- Firestore : champs additifs sur `settings/global` et `syntheses/{date}` — aucune nouvelle collection, pas de changement de `firestore.rules`.

## Contraintes

- **Coût / taille de prompt** : le contenu intégral est beaucoup plus volumineux que les résumés — plafonds par article et global (180 k caractères) obligatoires ; risque accru de fallback vers des modèles moins prioritaires si dépassement de quota.
- **Durée du run** : jusqu'à 100 téléchargements HTTP s'ajoutent au run du collector (Cloud Run Job) — timeouts unitaires courts et plafond global impératifs.
- **Robustesse** : paywalls, pages JS-only (contenu non présent dans le HTML statique) et anti-bots dégradent le contenu récupéré → le fallback résumé garantit qu'aucun article n'est perdu.
- **Rétrocompat** : settings existants sans les nouveaux champs → comportement strictement identique à l'actuel (aucune migration de données).
- **Sécurité** : le texte téléchargé est du contenu externe non fiable injecté dans le prompt — le rendu de la synthèse reste protégé par escape HTML + DOMPurify (cf. 09-admin-synthesis.md).
