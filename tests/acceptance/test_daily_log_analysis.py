import pytest
from pytest_bdd import scenarios, given, when, then, parsers

scenarios("../../features/daily-log-analysis.feature")


# ---------------------------------------------------------------------------
# Fixtures partagées
# ---------------------------------------------------------------------------

@pytest.fixture
def contexte():
    """Dictionnaire d'état partagé entre les steps."""
    return {}


# ---------------------------------------------------------------------------
# Contexte global (Background)
# ---------------------------------------------------------------------------

@given("l'API backend est démarrée")
def api_backend_demarree(contexte):
    raise NotImplementedError("L'API backend doit être démarrée")


@given("Firestore est disponible")
def firestore_disponible(contexte):
    raise NotImplementedError("Firestore doit être disponible")


# ---------------------------------------------------------------------------
# US-DLA-002 : collecte des logs
# ---------------------------------------------------------------------------

@given("que Cloud Logging contient les entrées suivantes sur les dernières 24h :")
def cloud_logging_contient_entrees(contexte, datatable):
    raise NotImplementedError("Configurer Cloud Logging avec les entrées du tableau")


@when("le job log-analyzer collecte les logs")
def job_log_analyzer_collecte_logs(contexte):
    raise NotImplementedError("Exécuter la collecte des logs par le job log-analyzer")


@then(parsers.parse('les entrées collectées contiennent uniquement les entrées "{sev1}" et "{sev2}"'))
def entrees_collectees_contiennent_uniquement(contexte, sev1, sev2):
    raise NotImplementedError(f"Vérifier que seules les entrées {sev1} et {sev2} sont collectées")


@then(parsers.parse('l\'entrée "{severity}" n\'est pas collectée'))
def entree_non_collectee(contexte, severity):
    raise NotImplementedError(f"Vérifier que l'entrée {severity} n'est pas collectée")


@given("que Cloud Logging ne contient aucune entrée WARNING ou supérieure sur les dernières 24h")
def cloud_logging_aucune_entree_warning(contexte):
    raise NotImplementedError("Configurer Cloud Logging sans entrée WARNING ou supérieure")


@then(parsers.parse('le champ "{champ}" du rapport vaut {valeur:d}'))
def champ_rapport_vaut_entier(contexte, champ, valeur):
    raise NotImplementedError(f"Vérifier que le champ '{champ}' du rapport vaut {valeur}")


@then(parsers.parse('le champ "{champ}" du rapport est vide'))
def champ_rapport_est_vide(contexte, champ):
    raise NotImplementedError(f"Vérifier que le champ '{champ}' du rapport est vide")


@then(parsers.parse('le champ "{champ}" indique qu\'aucune anomalie n\'a été détectée'))
def champ_indique_aucune_anomalie(contexte, champ):
    raise NotImplementedError(f"Vérifier que le champ '{champ}' indique l'absence d'anomalie")


@given(parsers.parse("que Cloud Logging contient {nb_warning:d} entrées WARNING et {nb_error:d} entrées ERROR sur les dernières 24h"))
def cloud_logging_contient_warning_et_error(contexte, nb_warning, nb_error):
    raise NotImplementedError(f"Configurer Cloud Logging avec {nb_warning} WARNING et {nb_error} ERROR")


@then(parsers.parse("toutes les {nb:d} entrées ERROR sont incluses dans la collecte"))
def toutes_entrees_error_incluses(contexte, nb):
    raise NotImplementedError(f"Vérifier que les {nb} entrées ERROR sont toutes incluses")


@then(parsers.parse("le total collecté ne dépasse pas {max_entrees:d} entrées"))
def total_collecte_ne_depasse_pas(contexte, max_entrees):
    raise NotImplementedError(f"Vérifier que le total collecté ne dépasse pas {max_entrees}")


@then(parsers.parse('le champ "{champ}" mentionne que le volume a été tronqué'))
def champ_mentionne_volume_tronque(contexte, champ):
    raise NotImplementedError(f"Vérifier que le champ '{champ}' mentionne la troncature du volume")


# ---------------------------------------------------------------------------
# US-DLA-003 : analyse LLM
# ---------------------------------------------------------------------------

@given("que Cloud Logging contient des entrées ERROR sur les dernières 24h")
def cloud_logging_contient_erreurs(contexte):
    raise NotImplementedError("Configurer Cloud Logging avec des entrées ERROR")


@when("le job log-analyzer génère le rapport")
def job_log_analyzer_genere_rapport(contexte):
    raise NotImplementedError("Exécuter la génération du rapport par le job log-analyzer")


