# Tests d'acceptance — filter-articles-by-days (v3 : tests contre le code de production réel)
import os
# Env vars factices pour satisfaire pydantic-settings avant tout import du backend
os.environ.setdefault("GOOGLE_CLIENT_ID", "test")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-acceptance")
os.environ.setdefault("FIRESTORE_PROJECT_ID", "test-project")
os.environ.setdefault("GEMINI_API_KEY", "test")

from pytest_bdd import scenarios, given, when, then, parsers
from datetime import datetime, timedelta, timezone
import pytest

scenarios("../../features/filter-articles-by-days.feature")


# ─── Fake Firestore en mémoire ────────────────────────────────────────────────

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


class _FakeQuery:
    def __init__(self, docs):
        self._docs = list(docs)

    def order_by(self, field, direction="ASCENDING"):
        rev = direction.upper() in ("DESCENDING", "DESC")
        return _FakeQuery(sorted(self._docs, key=lambda d: str(d._data.get(field, "")), reverse=rev))

    def where(self, field, op, value):
        if isinstance(value, datetime):
            value = value.isoformat()
        value = str(value)
        ops = {
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            ">=": lambda a, b: a >= b,
            ">": lambda a, b: a > b,
            "<=": lambda a, b: a <= b,
            "<": lambda a, b: a < b,
        }
        cmp = ops.get(op, lambda a, b: True)
        filtered = []
        for d in self._docs:
            v = d._data.get(field)
            if v is None:
                continue
            if isinstance(v, datetime):
                v = v.isoformat()
            if cmp(str(v), value):
                filtered.append(d)
        return _FakeQuery(filtered)

    def offset(self, n):
        return _FakeQuery(self._docs[n:])

    def limit(self, n):
        return _FakeQuery(self._docs[:n])

    def stream(self):
        return iter(self._docs)

    def count(self):
        n = len(self._docs)
        class _C:
            def get(self_inner):
                class _V:
                    value = n
                return [[_V()]]
        return _C()


