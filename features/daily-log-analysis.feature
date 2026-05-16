# language: fr
Fonctionnalité: Analyse quotidienne des logs GCP par LLM

  Chaque nuit à 05h00, le job log-analyzer récupère les logs WARNING+
  des 24 dernières heures depuis Cloud Logging, les soumet à Gemini,
  et stocke un rapport structuré dans Firestore (log_analyses/{date}).
  Le backend expose ce rapport aux admins via GET /admin/log-analysis.

  Contexte:
    Étant donné que l'API backend est démarrée
    Et que Firestore est disponible

  # --- US-DLA-002 : collecte des logs ---

  Scénario: Les logs INFO sont ignorés — seuls WARNING+ sont collectés
    Étant donné que Cloud Logging contient les entrées suivantes sur les dernières 24h :
      | severity | message              |
      | INFO     | "Démarrage du backend" |
      | WARNING  | "Quota LLM à 80%"    |
      | ERROR    | "Timeout source RSS" |
    Quand le job log-analyzer collecte les logs
    Alors les entrées collectées contiennent uniquement les entrées "WARNING" et "ERROR"
    Et l'entrée "INFO" n'est pas collectée

  Scénario: Aucun log WARNING+ dans les 24h — pas d'anomalie détectée
    Étant donné que Cloud Logging ne contient aucune entrée WARNING ou supérieure sur les dernières 24h
    Quand le job log-analyzer collecte les logs
    Alors le champ "logs_count" du rapport vaut 0
    Et le champ "items" du rapport est vide
    Et le champ "resume" indique qu'aucune anomalie n'a été détectée

  Scénario: Volume de logs dépasse 2000 entrées — les ERROR sont priorisés
    Étant donné que Cloud Logging contient 1800 entrées WARNING et 500 entrées ERROR sur les dernières 24h
    Quand le job log-analyzer collecte les logs
    Alors toutes les 500 entrées ERROR sont incluses dans la collecte
    Et le total collecté ne dépasse pas 2000 entrées
    Et le champ "resume" mentionne que le volume a été tronqué

  # --- US-DLA-003 : analyse LLM ---

  Scénario: Le rapport LLM contient les champs requis pour chaque item
    Étant donné que Cloud Logging contient des entrées ERROR sur les dernières 24h
    Quand le job log-analyzer génère le rapport
    Alors chaque item du rapport contient les champs "point_notable", "prompt_correction", "date" et "priorite"
    Et le champ "priorite" de chaque item est l'un de : "CRITIQUE", "HAUTE", "MOYENNE", "BASSE"
    Et le nombre d'items ne dépasse pas 20

  Scénario: Les items sont triés par priorité décroissante
    Étant donné que le LLM retourne des items avec les priorités : "BASSE", "CRITIQUE", "HAUTE", "MOYENNE"
    Quand le rapport est stocké dans Firestore
    Alors les items sont ordonnés : "CRITIQUE" en premier, puis "HAUTE", "MOYENNE", "BASSE"

  Scénario: Tous les modèles Gemini sont indisponibles — fallback gracieux
    Étant donné que tous les modèles Gemini retournent une erreur de quota
    Quand le job log-analyzer tente de générer le rapport
    Alors le rapport est quand même écrit dans Firestore
    Et le champ "items" est vide
    Et le champ "resume" contient le message d'indisponibilité LLM

  # --- US-DLA-004 : stockage Firestore ---

  Scénario: Le document Firestore est créé avec la date couverte comme clé
    Étant donné que le job s'exécute le 2026-05-17 à 05h00
    Et que la période couverte est le 2026-05-16 (les 24h précédentes)
    Quand le rapport est généré avec succès
    Alors le document Firestore existe à la clé "log_analyses/2026-05-16"
    Et le champ "date" du document vaut "2026-05-16"
    Et le champ "generated_at" est renseigné

  Scénario: Le job est idempotent — un second run le même jour ne recrée pas le rapport
    Étant donné qu'un rapport existe déjà dans Firestore à la clé "log_analyses/2026-05-16"
    Quand le job log-analyzer s'exécute à nouveau pour la même journée
    Alors aucun nouveau document n'est créé ou écrasé dans Firestore
    Et le job se termine normalement sans erreur

  # --- US-DLA-005 : endpoints backend ---

  Scénario: Un admin récupère le rapport du jour
    Étant donné qu'un rapport existe dans Firestore pour aujourd'hui
    Et que l'utilisateur est authentifié en tant qu'admin
    Quand il requête GET /admin/log-analysis
    Alors la réponse a le statut 200
    Et la réponse contient les champs "date", "generated_at", "logs_count", "resume" et "items"

  Scénario: Rapport non disponible pour la date demandée — 404
    Étant donné qu'aucun rapport n'existe dans Firestore pour la date "2099-01-01"
    Et que l'utilisateur est authentifié en tant qu'admin
    Quand il requête GET /admin/log-analysis/2099-01-01
    Alors la réponse a le statut 404

  Scénario: Un reader tente d'accéder au rapport — accès refusé
    Étant donné qu'un rapport existe dans Firestore pour aujourd'hui
    Et que l'utilisateur est authentifié en tant que reader
    Quand il requête GET /admin/log-analysis
    Alors la réponse a le statut 403

  Scénario: Format de date invalide dans l'URL — erreur de validation
    Étant donné que l'utilisateur est authentifié en tant qu'admin
    Quand il requête GET /admin/log-analysis/not-a-date
    Alors la réponse a le statut 422

  # --- US-DLA-006 : UI admin (non testés en pytest-bdd — implémentation frontend) ---

  Scénario: La page /admin/log-analysis est accessible uniquement aux admins
    Étant donné qu'un utilisateur est connecté avec le rôle "reader"
    Quand il navigue vers "/admin/log-analysis"
    Alors il est redirigé vers "/"

  Scénario: La page affiche le résumé global et les items du rapport du jour
    Étant donné qu'un utilisateur est connecté avec le rôle "admin"
    Et qu'un rapport existe pour aujourd'hui avec 3 items et un résumé "RAS hormis un timeout"
    Quand il navigue vers "/admin/log-analysis"
    Alors le résumé "RAS hormis un timeout" est affiché en haut de page
    Et 3 cards d'items sont visibles

  Scénario: Les items sont affichés triés par priorité avec un badge coloré
    Étant donné qu'un utilisateur admin consulte la page "/admin/log-analysis"
    Et que le rapport contient un item CRITIQUE, un item HAUTE et un item BASSE
    Alors l'item CRITIQUE apparaît en premier avec un badge rouge
    Et l'item HAUTE apparaît en second avec un badge orange
    Et l'item BASSE apparaît en dernier avec un badge gris

  Scénario: Le bouton "Copier le prompt" copie le prompt_correction dans le presse-papier
    Étant donné qu'un utilisateur admin consulte la page "/admin/log-analysis"
    Et qu'un item affiche le prompt_correction "Vérifie le timeout dans backend/app/routers/articles.py"
    Quand il clique sur le bouton "Copier le prompt" de cet item
    Alors le texte "Vérifie le timeout dans backend/app/routers/articles.py" est copié dans le presse-papier
    Et le bouton affiche "✓ Copié !" pendant 2 secondes

  Scénario: Le sélecteur de date permet de consulter un rapport antérieur
    Étant donné qu'un utilisateur admin consulte la page "/admin/log-analysis"
    Et qu'un rapport existe pour la date "2026-05-15"
    Quand il sélectionne la date "2026-05-15" dans le sélecteur
    Alors la page affiche le rapport du "2026-05-15"

  Scénario: Aucun rapport disponible pour la date sélectionnée
    Étant donné qu'un utilisateur admin consulte la page "/admin/log-analysis"
    Et qu'aucun rapport n'existe pour la date "2026-05-01"
    Quand il sélectionne la date "2026-05-01" dans le sélecteur
    Alors le message "Aucun rapport disponible pour cette date" est affiché

  Scénario: Aucune anomalie détectée — message explicite affiché
    Étant donné qu'un utilisateur admin consulte la page "/admin/log-analysis"
    Et que le rapport du jour contient 0 items
    Alors le message "Aucune anomalie détectée" est affiché de façon distincte
    Et aucune card d'item n'est visible

  Scénario: Le bouton Rafraîchir recharge le rapport sans rechargement de page
    Étant donné qu'un utilisateur admin consulte la page "/admin/log-analysis"
    Quand il clique sur le bouton "Rafraîchir"
    Alors une nouvelle requête GET /admin/log-analysis est émise
    Et la page se met à jour sans rechargement complet

  Scénario: La page "Analyse logs" est accessible depuis la navigation admin
    Étant donné qu'un utilisateur admin est connecté
    Quand il consulte la barre de navigation admin
    Alors un lien "Analyse logs" est visible et pointe vers "/admin/log-analysis"
