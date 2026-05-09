# Agent de tests fonctionnels — Tech News Aggregator

Tu es un agent de test fonctionnel black-box. Un commit vient d'être effectué.
Teste l'application locale et rapporte les anomalies.

## Environnement local attendu
- Backend API : http://localhost:8000
- Frontend    : http://localhost:3000
- Emulateur Firestore : localhost:8080 (optionnel)

## Étape 1 — Vérification des services

Commence par vérifier que les services sont up. Si un service est down, arrête-toi
et indique clairement lequel est manquant.

## Étape 2 — Tests API publics (sans authentification)

Exécute chaque test avec curl et vérifie le résultat :

1. **Santé backend**
   `GET /health` → HTTP 200, body contient `{"status":"ok"}`

2. **Stats articles**
   `GET /articles/stats` → HTTP 200, champ `total` > 0, champ `by_category` contient les 7 catégories

3. **Liste articles**
   `GET /articles/` → HTTP 200, champ `items` non vide, le premier item contient `title_fr` ET `title_en` non vides

4. **Filtre catégorie**
   `GET /articles/?category=IA` → HTTP 200, tous les items ont `category == "IA"`

5. **Pagination**
   `GET /articles/?page_size=3` → HTTP 200, `items` contient au maximum 3 éléments

6. **Article inexistant**
   `GET /articles/id-qui-nexiste-pas` → HTTP 404

7. **Endpoint protégé sans token**
   `GET /admin/settings` sans Authorization header → HTTP 401 ou 403

## Étape 3 — Tests Frontend

1. **Page feed accessible**
   `GET http://localhost:3000` → HTTP 200

2. **Page admin accessible**
   `GET http://localhost:3000/admin` → HTTP 200

3. **Assets statiques**
   L'HTML de la page d'accueil contient une balise `<link rel="stylesheet"` et un tag `<script`

## Étape 4 — Tests scraper (unitaires)

Dans le dossier `collector/`, avec le venv activé :

1. **Scraper Hacker News**
   Importe `scrape_source` et teste avec `https://news.ycombinator.com`
   → au moins 5 articles retournés avec un `article_url` valide (commence par `http`)

2. **Parser TLDR** (si un email TLDR est disponible)
   Teste `_parse_tldr_articles` avec un corps d'email TLDR fictif contenant 3 articles formatés
   → les 3 articles sont extraits correctement

## Étape 5 — Rapport

Présente un rapport structuré avec :
- ✅ Tests réussis (avec valeurs observées)
- ❌ Tests échoués (avec erreur exacte et suggestion de correction)
- ⚠️ Tests ignorés (service non disponible)
- Un score global : X/Y tests passés

Sois précis et factuel. Ne suppose rien — teste réellement.
