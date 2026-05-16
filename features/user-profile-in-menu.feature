# language: fr
Fonctionnalité: Affichage du nom et du rôle utilisateur dans le menu déroulant

  À l'intérieur du menu de navigation, l'identité de l'utilisateur
  connecté est affichée sous la forme "Nom (rôle)", avec le rôle
  tel qu'il est stocké en base (ex. "admin", "reader").

  Scénario: Utilisateur avec nom complet
    Étant donné qu'un utilisateur est connecté avec le nom "Jean Dupont"
    Et que son rôle est "admin"
    Alors le menu déroulant affiche "Jean Dupont (admin)"

  Scénario: Utilisateur avec rôle reader
    Étant donné qu'un utilisateur est connecté avec le nom "Jean Dupont"
    Et que son rôle est "reader"
    Alors le menu déroulant affiche "Jean Dupont (reader)"

  Scénario: Utilisateur sans nom — repli sur l'email
    Étant donné qu'un utilisateur est connecté sans nom
    Et que son email est "jean@example.com"
    Et que son rôle est "reader"
    Alors le menu déroulant affiche "jean@example.com (reader)"

  Scénario: Utilisateur non connecté
    Étant donné qu'aucun utilisateur n'est connecté
    Alors le menu déroulant n'affiche aucune identité
