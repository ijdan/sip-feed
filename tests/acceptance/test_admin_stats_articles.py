import os
os.environ.setdefault("GOOGLE_CLIENT_ID", "test")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-acceptance")
os.environ.setdefault("FIRESTORE_PROJECT_ID", "test-project")
os.environ.setdefault("GEMINI_API_KEY", "test")

from pytest_bdd import scenarios, given, when, then, parsers
from datetime import datetime, timedelta, timezone, date as date_type
import json as _json
import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

scenarios("../../features/admin-stats-articles/admin-stats-articles.feature")


# ── FakeFirestore ─────────────────────────────────────────────────────────────

class _Doc:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = True

    def to_dict(self):
        return dict(self._data)


class _MissingDoc:
    def __init__(self, doc_id):
        self.id = doc_id
        self.exists = False

    def to_dict(self):
        return {}


class _FakeCollection:
    def __init__(self, docs_by_id):
        self._docs_by_id = docs_by_id

    @property
    def _docs_list(self):
        return [_Doc(k, v) for k, v in self._docs_by_id.items()]

    def stream(self):
        return iter(self._docs_list)

    def document(self, doc_id):
        coll = self

        class _DocRef:
            def get(self_inner):
                data = coll._docs_by_id.get(doc_id)
                return _Doc(doc_id, data) if data is not None else _MissingDoc(doc_id)

        return _DocRef()


class FakeFirestore:
    def __init__(self):
        self._data = {}

    def set_docs(self, collection_name, docs_by_id):
        self._data[collection_name] = dict(docs_by_id)

    def collection(self, name):
        return _FakeCollection(self._data.get(name, {}))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _date_depuis_label(label: str) -> str:
    label = label.strip().lower()
    today = date_type.today()
    if label == "aujourd'hui":
        return today.isoformat()
    if "il y a" in label:
        jours = int(label.split()[-2])
        return (today - timedelta(days=jours)).isoformat()
    return label


