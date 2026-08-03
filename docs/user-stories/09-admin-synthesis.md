# Console admin — Synthèse LLM ciblée

## Contexte fonctionnel

Si l'admin renseigne un **centre d'intérêt** (champ texte libre, ex. "SDLC à l'aune de l'IA"), le collector génère après chaque run une **synthèse markdown** analytique des 100 derniers articles, ciblée sur ce sujet. La synthèse est rendue dans `/admin/synthesis` (HTML escapé + DOMPurify pour sécurité).

## Objectif

- Offrir une vue agrégée et analytique du flux récent autour d'un thème.
- Identifier rapidement les tendances, signaux faibles, manques.
- Lier les articles cités à la synthèse pour navigation rapide.

## User Stories

### US-SYN-001 — Définir un centre d'intérêt

**En tant qu'** admin,
**je veux** renseigner un centre d'intérêt textuel,
**afin de** que le LLM produise une synthèse ciblée sur ce sujet à chaque collecte.

**Description fonctionnelle**
Champ texte + bouton "Sauvegarder" en haut de `/admin/synthesis`. Persiste dans `settings/global.interest`. Vide = synthèse désactivée.

**Règles métier**
- Pas de longueur max imposée.
- Modification immédiate côté backend (`PUT /admin/settings` avec settings complet).
- L'effet n'est visible qu'**au prochain run** du collector.

**Critères d'acceptation**
1. Le champ texte est visible avec placeholder "Ex: SDLC à l'aune de l'IA".
2. Renseigner + Sauvegarder → "✓ Sauvegardé" pendant 3s.
3. Vider + Sauvegarder → désactive la génération de synthèse.
4. La valeur persiste entre sessions.

---

### US-SYN-002 — Génération automatique de la synthèse

**En tant que** système,
**je veux** générer une synthèse markdown après chaque run du collector,
**afin de** maintenir une analyse à jour sans intervention manuelle.

**Description fonctionnelle**
À la fin de `run()` dans le collector, si `interest` non vide : `generate_synthesis(articles[100], interest, model_priority)`. Le LLM produit `{synthesis: markdown, cited_ids: [...]}`. Écrit dans `syntheses/{date.today().isoformat()}`.

**Règles métier**
- Toujours les **100 plus récents articles** par `collected_at` desc.
- Structure attendue (cf. prompt) : "🔭 Vue d'ensemble" / "🔑 Points clés" / "📈 Tendances" / "❓ Ce qui manque".
- Si tous les modèles LLM échouent → synthèse `"⚠️ Synthèse indisponible — tous les modèles LLM ont échoué :"` suivie de la cause réelle par modèle (code HTTP + message de l'API).
- Document Firestore : `{interest, content (markdown), cited_ids, articles_count, generated_at}`.

**Critères d'acceptation**
1. Après un run avec `interest` non vide, `syntheses/YYYY-MM-DD` existe en Firestore.
2. Le `content` contient du markdown structuré.
3. `cited_ids` ne contient que des IDs présents dans le corpus.
4. Si un run du même jour relance, le doc est **écrasé** (clé = date).
5. En cas de quota épuisé, un message warning remplace le contenu.

**Cas limites**
- Aucun article récent (base vide) → synthèse vide ou warning explicite.
- `cited_ids` référence des articles purgés entre-temps → certaines cards ne se rendront pas (fallback silencieux côté UI).

---

### US-SYN-003 — Afficher les synthèses des 3 derniers jours

**En tant qu'** admin,
**je veux** consulter les synthèses des 3 derniers jours,
**afin de** voir l'évolution du sujet dans le temps.

**Description fonctionnelle**
`/admin/synthesis` interroge `GET /admin/syntheses` (require_admin) qui renvoie les 3 derniers documents. Chaque synthèse est rendue dans une card avec en-tête (interest, date, articles_count, heure de génération) + corps markdown converti en HTML.

**Règles métier**
- Rendu markdown via `markdownToHtml` avec **escape HTML upstream** + DOMPurify (cf. priorité 1 audit sécu).
- Le bouton "Rafraîchir" recharge la liste sans full reload.

**Critères d'acceptation**
1. Page `/admin/synthesis` accessible aux admins uniquement (redirect `/` si reader).
2. Les 3 dernières synthèses s'affichent par date desc.
3. Le markdown est rendu en HTML avec emojis, titres, listes.
4. Aucune injection HTML possible depuis le contenu LLM (DOMPurify).
5. Si aucune synthèse → message "Aucune synthèse disponible".

---

### US-SYN-004 — Naviguer vers un article cité depuis la synthèse

**En tant qu'** admin,
**je veux** cliquer sur un article cité dans la synthèse,
**afin de** lire son détail sans quitter la page.

**Description fonctionnelle**
Sous chaque synthèse, la liste des "articles cités" est rendue en **chips cliquables** (pill buttons). Un clic ouvre une **modal** affichant : titre, source, description longue, bouton "Lire l'article →".

**Règles métier**
- Le backend résout les `cited_ids` en batch (`db.get_all([...])`) pour éviter N+1 queries (cf. optimisation C2 dans le code).
- Articles citées disparus (purgés) → simplement absents de la liste.

**Critères d'acceptation**
1. Chaque article cité apparaît comme une chip avec son titre.
2. Cliquer une chip ouvre une modal centrée avec les détails.
3. Cliquer en dehors de la modal la ferme.
4. Le lien "Lire l'article" ouvre l'URL externe en nouvel onglet.
5. La langue de la modal respecte `localStorage.feed-lang` (FR/EN).

---

### US-SYN-005 — Rafraîchir manuellement la synthèse

**En tant qu'** admin,
**je veux** rafraîchir la liste des synthèses sans reloader,
**afin de** voir la dernière sans interrompre ma navigation.

**Description fonctionnelle**
Bouton "Rafraîchir" en haut de la page → invalide le cache SWR et refetch.

**Critères d'acceptation**
1. Le bouton est visible et cliquable.
2. Cliquer déclenche un refetch (visible dans l'onglet Network).
3. Pas de spinner global ; l'utilisateur peut continuer à interagir.

---

## Dépendances

- Backend : `GET /admin/syntheses`, `GET/PUT /admin/settings`.
- Collector : `generate_synthesis()` dans `gemini_processor.py`.
- LLM Gemini avec cascade de fallback (cf. US-ADM-003).
- Frontend : `/admin/synthesis/page.tsx`, `markdownToHtml.ts` (XSS-safe).

## Contraintes

- **Sécurité** : le markdown produit par le LLM peut contenir du HTML hostile si un article hostile influence l'output. Le rendu est protégé par escape upstream + DOMPurify.
- **Métier** : le centre d'intérêt est unique (pas multi-utilisateur). Si plusieurs admins veulent suivre des sujets différents → contrainte à lever via une future US.
- **Coût** : 1 appel LLM par run (max 100 articles dans le prompt, max 8000 tokens en sortie).
