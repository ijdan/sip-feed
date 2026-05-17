# language: fr
Fonctionnalité: Page Admin — Statistiques

  La page /admin/stats consolide quatre pavés d'information à destination
  de l'administrateur : l'inventaire total des articles en base (toutes dates
  confondues), le nombre d'utilisateurs enregistrés, l'activité API sur
  /articles/ et l'engagement article par utilisateur.

  L'inventaire des articles est fourni par GET /articles/stats, indépendant
  de GET /admin/stats. Les deux appels sont effectués en parallèle et un
  échec partiel n'empêche pas l'affichage des autres pavés.

  Contexte:
    Étant donné que l'API backend est démarrée
    Et qu'un token admin valide est disponible

  # ── Pavé 1 : Inventaire des articles ──────────────────────────────────────

  Scénario: L'endpoint /articles/stats retourne le total global des articles
    Étant donné que Firestore contient 5 articles
    Quand je requête GET /articles/stats avec le token admin
    Alors la réponse contient le champ "total" égal à 5

  Scénario: L'endpoint /articles/stats ventile les articles par catégorie
    Étant donné que Firestore contient les articles suivants :
      | id | category |
      | A1 | IA       |
      | A2 | IA       |
      | A3 | Cloud    |
      | A4 | DevOps   |
      | A5 | Autre    |
    Quand je requête GET /articles/stats avec le token admin
    Alors la réponse contient le champ "by_category.IA" égal à 2
    Et la réponse contient le champ "by_category.Cloud" égal à 1
    Et la réponse contient le champ "by_category.DevOps" égal à 1
    Et la réponse contient le champ "by_category.Autre" égal à 1

  Scénario: Le total des articles inclut les articles hors fenêtre de rétention
    Étant donné que le paramètre "retention_days" vaut 7
    Et que Firestore contient les articles suivants :
      | id | collected_at    |
      | A1 | aujourd'hui     |
      | A2 | il y a 30 jours |
    Quand je requête GET /articles/stats avec le token admin
    Alors la réponse contient le champ "total" égal à 2

  Scénario: Une catégorie inconnue est comptabilisée dans "Autre"
    Étant donné que Firestore contient un article avec la catégorie "Inconnu"
    Quand je requête GET /articles/stats avec le token admin
    Alors la réponse contient le champ "by_category.Autre" supérieur ou égal à 1

  Scénario: L'accès à /articles/stats est refusé sans token admin
    Quand je requête GET /articles/stats sans token d'authentification
    Alors la réponse a le statut HTTP 401

  # ── Pavé 2 : Utilisateurs enregistrés ────────────────────────────────────

  Scénario: L'endpoint /admin/stats retourne le nombre d'utilisateurs enregistrés
    Étant donné que Firestore contient 3 documents dans la collection "users"
    Quand je requête GET /admin/stats avec le token admin
    Alors la réponse contient le champ "users_count" égal à 3

  # ── Pavé 3 : Activité API ─────────────────────────────────────────────────

  Scénario: L'endpoint /admin/stats agrège les appels API sur aujourd'hui, 7 jours et 30 jours
    Étant donné que la collection "api_stats" contient les entrées suivantes :
      | date           | identifier      | count |
      | aujourd'hui    | user@example.fr | 5     |
      | il y a 3 jours | user@example.fr | 8     |
      | il y a 15 jours| user@example.fr | 3     |
    Quand je requête GET /admin/stats avec le token admin
    Alors la réponse contient pour "user@example.fr" : today=5, last_7=13, last_30=16

  Scénario: Les identifiants IP et email sont tous deux retournés dans les appels API
    Étant donné que la collection "api_stats" contient des entrées pour "ip:192.168.1.1" et "user@example.fr"
    Quand je requête GET /admin/stats avec le token admin
    Alors la liste "api_calls" contient un élément avec identifier="ip:192.168.1.1"
    Et la liste "api_calls" contient un élément avec identifier="user@example.fr"

  Scénario: La liste des appels API est triée par activité décroissante sur 30 jours
    Étant donné que deux identifiants ont respectivement 10 et 50 appels sur 30 jours
    Quand je requête GET /admin/stats avec le token admin
    Alors le premier élément de "api_calls" est celui ayant 50 appels sur 30 jours

  # ── Pavé 4 : Activité articles par utilisateur ───────────────────────────

  Scénario: L'endpoint /admin/stats retourne les compteurs d'activité article par utilisateur
    Étant donné que Firestore contient dans "user_preferences" le document "user@example.fr" :
      | champ        | valeur                  |
      | favorites    | ["A1", "A2"]            |
      | reading_list | ["A3"]                  |
      | read_articles| ["A4", "A5", "A6"]      |
      | dismissed    | []                      |
    Quand je requête GET /admin/stats avec le token admin
    Alors la liste "user_article_stats" contient pour "user@example.fr" : favorites=2, reading_list=1, read_articles=3, dismissed=0

  Scénario: La liste des stats utilisateurs est triée par nombre de favoris décroissant
    Étant donné que deux utilisateurs ont respectivement 1 et 5 favoris
    Quand je requête GET /admin/stats avec le token admin
    Alors le premier élément de "user_article_stats" est celui ayant 5 favoris

  # ── Accès ─────────────────────────────────────────────────────────────────

  Scénario: L'accès à /admin/stats est refusé sans token admin
    Quand je requête GET /admin/stats sans token d'authentification
    Alors la réponse a le statut HTTP 401

  Scénario: L'accès à /admin/stats est refusé avec un token reader
    Étant donné qu'un token reader valide est disponible
    Quand je requête GET /admin/stats avec le token reader
    Alors la réponse a le statut HTTP 403