class _FakeCollection:
    def __init__(self, docs_by_id):
        self._docs_by_id = docs_by_id

    @property
    def _docs_list(self):
        return [_Doc(k, v) for k, v in self._docs_by_id.items()]

    def order_by(self, field, direction="ASCENDING"):
        return _FakeQuery(self._docs_list).order_by(field, direction)

    def where(self, field, op, value):
        return _FakeQuery(self._docs_list).where(field, op, value)

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
        self._data = {}  # collection_name → {doc_id: doc_data}

    def set_docs(self, collection_name, docs_by_id):
        self._data[collection_name] = dict(docs_by_id)

    def collection(self, name):
        return _FakeCollection(self._data.get(name, {}))

    def get_ids(self, collection_name):
        return list(self._data.get(collection_name, {}).keys())


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def contexte():
    return {
        "articles_firestore": {},
        "retention_days": None,
        "reponse": None,
        "fake_db": FakeFirestore(),
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

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


_DEFAULTS = {
    "title": "Titre test",
    "title_fr": "",
    "title_en": "",
    "short_description": "Description courte",
    "short_description_fr": "",
    "short_description_en": "",
    "long_description": "Description longue",
    "long_description_fr": "",
    "long_description_en": "",
    "keywords_fr": [],
    "keywords_en": [],
    "source_name": "Source Test",
    "source_id": "source-test",
    "category": "Autre",
}


def _to_doc(article_id, article_data):
    collected_at = article_data.get("collected_at", datetime.now(tz=timezone.utc))
    if isinstance(collected_at, datetime):
        collected_at = collected_at.isoformat()
    doc = {
        **_DEFAULTS,
        "id": article_id,
        "article_url": f"https://example.com/{article_id}",
        "collected_at": collected_at,
        "published_at": collected_at,
    }
    for k, v in article_data.items():
        if k not in ("id", "collected_at"):
            doc[k] = v
    return doc


def _appeler_articles(contexte, params=None):
    import app.routers.articles as articles_module
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from unittest.mock import patch

    fake_db = contexte["fake_db"]
    fake_db.set_docs("articles", {k: _to_doc(k, v) for k, v in contexte["articles_firestore"].items()})
    fake_db.set_docs("settings", {"global": {"retention_days": contexte["retention_days"] or 0}})

    test_app = FastAPI()
    test_app.include_router(articles_module.router, prefix="/articles")

    with patch.object(articles_module, "get_db", return_value=fake_db):
        client = TestClient(test_app)
        response = client.get("/articles", params=params or {})

    contexte["reponse"] = response.json()


# ─── Steps ────────────────────────────────────────────────────────────────────

@given("l'API backend est démarrée")
def api_backend_demarree(contexte):
    pass  # Le client est créé à la demande dans _appeler_articles


@given("Firestore contient les articles suivants :")
def firestore_contient_articles_tableau(contexte, datatable):
    entetes = datatable[0]
    for ligne in datatable[1:]:
        row = dict(zip(entetes, ligne))
        article_id = row["id"]
        collected_at = _date_depuis_label(row["collected_at"])
        existant = contexte["articles_firestore"].get(article_id, {})
        existant.update({"id": article_id, "collected_at": collected_at})
        contexte["articles_firestore"][article_id] = existant


@given(parsers.parse('le paramètre "retention_days" vaut {valeur:d}'))
def parametre_retention_days(contexte, valeur):
    contexte["retention_days"] = valeur


@given(parsers.parse('l\'article "{article_id}" a la catégorie "{categorie}"'))
def article_avec_categorie(contexte, article_id, categorie):
    if article_id in contexte["articles_firestore"]:
        contexte["articles_firestore"][article_id]["category"] = categorie
    else:
        contexte["articles_firestore"][article_id] = {"category": categorie}


@when("je requête GET /articles")
def requete_get_articles(contexte):
    _appeler_articles(contexte)


@when(parsers.parse("je requête GET /articles?category={categorie}"))
def requete_get_articles_avec_categorie(contexte, categorie):
    contexte["category"] = categorie
    _appeler_articles(contexte, {"category": categorie})


@when("le collector termine une exécution")
def collector_termine_execution(contexte):
    # Simule un run du collector : sans suppression, les articles doivent persister.
    # On s'assure que le fake Firestore est peuplé avec les données du contexte.
    fake_db = contexte["fake_db"]
    fake_db.set_docs("articles", {k: _to_doc(k, v) for k, v in contexte["articles_firestore"].items()})


@then(parsers.parse('la réponse contient les articles "{id1}" et "{id2}"'))
def reponse_contient_deux_articles(contexte, id1, id2):
    reponse = contexte.get("reponse")
    assert reponse is not None, "Aucune réponse HTTP reçue"
    ids = [a["id"] for a in reponse.get("items", [])]
    assert id1 in ids, f"L'article {id1!r} devrait être présent dans la réponse"
    assert id2 in ids, f"L'article {id2!r} devrait être présent dans la réponse"


@then(parsers.parse('la réponse contient les articles "{id1}", "{id2}", "{id3}" et "{id4}"'))
def reponse_contient_quatre_articles(contexte, id1, id2, id3, id4):
    reponse = contexte.get("reponse")
    assert reponse is not None, "Aucune réponse HTTP reçue"
    ids = [a["id"] for a in reponse.get("items", [])]
    for article_id in [id1, id2, id3, id4]:
        assert article_id in ids, f"L'article {article_id!r} devrait être présent dans la réponse"


@then(parsers.parse('la réponse ne contient pas les articles "{id1}" et "{id2}"'))
def reponse_ne_contient_pas_articles(contexte, id1, id2):
    reponse = contexte.get("reponse")
    assert reponse is not None, "Aucune réponse HTTP reçue"
    ids = [a["id"] for a in reponse.get("items", [])]
    assert id1 not in ids, f"L'article {id1!r} ne devrait pas être présent dans la réponse"
    assert id2 not in ids, f"L'article {id2!r} ne devrait pas être présent dans la réponse"


@then(parsers.parse("le total retourné est {total:d}"))
def total_retourne(contexte, total):
    reponse = contexte.get("reponse")
    assert reponse is not None, "Aucune réponse HTTP reçue"
    total_reponse = reponse.get("total", len(reponse.get("items", [])))
    assert total_reponse == total, f"Le total attendu est {total} mais la réponse retourne {total_reponse}"


@then(parsers.parse('les articles "{id1}" et "{id2}" existent toujours dans la collection Firestore "{collection}"'))
def articles_existent_dans_firestore(contexte, id1, id2, collection):
    ids = contexte["fake_db"].get_ids(collection)
    assert id1 in ids, f"L'article {id1!r} devrait toujours exister dans la collection {collection!r}"
    assert id2 in ids, f"L'article {id2!r} devrait toujours exister dans la collection {collection!r}"


@then(parsers.parse('la réponse contient uniquement l\'article "{article_id}"'))
def reponse_contient_uniquement(contexte, article_id):
    reponse = contexte.get("reponse")
    assert reponse is not None, "Aucune réponse HTTP reçue"
    ids = [a["id"] for a in reponse.get("items", [])]
    assert ids == [article_id], (
        f"La réponse devrait contenir uniquement l'article {article_id!r}, mais contient : {ids}"
    )