@then(parsers.parse('chaque item du rapport contient les champs "{c1}", "{c2}", "{c3}" et "{c4}"'))
def chaque_item_contient_champs(contexte, c1, c2, c3, c4):
    raise NotImplementedError(f"Vérifier que chaque item contient les champs {c1}, {c2}, {c3}, {c4}")


@then(parsers.parse('le champ "{champ}" de chaque item est l\'un de : "{v1}", "{v2}", "{v3}", "{v4}"'))
def champ_item_est_lun_de(contexte, champ, v1, v2, v3, v4):
    raise NotImplementedError(f"Vérifier que le champ '{champ}' est l'un de : {v1}, {v2}, {v3}, {v4}")


@then(parsers.parse("le nombre d'items ne dépasse pas {max_items:d}"))
def nombre_items_ne_depasse_pas(contexte, max_items):
    raise NotImplementedError(f"Vérifier que le nombre d'items ne dépasse pas {max_items}")


@given(parsers.parse('que le LLM retourne des items avec les priorités : "{p1}", "{p2}", "{p3}", "{p4}"'))
def llm_retourne_items_avec_priorites(contexte, p1, p2, p3, p4):
    raise NotImplementedError(f"Configurer le LLM pour retourner des items avec les priorités {p1}, {p2}, {p3}, {p4}")


@when("le rapport est stocké dans Firestore")
def rapport_stocke_dans_firestore(contexte):
    raise NotImplementedError("Stocker le rapport dans Firestore")


@then(parsers.parse('les items sont ordonnés : "{p1}" en premier, puis "{p2}", "{p3}", "{p4}"'))
def items_ordonnes_par_priorite(contexte, p1, p2, p3, p4):
    raise NotImplementedError(f"Vérifier l'ordre des items : {p1}, {p2}, {p3}, {p4}")


@given("que tous les modèles Gemini retournent une erreur de quota")
def tous_modeles_gemini_erreur_quota(contexte):
    raise NotImplementedError("Simuler une erreur de quota sur tous les modèles Gemini")


@when("le job log-analyzer tente de générer le rapport")
def job_log_analyzer_tente_generer_rapport(contexte):
    raise NotImplementedError("Tenter de générer le rapport avec les modèles Gemini indisponibles")


@then("le rapport est quand même écrit dans Firestore")
def rapport_ecrit_dans_firestore_malgre_erreur(contexte):
    raise NotImplementedError("Vérifier que le rapport est écrit dans Firestore même en cas d'erreur LLM")


@then(parsers.parse('le champ "{champ}" est vide'))
def champ_est_vide(contexte, champ):
    raise NotImplementedError(f"Vérifier que le champ '{champ}' est vide")


@then(parsers.parse('le champ "{champ}" contient le message d\'indisponibilité LLM'))
def champ_contient_message_indisponibilite_llm(contexte, champ):
    raise NotImplementedError(f"Vérifier que le champ '{champ}' contient le message d'indisponibilité LLM")


# ---------------------------------------------------------------------------
# US-DLA-004 : stockage Firestore
# ---------------------------------------------------------------------------

@given(parsers.parse("que le job s'exécute le {date_execution} à 05h00"))
def job_execute_a_date(contexte, date_execution):
    raise NotImplementedError(f"Configurer l'exécution du job à la date {date_execution}")


@given(parsers.parse("que la période couverte est le {date_couverte} (les 24h précédentes)"))
def periode_couverte(contexte, date_couverte):
    raise NotImplementedError(f"Configurer la période couverte : {date_couverte}")


@when("le rapport est généré avec succès")
def rapport_genere_avec_succes(contexte):
    raise NotImplementedError("Générer le rapport avec succès")


@then(parsers.parse('le document Firestore existe à la clé "{cle}"'))
def document_firestore_existe_a_cle(contexte, cle):
    raise NotImplementedError(f"Vérifier que le document Firestore existe à la clé '{cle}'")


@then(parsers.parse('le champ "{champ}" du document vaut "{valeur}"'))
def champ_document_vaut(contexte, champ, valeur):
    raise NotImplementedError(f"Vérifier que le champ '{champ}' du document vaut '{valeur}'")


@then(parsers.parse('le champ "{champ}" est renseigné'))
def champ_est_renseigne(contexte, champ):
    raise NotImplementedError(f"Vérifier que le champ '{champ}' est renseigné")


@given(parsers.parse('qu\'un rapport existe déjà dans Firestore à la clé "{cle}"'))
def rapport_existe_deja_firestore(contexte, cle):
    raise NotImplementedError(f"Créer un rapport existant dans Firestore à la clé '{cle}'")


@when("le job log-analyzer s'exécute à nouveau pour la même journée")
def job_log_analyzer_execute_a_nouveau(contexte):
    raise NotImplementedError("Exécuter à nouveau le job log-analyzer pour la même journée")


