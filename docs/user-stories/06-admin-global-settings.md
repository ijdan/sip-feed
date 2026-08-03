# Console admin — Paramètres globaux LLM & collecte

## Contexte fonctionnel

La page `/admin` (réservée aux administrateurs) expose les paramètres globaux qui pilotent le **collector** : activation du LLM, mode "thinking" Gemini, ordre de priorité des modèles Gemini, lookback Gmail, rétention des articles, centre d'intérêt pour la synthèse. Ces paramètres sont stockés dans `settings/global` côté Firestore et lus par le collector à chaque run.

## Objectif

- Permettre à un admin de modifier le comportement de la collecte sans déployer du code.
- Garder l'historique des modèles LLM disponibles à jour (fallback en cascade).
- Donner une visibilité immédiate sur les réglages actifs.

## User Stories

### US-ADM-001 — Activer / désactiver le traitement LLM

**En tant qu'** admin,
**je veux** désactiver Gemini en cas de quota épuisé ou pour économiser,
**afin de** que le collector continue à fonctionner en mode "raw" (titres bruts).

**Description fonctionnelle**
Switch "Activer le traitement LLM" dans `/admin`. Quand désactivé, le collector sauvegarde les articles **sans enrichissement** (titres tels que scrapés, descriptions tronquées du raw_content, catégorie "Autre" par défaut).

**Règles métier**
- Par défaut : activé.
- Désactivation immédiate au prochain run (lu à chaque run via `get_global_settings()`).
- Le mode "Thinking" (US-ADM-002) est forcément désactivé si LLM est OFF.

**Critères d'acceptation**
1. Le switch est visible dans `/admin`, mis en évidence selon son état.
2. Cliquer le switch change l'état en backend immédiatement (PUT /admin/settings).
3. Le switch "Thinking" est grisé si LLM est OFF.
4. Au prochain run du collector, les logs confirment "LLM désactivé — sauvegarde des articles bruts".

---

### US-ADM-002 — Activer / désactiver le mode Thinking de Gemini

**En tant qu'** admin,
**je veux** activer le mode "Thinking" de Gemini pour les modèles qui le supportent,
**afin de** obtenir une meilleure qualité de synthèse au prix d'un délai plus long.

**Description fonctionnelle**
Switch indépendant. Configure `thinking_config = {"thinking_budget": -1}` (auto) ou `0` (off) lors de l'appel `genai.GenerativeModel`. Si le modèle ne supporte pas thinking, fallback sans erreur.

**Règles métier**
- Désactivé automatiquement si `llm_enabled = False`.
- Affecte tous les appels LLM du run (batch enrichissement + synthèse + rapport).

**Critères d'acceptation**
1. Le switch est visible et changeable d'état.
2. Au run suivant, les logs indiquent "Thinking mode : activé (auto)" ou "désactivé".
3. Si un modèle ne supporte pas thinking, le run ne crashe pas (fallback silent).

---

### US-ADM-003 — Réordonner la priorité des modèles LLM

**En tant qu'** admin,
**je veux** réordonner la liste des modèles Gemini (cascade de fallback),
**afin de** privilégier les modèles récents tout en gardant un fallback en cas de quota.

**Description fonctionnelle**
Liste ordonnée des modèles connus avec boutons ▲▼ pour réordonner. Chaque modèle a une étiquette explicative (ex. "Gemini 3 Flash — Dernière génération", "Gemini 2.0 Flash Lite — Dernier recours"). La liste persiste dans `model_priority[]`.

**Règles métier**
- **L'ordre choisi ici est appliqué littéralement à chaque appel LLM.** Aucune déduction du code : ni tri, ni purge, ni insertion. Modifier `DEFAULT_MODEL_PRIORITY` n'a aucun effet sur un projet existant — cette constante n'amorce qu'un projet neuf, quand aucun ordre n'a encore été choisi.
- La liste d'amorçage `DEFAULT_MODEL_PRIORITY` (2 exemplaires — cf. CLAUDE.md) est ordonnée du moins cher au plus cher parmi les modèles qui tiennent la qualité attendue. Les Gemma sont les moins chers du catalogue mais rendent des descriptions trop courtes pour la fiche article (4 à 6 phrases attendues) : ils y figurent en **repli de dernier recours**. Ce n'est qu'un point de départ — l'admin reste libre de tout réordonner.
- Le GET est en **lecture seule** : il restitue l'ordre stocké sans le réécrire. Seul le PUT (boutons ▲▼) modifie `model_priority`. Un modèle hors catalogue est signalé dans les logs mais reste sollicité.
- Motifs de montée d'un cran, journalisés distinctement dans le rapport d'exécution :
  - **dépassement** (429 de quota ou de débit) → cas nominal, c'est la raison d'être de la cascade ;
  - **anomalie** (404 modèle inconnu, 400 requête invalide, réponse vide ou non conforme au JSON demandé) → on monte aussi, mais c'est un défaut à corriger ;
  - **blocage du compte** (429 de facturation) → arrêt immédiat, aucun modèle ne peut aboutir.
- La validité du JSON est vérifiée **dans** la cascade (`_call_llm`) : une réponse malformée fait monter d'un cran au lieu de faire basculer tout le run vers `save_raw_articles`.