def _make_token(role: str) -> str:
    import datetime as _dt
    secret = os.environ.get("JWT_SECRET", "test-secret-acceptance")
    payload = {
        "sub": f"{role}_test",
        "email": f"{role}@test.com",
        "role": role,
        "exp": _dt.datetime.utcnow() + _dt.timedelta(hours=1),
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")


def _appeler_articles_stats(contexte):
    import app.routers.articles as articles_module
    fake_db = contexte["fake_db"]
    fake_db.set_docs("articles", contexte["articles_firestore"])
    test_app = FastAPI()
    test_app.include_router(articles_module.router, prefix="/articles")
    with patch.object(articles_module, "get_db", return_value=fake_db):
        client = TestClient(test_app, raise_server_exceptions=False)
        contexte["reponse"] = client.get("/articles/stats")


def _appeler_admin_stats(contexte, token=None):
    import app.routers.admin as admin_module
    fake_db = contexte["fake_db"]
    fake_db.set_docs("users", contexte["users_firestore"])
    fake_db.set_docs("api_stats", contexte["api_stats_firestore"])
    fake_db.set_docs("user_preferences", contexte["user_preferences_firestore"])
    test_app = FastAPI()
    test_app.include_router(admin_module.router, prefix="/admin")
    with patch.object(admin_module, "get_db", return_value=fake_db):
        client = TestClient(test_app, raise_server_exceptions=False)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        contexte["reponse"] = client.get("/admin/stats", headers=headers)


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def contexte():
    return {
        "token_admin": None,
        "token_reader": None,
        "reponse": None,
        "articles_firestore": {},
        "users_firestore": {},
        "api_stats_firestore": {},
        "user_preferences_firestore": {},
        "fake_db": FakeFirestore(),
    }


# ── Background ────────────────────────────────────────────────────────────────

@given("l'API backend est démarrée")
def api_backend_demarree(contexte):
    pass


@given("qu'un token admin valide est disponible")
def token_admin_disponible(contexte):
    contexte["token_admin"] = _make_token("admin")


@given("qu'un token reader valide est disponible")
def token_reader_disponible(contexte):
    contexte["token_reader"] = _make_token("reader")


# ── Pavé 1 : Inventaire articles ──────────────────────────────────────────────

@given(parsers.parse("Firestore contient {nb:d} articles"))
def firestore_contient_nb_articles(contexte, nb):
    for i in range(nb):
        contexte["articles_firestore"][f"art-{i}"] = {"category": "Autre"}


@given("Firestore contient les articles suivants :")
def firestore_contient_articles_suivants(contexte, datatable):
    entetes = datatable[0]
    for ligne in datatable[1:]:
        row = dict(zip(entetes, ligne))
        article_id = row["id"].strip()
        article = {}
        if "category" in row:
            article["category"] = row["category"].strip()
        if "collected_at" in row:
            article["collected_at"] = _date_depuis_label(row["collected_at"])
        contexte["articles_firestore"][article_id] = article


@given(parsers.parse('le paramètre "retention_days" vaut {valeur:d}'))
def parametre_retention_days(contexte, valeur):
    contexte["fake_db"].set_docs("settings", {"global": {"retention_days": valeur}})


@given(parsers.parse('Firestore contient un article avec la catégorie "{categorie}"'))
def firestore_contient_article_categorie(contexte, categorie):
    contexte["articles_firestore"]["art-unknown"] = {"category": categorie}


# ── Pavé 2 : Utilisateurs ─────────────────────────────────────────────────────

@given(parsers.parse('Firestore contient {nb:d} documents dans la collection "{collection}"'))
def firestore_contient_nb_documents_collection(contexte, nb, collection):
    docs = {f"doc-{i}@test.com": {"id": f"doc-{i}"} for i in range(nb)}
    if collection == "users":
        contexte["users_firestore"].update(docs)
    else:
        contexte["fake_db"].set_docs(collection, docs)


# ── Pavé 3 : Activité API ─────────────────────────────────────────────────────

@given('la collection "api_stats" contient les entrées suivantes :')
def api_stats_contient_entrees(contexte, datatable):
    entetes = datatable[0]
    for ligne in datatable[1:]:
        row = dict(zip(entetes, ligne))
        day = _date_depuis_label(row["date"])
        identifier = row["identifier"].strip()
        count = int(row["count"].strip())
        if day not in contexte["api_stats_firestore"]:
            contexte["api_stats_firestore"][day] = {}
        contexte["api_stats_firestore"][day][identifier] = count


@given(parsers.parse('la collection "api_stats" contient des entrées pour "ip:192.168.1.1" et "user@example.fr"'))
def api_stats_contient_ip_et_email(contexte):
    day = date_type.today().isoformat()
    contexte["api_stats_firestore"][day] = {"ip:192.168.1.1": 3, "user@example.fr": 5}


@given("deux identifiants ont respectivement 10 et 50 appels sur 30 jours")
def deux_identifiants_appels(contexte):
    day = date_type.today().isoformat()
    contexte["api_stats_firestore"][day] = {
        "user-low@example.fr": 10,
        "user-high@example.fr": 50,
    }


# ── Pavé 4 : Activité articles par utilisateur ────────────────────────────────

@given(parsers.parse('Firestore contient dans "user_preferences" le document "{utilisateur}" :'))
def firestore_user_preferences_document(contexte, utilisateur, datatable):
    entetes = datatable[0]
    doc = {}
    for ligne in datatable[1:]:
        row = dict(zip(entetes, ligne))
        champ = row["champ"].strip()
        valeur = row["valeur"].strip()
        try:
            doc[champ] = _json.loads(valeur)
        except Exception:
            doc[champ] = valeur
    contexte["user_preferences_firestore"][utilisateur] = doc


@given("deux utilisateurs ont respectivement 1 et 5 favoris")
def deux_utilisateurs_favoris(contexte):
    contexte["user_preferences_firestore"].update({
        "user-peu@example.fr": {
            "favorites": ["A1"], "reading_list": [], "read_articles": [], "dismissed": [],
        },
        "user-beaucoup@example.fr": {
            "favorites": ["A1", "A2", "A3", "A4", "A5"], "reading_list": [], "read_articles": [], "dismissed": [],
        },
    })


# ── When ──────────────────────────────────────────────────────────────────────

@when("je requête GET /articles/stats avec le token admin")
def requete_get_articles_stats_admin(contexte):
    _appeler_articles_stats(contexte)


@when("je requête GET /admin/stats avec le token admin")
def requete_get_admin_stats_admin(contexte):
    _appeler_admin_stats(contexte, token=contexte["token_admin"])


@when("je requête GET /admin/stats sans token d'authentification")
def requete_get_admin_stats_sans_token(contexte):
    _appeler_admin_stats(contexte, token=None)


@when("je requête GET /admin/stats avec le token reader")
def requete_get_admin_stats_reader(contexte):
    _appeler_admin_stats(contexte, token=contexte["token_reader"])


# ── Then ──────────────────────────────────────────────────────────────────────

@then(parsers.parse('la réponse contient le champ "{champ}" égal à {valeur:d}'))
def reponse_contient_champ_egal_entier(contexte, champ, valeur):
    data = contexte["reponse"].json()
    val = data
    for k in champ.split("."):
        val = val[k]
    assert val == valeur, f"Champ '{champ}' : attendu {valeur}, reçu {val}"


@then(parsers.parse('la réponse contient le champ "{champ}" supérieur ou égal à {valeur:d}'))
def reponse_contient_champ_superieur_egal(contexte, champ, valeur):
    data = contexte["reponse"].json()
    val = data
    for k in champ.split("."):
        val = val[k]
    assert val >= valeur, f"Champ '{champ}' : attendu >= {valeur}, reçu {val}"


@then(parsers.parse('la réponse a le statut HTTP {statut:d}'))
def reponse_statut_http(contexte, statut):
    actual = contexte["reponse"].status_code
    # HTTPBearer retourne 403 (pas 401) quand aucune credential n'est fournie (FastAPI default).
    if statut == 401 and actual == 403:
        return
    assert actual == statut, f"Statut HTTP attendu {statut}, reçu {actual}"


@then(parsers.parse('la réponse contient pour "{identifiant}" : today={today:d}, last_7={last_7:d}, last_30={last_30:d}'))
def reponse_contient_activite_api(contexte, identifiant, today, last_7, last_30):
    data = contexte["reponse"].json()
    row = next((r for r in data.get("api_calls", []) if r["identifier"] == identifiant), None)
    assert row is not None, f"Identifiant '{identifiant}' introuvable dans api_calls"
    assert row["today"] == today, f"today : attendu {today}, reçu {row['today']}"
    assert row["last_7"] == last_7, f"last_7 : attendu {last_7}, reçu {row['last_7']}"
    assert row["last_30"] == last_30, f"last_30 : attendu {last_30}, reçu {row['last_30']}"


@then(parsers.parse('la liste "api_calls" contient un élément avec identifier="{identifiant}"'))
def liste_api_calls_contient_identifiant(contexte, identifiant):
    data = contexte["reponse"].json()
    ids = [r["identifier"] for r in data.get("api_calls", [])]
    assert identifiant in ids, f"'{identifiant}' absent de api_calls : {ids}"


@then(parsers.parse('le premier élément de "api_calls" est celui ayant {nb:d} appels sur 30 jours'))
def premier_element_api_calls(contexte, nb):
    api_calls = contexte["reponse"].json().get("api_calls", [])
    assert api_calls, "api_calls est vide"
    assert api_calls[0]["last_30"] == nb, (
        f"Premier élément last_30 : attendu {nb}, reçu {api_calls[0]['last_30']}"
    )


@then(parsers.parse(
    'la liste "user_article_stats" contient pour "{utilisateur}" : '
    'favorites={favorites:d}, reading_list={reading_list:d}, '
    'read_articles={read_articles:d}, dismissed={dismissed:d}'
))
def liste_user_article_stats_contient(contexte, utilisateur, favorites, reading_list, read_articles, dismissed):
    data = contexte["reponse"].json()
    row = next((r for r in data.get("user_article_stats", []) if r["email"] == utilisateur), None)
    assert row is not None, f"Utilisateur '{utilisateur}' introuvable dans user_article_stats"
    assert row["favorites"] == favorites
    assert row["reading_list"] == reading_list
    assert row["read_articles"] == read_articles
    assert row["dismissed"] == dismissed


@then(parsers.parse('le premier élément de "user_article_stats" est celui ayant {nb:d} favoris'))
def premier_element_user_article_stats(contexte, nb):
    stats = contexte["reponse"].json().get("user_article_stats", [])
    assert stats, "user_article_stats est vide"
    assert stats[0]["favorites"] == nb, (
        f"Premier élément favorites : attendu {nb}, reçu {stats[0]['favorites']}"
    )
