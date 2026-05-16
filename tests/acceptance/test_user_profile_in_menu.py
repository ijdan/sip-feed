from pytest_bdd import scenarios, given, when, then, parsers
import pytest

scenarios("../../features/user-profile-in-menu.feature")


@pytest.fixture
def contexte():
    return {
        "utilisateur": None,
    }


def _affichage(utilisateur):
    if utilisateur is None:
        return None
    identite = utilisateur.get("nom") or utilisateur.get("email")
    if not identite:
        return None
    role = utilisateur.get("role")
    return f"{identite} ({role})" if role else identite


@given(parsers.parse('qu\'un utilisateur est connecté avec le nom "{nom}"'))
def utilisateur_connecte_avec_nom(contexte, nom):
    contexte["utilisateur"] = {"nom": nom, "email": None, "role": None}


@given(parsers.parse('que son rôle est "{role}"'))
def role_utilisateur(contexte, role):
    contexte["utilisateur"]["role"] = role


@given(parsers.parse('que son email est "{email}"'))
def email_utilisateur(contexte, email):
    contexte["utilisateur"]["email"] = email


@given("qu'un utilisateur est connecté sans nom")
def utilisateur_connecte_sans_nom(contexte):
    contexte["utilisateur"] = {"nom": None, "email": None, "role": None}


@given("qu'aucun utilisateur n'est connecté")
def aucun_utilisateur_connecte(contexte):
    contexte["utilisateur"] = None


@then(parsers.parse('le menu déroulant affiche "{texte_attendu}"'))
def menu_affiche_texte(contexte, texte_attendu):
    resultat = _affichage(contexte["utilisateur"])
    assert resultat == texte_attendu, (
        f"Affichage attendu : '{texte_attendu}', mais obtenu : '{resultat}'"
    )


@then("le menu déroulant n'affiche aucune identité")
def menu_n_affiche_aucune_identite(contexte):
    resultat = _affichage(contexte["utilisateur"])
    assert resultat is None or resultat == "", (
        f"Aucune identité attendue, mais obtenu : '{resultat}'"
    )