**Critères d'acceptation**
1. La liste affiche les 5 modèles dans l'ordre actuel.
2. Cliquer ▲ ou ▼ déplace le modèle d'une position.
3. La sauvegarde est immédiate (PUT /admin/settings).
4. Le collector utilise réellement l'ordre au prochain run (vérifiable dans les logs).
5. L'ordre affiché est exactement celui stocké : ouvrir la page ne le réécrit jamais.

**Cas limites**
- L'admin vide la liste (impossible via l'UI, possible en raw API) → amorçage sur `DEFAULT_MODEL_PRIORITY`.
- Un modèle est retiré du catalogue Google mais reste dans l'ordre choisi → il est sollicité quand même, échoue en 404, et la cascade monte d'un cran. Un avertissement le signale dans les logs ; à l'admin de le retirer.
- Un nouveau modèle est ajouté côté code → il n'apparaît **pas** automatiquement. C'est le prix de la règle « aucune déduction ».

---

### US-ADM-004 — Configurer le lookback Gmail

**En tant qu'** admin,
**je veux** définir combien de jours en arrière le collector lit les newsletters Gmail,
**afin de** récupérer les articles d'un week-end (3 jours) sans dupliquer trop d'anciens.

**Description fonctionnelle**
Sélecteur dans `/admin` avec valeurs `[1, 2, 3, 5, 7, 10]` jours. Utilisé par `read_gmail_source(source, lookback_days=X)` qui filtre via `newer_than:{X}d` dans la query Gmail.

**Règles métier**
- Par défaut : 1 jour.
- La dédup contre la base Firestore empêche les doublons même si lookback élargi.

**Critères d'acceptation**
1. Le sélecteur est visible avec les 6 options.
2. Sélectionner 7 → le run suivant fait `newer_than:7d` sur Gmail.
3. Les emails déjà collectés ne sont pas re-saved (dédup par URL).

---

### US-ADM-005 — Rétention des articles (purge automatique)

**En tant qu'** admin,
**je veux** définir combien de jours les articles sont conservés (au-delà ils sont supprimés),
**afin de** maîtriser la croissance de la base et le coût Firestore.

**Description fonctionnelle**
Sélecteur dans `/admin` avec valeurs `[0, 1, 2, 3, 4, 5, 6, 7, 15, 30, 90, 365]` (0 = illimité). À la fin de chaque run, si des nouveaux articles ont été collectés, le collector appelle `apply_retention(days)` qui supprime tous les articles dont `collected_at < now - days`.

**Règles métier**
- Par défaut : 0 (illimité, aucune purge).
- La purge ne s'exécute **que si** au moins un nouvel article a été collecté (évite les vagues de suppression sur runs vides).
- Suppression par batch Firestore (`batch.commit()` tous les 500 docs).

**Critères d'acceptation**
1. Le sélecteur affiche "Illimitée" pour 0.
2. Sélectionner 7 → au prochain run avec des articles, les articles > 7 jours sont supprimés.
3. Le compteur supprimé est loggé.
4. Si 0 nouvel article → aucune purge même si rétention configurée.

**Cas limites**
- Tous les articles ont > rétention jours et 1 nouvel article arrive → tous les anciens sont purgés en un coup. Risque : si l'admin a mal lu, panique.

---

### US-ADM-006 — Définir le centre d'intérêt pour la synthèse

**En tant qu'** admin,
**je veux** renseigner un centre d'intérêt (ex. "SDLC à l'aune de l'IA"),
**afin de** que le LLM produise une synthèse markdown ciblée après chaque collecte.

**Description fonctionnelle**
Champ texte libre dans `/admin/synthesis`. Stocké dans `settings.interest`. Si non vide, le collector appelle `generate_synthesis(articles[100], interest, model_priority)` à chaque run, et écrit le résultat dans `syntheses/{date}`.

**Règles métier**
- Vide = synthèse désactivée.
- La synthèse opère sur les **100 derniers articles** (par `collected_at` desc), peu importe l'âge.
- Le LLM produit aussi `cited_ids` (les articles réellement utilisés).

**Critères d'acceptation**
1. Le champ texte est visible avec placeholder ("Ex: SDLC à l'aune de l'IA").
2. Cliquer Sauvegarder → persistance immédiate.
3. Au prochain run, la synthèse est générée (visible dans `/admin/synthesis`).
4. Vider le champ → désactive la synthèse.

---

## Dépendances

- Backend : `GET/PUT /admin/settings` (require_admin).
- Collector : `get_global_settings()` lu à chaque run.
- Frontend : composant `AdminSettings.tsx`.

## Contraintes

- **Métier** : seuls les utilisateurs avec `role: admin` peuvent modifier ces paramètres.
- **Technique** : la modification d'un paramètre n'a d'effet qu'**au prochain run** du collector (Cloud Scheduler ou bouton "Lancer la collecte"). Pas de hot-reload du collector.
- **Synchro** : le champ `interest` est édité depuis `/admin/synthesis` (cf. 09-admin-synthesis.md) mais persiste dans le même document `settings/global` que les autres réglages.