@then("aucun nouveau document n'est créé ou écrasé dans Firestore")
def aucun_nouveau_document_firestore(contexte):
    raise NotImplementedError("Vérifier qu'aucun nouveau document n'est créé ou écrasé dans Firestore")


@then("le job se termine normalement sans erreur")
def job_termine_normalement(contexte):
    raise NotImplementedError("Vérifier que le job se termine sans erreur")


# ---------------------------------------------------------------------------
# US-DLA-005 : endpoints backend
# ---------------------------------------------------------------------------

@given("qu'un rapport existe dans Firestore pour aujourd'hui")
def rapport_existe_firestore_aujourd_hui(contexte):
    raise NotImplementedError("Créer un rapport dans Firestore pour aujourd'hui")


@given("que l'utilisateur est authentifié en tant qu'admin")
def utilisateur_authentifie_admin(contexte):
    raise NotImplementedError("Authentifier l'utilisateur en tant qu'admin")


@when(parsers.parse("il requête GET {endpoint}"))
def requete_get(contexte, endpoint):
    raise NotImplementedError(f"Effectuer une requête GET sur {endpoint}")


@then(parsers.parse("la réponse a le statut {statut:d}"))
def reponse_statut(contexte, statut):
    raise NotImplementedError(f"Vérifier que la réponse a le statut {statut}")


@then(parsers.parse('la réponse contient les champs "{c1}", "{c2}", "{c3}", "{c4}" et "{c5}"'))
def reponse_contient_champs(contexte, c1, c2, c3, c4, c5):
    raise NotImplementedError(f"Vérifier que la réponse contient les champs {c1}, {c2}, {c3}, {c4}, {c5}")


@given(parsers.parse('qu\'aucun rapport n\'existe dans Firestore pour la date "{date}"'))
def aucun_rapport_firestore_pour_date(contexte, date):
    raise NotImplementedError(f"S'assurer qu'aucun rapport n'existe dans Firestore pour la date '{date}'")


@given("que l'utilisateur est authentifié en tant que reader")
def utilisateur_authentifie_reader(contexte):
    raise NotImplementedError("Authentifier l'utilisateur en tant que reader")


# ---------------------------------------------------------------------------
# US-DLA-006 : UI admin (non testés en pytest-bdd — implémentation frontend)
# ---------------------------------------------------------------------------

@given(parsers.parse('qu\'un utilisateur est connecté avec le rôle "{role}"'))
def utilisateur_connecte_avec_role(contexte, role):
    raise NotImplementedError(f"Connecter l'utilisateur avec le rôle '{role}'")


@when(parsers.parse('il navigue vers "{url}"'))
def utilisateur_navigue_vers(contexte, url):
    raise NotImplementedError(f"Naviguer vers '{url}'")


@then(parsers.parse('il est redirigé vers "{url}"'))
def utilisateur_redirige_vers(contexte, url):
    raise NotImplementedError(f"Vérifier la redirection vers '{url}'")


@given(parsers.parse('qu\'un rapport existe pour aujourd\'hui avec {nb_items:d} items et un résumé "{resume}"'))
def rapport_existe_avec_items_et_resume(contexte, nb_items, resume):
    raise NotImplementedError(f"Créer un rapport avec {nb_items} items et le résumé '{resume}'")


@then(parsers.parse('le résumé "{resume}" est affiché en haut de page'))
def resume_affiche_en_haut(contexte, resume):
    raise NotImplementedError(f"Vérifier que le résumé '{resume}' est affiché en haut de page")


@then(parsers.parse("{nb:d} cards d'items sont visibles"))
def cards_items_visibles(contexte, nb):
    raise NotImplementedError(f"Vérifier que {nb} cards d'items sont visibles")


@given(parsers.parse('qu\'un utilisateur admin consulte la page "{url}"'))
def utilisateur_admin_consulte_page(contexte, url):
    raise NotImplementedError(f"Un utilisateur admin consulte la page '{url}'")


@given("que le rapport contient un item CRITIQUE, un item HAUTE et un item BASSE")
def rapport_contient_items_critique_haute_basse(contexte):
    raise NotImplementedError("Créer un rapport avec un item CRITIQUE, HAUTE et BASSE")


@then("l'item CRITIQUE apparaît en premier avec un badge rouge")
def item_critique_en_premier_badge_rouge(contexte):
    raise NotImplementedError("Vérifier que l'item CRITIQUE apparaît en premier avec un badge rouge")


@then("l'item HAUTE apparaît en second avec un badge orange")
def item_haute_en_second_badge_orange(contexte):
    raise NotImplementedError("Vérifier que l'item HAUTE apparaît en second avec un badge orange")


@then("l'item BASSE apparaît en dernier avec un badge gris")