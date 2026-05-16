# language: fr
Fonctionnalité: Filtrage des articles par ancienneté sans suppression

  Le paramètre "retention_days" contrôle la fenêtre temporelle des articles
  affichés dans le feed. Les articles plus anciens restent dans Firestore
  mais ne sont pas restitués. Aucune suppression automatique n'est effectuée
  par le collector.

  Contexte:
    Étant donné que l'API backend est démarrée
    Et que Firestore contient les articles suivants :
      | id  | collected_at      |
      | A1  | aujourd'hui       |
      | A2  | il y a 5 jours    |
      | A3  | il y a 10 jours   |
      | A4  | il y a 30 jours   |

  Scénario: Le feed ne retourne que les articles dans la fenêtre de rétention
    Étant donné que le paramètre "retention_days" vaut 7
    Quand je requête GET /articles
    Alors la réponse contient les articles "A1" et "A2"
    Et la réponse ne contient pas les articles "A3" et "A4"
    Et le total retourné est 2

  Scénario: Rétention illimitée — tous les articles sont retournés
    Étant donné que le paramètre "retention_days" vaut 0
    Quand je requête GET /articles
    Alors la réponse contient les articles "A1", "A2", "A3" et "A4"
    Et le total retourné est 4

  Scénario: Les articles hors fenêtre restent présents dans Firestore
    Étant donné que le paramètre "retention_days" vaut 7
    Quand je requête GET /articles
    Alors les articles "A3" et "A4" existent toujours dans la collection Firestore "articles"

  Scénario: Le filtre se combine avec le filtre de catégorie
    Étant donné que le paramètre "retention_days" vaut 7
    Et que l'article "A1" a la catégorie "IA"
    Et que l'article "A2" a la catégorie "Cloud"
    Quand je requête GET /articles?category=IA
    Alors la réponse contient uniquement l'article "A1"

  Scénario: Le collector ne supprime plus les articles anciens
    Étant donné que le paramètre "retention_days" vaut 7
    Quand le collector termine une exécution
    Alors les articles "A3" et "A4" existent toujours dans la collection Firestore "articles"
