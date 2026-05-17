import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from unittest.mock import MagicMock, patch
import requests
import sys
import os
from datetime import datetime, timedelta, timezone

scenarios("../../features/admin-stats-articles/admin-stats-articles.feature")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def contexte():
    return {
        "token_admin": None,
        "token_reader": None,
        "token_courant": None,
        "reponse": None,
        "firestore_articles": [],
        "firestore_users": [],
        "firestore_api_stats": [],
        "firestore_user_preferences": {},
        "retention_days": None,
        "base_url": "http://localhost:8000",
    }


# ── Contexte commun ───────────────────────────────────────────────────────────

@given("l'API backend est démarrée")
def api_backend_demarree(contexte):
    raise NotImplementedError("Vérifier que l'API backend est démarrée")


@given("qu'un token admin valide est disponible")
def token_admin_disponible(contexte):
    raise NotImplementedError("Obtenir un token admin valide")


@given("qu'un token reader valide est disponible")
def token_reader_disponible(contexte):
    raise NotImplementedError("Obtenir un token reader valide")


# ── Pavé 1 : Inventaire des articles ──────────────────────────────────────────

@given(parsers.parse("Firestore contient {nb:d} articles"))
def firestore_contient_nb_articles(contexte, nb):
    raise NotImplementedError(f"Insérer {nb} articles dans Firestore")


@given("Firestore contient les articles suivants :")
def firestore_contient_articles_suivants(contexte, datatable):
    raise NotImplementedError("Insérer les articles du tableau dans Firestore")


@given(parsers.parse('le paramètre "retention_days" vaut {valeur:d}'))
def parametre_retention_days(contexte, valeur):
    raise NotImplementedError(f"Configurer retention_days à {valeur}")


@given(parsers.parse('Firestore contient un article avec la catégorie "{categorie}"'))
def firestore_contient_article_categorie(contexte, categorie):
    raise NotImplementedError(f"Insérer un article avec la catégorie '{categorie}' dans Firestore")


# ── Pavé 2 : Utilisateurs ─────────────────────────────────────────────────────

@given(parsers.parse('Firestore contient {nb:d} documents dans la collection "{collection}"'))
def firestore_contient_nb_documents_collection(contexte, nb, collection):
    raise NotImplementedError(f"Insérer {nb} documents dans la collection '{collection}'")


# ── Pavé 3 : Activité API ─────────────────────────────────────────────────────

@given("la collection \"api_stats\" contient les entrées suivantes :")
def api_stats_contient_entrees(contexte, datatable):
    raise NotImplementedError("Insérer les entrées api_stats du tableau dans Firestore")


@given(parsers.parse('la collection "api_stats" contient des entrées pour "ip:192.168.1.1" et "user@example.fr"'))
def api_stats_contient_ip_et_email(contexte):
    raise NotImplementedError("Insérer des entrées api_stats pour ip:192.168.1.1 et user@example.fr")


@given("deux identifiants ont respectivement 10 et 50 appels sur 30 jours")
def deux_identifiants_appels(contexte):
    raise NotImplementedError("Insérer deux identifiants avec 10 et 50 appels sur 30 jours")


# ── Pavé 4 : Activité articles par utilisateur ────────────────────────────────

@given(parsers.parse('Firestore contient dans "user_preferences" le document "{utilisateur}" :'))
def firestore_user_preferences_document(contexte, utilisateur, datatable):
    raise NotImplementedError(f"Insérer le document user_preferences pour '{utilisateur}'")


@given("deux utilisateurs ont respectivement 1 et 5 favoris")
def deux_utilisateurs_favoris(contexte):
    raise NotImplementedError("Insérer deux utilisateurs avec 1 et 5 favoris")


# ── When ──────────────────────────────────────────────────────────────────────

@when("je requête GET /articles/stats avec le token admin")
def requete_get_articles_stats_admin(contexte):
    raise NotImplementedError("Effectuer GET /articles/stats avec le token admin")


@when("je requête GET /articles/stats sans token d'authentification")
def requete_get_articles_stats_sans_token(contexte):
    raise NotImplementedError("Effectuer GET /articles/stats sans token d'authentification")


@when("je requête GET /admin/stats avec le token admin")
def requete_get_admin_stats_admin(contexte):
    raise NotImplementedError("Effectuer GET /admin/stats avec le token admin")


@when("je requête GET /admin/stats sans token d'authentification")
def requete_get_admin_stats_sans_token(contexte):
    raise NotImplementedError("Effectuer GET /admin/stats sans token d'authentification")


@when("je requête GET /admin/stats avec le token reader")
def requete_get_admin_stats_reader(contexte):
    raise NotImplementedError("Effectuer GET /admin/stats avec le token reader")


# ── Then ──────────────────────────────────────────────────────────────────────

@then(parsers.parse('la réponse contient le champ "{champ}" égal à {valeur:d}'))
def reponse_contient_champ_egal_entier(contexte, champ, valeur):
    raise NotImplementedError(f"Vérifier que la réponse contient le champ '{champ}' égal à {valeur}")


@then(parsers.parse('la réponse contient le champ "{champ}" supérieur ou égal à {valeur:d}'))
def reponse_contient_champ_superieur_egal(contexte, champ, valeur):
    raise NotImplementedError(f"Vérifier que la réponse contient le champ '{champ}' >= {valeur}")


@then(parsers.parse('la réponse a le statut HTTP {statut:d}'))
def reponse_statut_http(contexte, statut):
    raise NotImplementedError(f"Vérifier que la réponse a le statut HTTP {statut}")


@then(parsers.parse('la réponse contient pour "{identifiant}" : today={today:d}, last_7={last_7:d}, last_30={last_30:d}'))
def reponse_contient_activite_api(contexte, identifiant, today, last_7, last_30):
    raise NotImplementedError(
        f"Vérifier l'activité API pour '{identifiant}' : today={today}, last_7={last_7}, last_30={last_30}"
    )


@then(parsers.parse('la liste "api_calls" contient un élément avec identifier="{identifiant}"'))
def liste_api_calls_contient_identifiant(contexte, identifiant):
    raise NotImplementedError(f"Vérifier que api_calls contient un élément avec identifier='{identifiant}'")


@then(parsers.parse('le premier élément de "api_calls" est celui ayant {nb:d} appels sur 30 jours'))
def premier_element_api_calls(contexte, nb):
    raise NotImplementedError(f"Vérifier que le premier élément de api_calls a {nb} appels sur 30 jours")


@then(parsers.parse('la liste "user_article_stats" contient pour "{utilisateur}" : favorites={favorites:d}, reading_list={reading_list:d}, read_articles={read_articles:d}, dismissed={dismissed:d}'))
def liste_user_article_stats_contient(contexte, utilisateur, favorites, reading_list, read_articles, dismissed):
    raise NotImplementedError(
        f"Vérifier user_article_stats pour '{utilisateur}' : "
        f"favorites={favorites}, reading_list={reading_list}, "
        f"read_articles={read_articles}, dismissed={dismissed}"
    )


@then(parsers.parse('le premier élément de "user_article_stats" est celui ayant {nb:d} favoris'))
def premier_element_user_article_stats(contexte, nb):
    raise NotImplementedError(f"Vérifier que le premier élément de user_article_stats a {nb} favoris")