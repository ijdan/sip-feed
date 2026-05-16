from pytest_bdd import scenarios, given, when, then, parsers
from datetime import datetime, timedelta, timezone
import pytest

scenarios("../../features/filter-articles-by-days.feature")


@pytest.fixture
def contexte():
    return {
        "articles_firestore": {},
        "retention_days": None,
        "reponse": None,
        "category": None,
    }


def _date_depuis_label(label: str) -> datetime:
    now = datetime.now(tz=timezone.utc)
    label = label.strip().lower()
    if label == "aujourd'hui":
        return now
    elif label.startswith("il y a"):
        parts = label.split()
        jours = int(parts[3])
        return now - timedelta(days=jours)
    raise ValueError(f"Label de date non reconnu : {label!r}")


@given("que l'API backend est démarrée")
def api_backend_demarree(contexte):
    raise NotImplementedError("L'implémentation applicative est à fournir")


@given(parsers.parse("que Firestore contient les articles suivants :\n{table}"))
def firestore_contient_articles(contexte, table):
    raise NotImplementedError("L'implémentation applicative est à fournir")


@given("que Firestore contient les articles suivants :")
def firestore_contient_articles_tableau(contexte):
    raise NotImplementedError("L'implémentation applicative est à fournir")


@given(parsers.parse('que le paramètre "retention_days" vaut {valeur:d}'))
def parametre_retention_days(contexte, valeur):
    contexte["retention_days"] = valeur


@given(parsers.parse('que l\'article "{article_id}" a la catégorie "{categorie}"'))
def article_avec_categorie(contexte, article_id, categorie):
    if article_id in contexte["articles_firestore"]:
        contexte["articles_firestore"][article_id]["category"] = categorie
    else:
        contexte["articles_firestore"][article_id] = {"category": categorie}


@when("je requête GET /articles")
def requete_get_articles(contexte):
    raise NotImplementedError("L'implémentation applicative est à fournir")


@when(parsers.parse("je requête GET /articles?category={categorie}"))
def requete_get_articles_avec_categorie(contexte, categorie):
    contexte["category"] = categorie
    raise NotImplementedError("L'implémentation applicative est à fournir")


@when("le collector termine une exécution")
def collector_termine_execution(contexte):
    raise NotImplementedError("L'implémentation applicative est à fournir")


@then(parsers.parse('la réponse contient les articles "{id1}" et "{id2}"'))
def reponse_contient_deux_articles(contexte, id1, id2):
    reponse = contexte.get("reponse")
    if reponse is None:
        raise NotImplementedError("L'implémentation applicative est à fournir")
    ids = [article["id"] for article in reponse.get("articles", [])]
    assert id1 in ids, f"L'article {id1!r} devrait être présent dans la réponse"
    assert id2 in ids, f"L'article {id2!r} devrait être présent dans la réponse"


@then(parsers.parse('la réponse contient les articles "{id1}", "{id2}", "{id3}" et "{id4}"'))
def reponse_contient_quatre_articles(contexte, id1, id2, id3, id4):
    reponse = contexte.get("reponse")
    if reponse is None:
        raise NotImplementedError("L'implémentation applicative est à fournir")
    ids = [article["id"] for article in reponse.get("articles", [])]
    for article_id in [id1, id2, id3, id4]:
        assert article_id in ids, f"L'article {article_id!r} devrait être présent dans la réponse"


@then(parsers.parse('la réponse ne contient pas les articles "{id1}" et "{id2}"'))
def reponse_ne_contient_pas_articles(contexte, id1, id2):
    reponse = contexte.get("reponse")
    if reponse is None:
        raise NotImplementedError("L'implémentation applicative est à fournir")
    ids = [article["id"] for article in reponse.get("articles", [])]
    assert id1 not in ids, f"L'article {id1!r} ne devrait pas être présent dans la réponse"
    assert id2 not in ids, f"L'article {id2!r} ne devrait pas être présent dans la réponse"


@then(parsers.parse("le total retourné est {total:d}"))
def total_retourne(contexte, total):
    reponse = contexte.get("reponse")
    if reponse is None:
        raise NotImplementedError("L'implémentation applicative est à fournir")
    total_reponse = reponse.get("total", len(reponse.get("articles", [])))
    assert total_reponse == total, (
        f"Le total attendu est {total} mais la réponse retourne {total_reponse}"
    )


@then(parsers.parse('les articles "{id1}" et "{id2}" existent toujours dans la collection Firestore "{collection}"'))
def articles_existent_dans_firestore(contexte, id1, id2, collection):
    raise NotImplementedError("L'implémentation applicative est à fournir")


@then(parsers.parse('la réponse contient uniquement l\'article "{article_id}"'))
def reponse_contient_uniquement(contexte, article_id):
    reponse = contexte.get("reponse")
    if reponse is None:
        raise NotImplementedError("L'implémentation applicative est à fournir")
    articles = reponse.get("articles", [])
    ids = [article["id"] for article in articles]
    assert ids == [article_id], (
        f"La réponse devrait contenir uniquement l'article {article_id!r}, "
        f"mais contient : {ids}"
    )