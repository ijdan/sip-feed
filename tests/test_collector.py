"""Tests fonctionnels — enrichissement articles (Gemini processor)."""
import os
import sys
import pytest
from pathlib import Path
from dotenv import load_dotenv

# Charger le .env du collector pour GEMINI_API_KEY
COLLECTOR_DIR = Path(__file__).resolve().parents[1] / "collector"
load_dotenv(COLLECTOR_DIR / ".env")

# Fournir une clé factice si absente (pour les tests avec mock)
if not os.environ.get("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = "AIza_TEST_KEY_FOR_UNIT_TESTS"

sys.path.insert(0, str(COLLECTOR_DIR))

CATEGORIES = ["IA", "DevOps", "Cloud", "Sécurité", "Dev", "IT", "Autre"]

SAMPLE_ARTICLES = [
    {
        "title": "Rust reaches 99% compatibility with Node.js",
        "raw_content": "The Bun JavaScript runtime has rewritten its core in Rust, achieving near-complete Node.js API compatibility.",
        "article_url": "https://example.com/rust-node",
        "source_name": "Hacker News",
        "source_id": "hn_test",
    },
    {
        "title": "Kubernetes v1.36 ships server-side sharding",
        "raw_content": "Kubernetes v1.36 introduces server-side sharded list and watch for improved scalability in large clusters.",
        "article_url": "https://example.com/k8s-136",
        "source_name": "TDLR",
        "source_id": "tldr_test",
    },
]


def test_save_raw_articles_structure():
    """Vérifie que save_raw_articles produit la bonne structure."""
    from processors.gemini_processor import save_raw_articles
    results = save_raw_articles(SAMPLE_ARTICLES)
    assert len(results) == 2
    for a in results:
        assert "id" in a
        assert "title" in a
        assert "article_url" in a
        assert "source_name" in a
        assert "category" in a
        assert a["category"] == "Autre"  # fallback sans LLM
        assert "keywords_fr" in a
        assert "keywords_en" in a
        assert "title_fr" in a
        assert "title_en" in a


def test_save_raw_articles_unique_ids():
    """Chaque article reçoit un ID unique."""
    from processors.gemini_processor import save_raw_articles
    results = save_raw_articles(SAMPLE_ARTICLES)
    ids = [a["id"] for a in results]
    assert len(ids) == len(set(ids)), "IDs dupliqués détectés"


def test_save_raw_articles_preserves_url():
    """L'URL de l'article est bien conservée."""
    from processors.gemini_processor import save_raw_articles
    results = save_raw_articles(SAMPLE_ARTICLES)
    assert results[0]["article_url"] == "https://example.com/rust-node"
    assert results[1]["article_url"] == "https://example.com/k8s-136"


def test_enrich_articles_batch_structure(monkeypatch):
    """Vérifie la structure de sortie d'enrich_articles_batch (mock LLM)."""
    from processors import gemini_processor

    # Mock du LLM pour ne pas consommer de quota
    mock_response = [
        {
            "title_fr": "Rust atteint 99% de compatibilité Node.js",
            "title_en": "Rust reaches 99% Node.js compatibility",
            "short_description_fr": "Bun réécrit son cœur en Rust.",
            "short_description_en": "Bun rewrites its core in Rust.",
            "long_description_fr": "Le runtime JavaScript Bun a réécrit son cœur en Rust.",
            "long_description_en": "The Bun JavaScript runtime has rewritten its core in Rust.",
            "keywords_fr": ["Rust", "Node.js", "JavaScript", "runtime", "Dev"],
            "keywords_en": ["Rust", "Node.js", "JavaScript", "runtime", "Dev"],
            "category": "Dev",
        },
        {
            "title_fr": "Kubernetes v1.36 : sharding côté serveur",
            "title_en": "Kubernetes v1.36 ships server-side sharding",
            "short_description_fr": "Kubernetes améliore la scalabilité.",
            "short_description_en": "Kubernetes improves scalability.",
            "long_description_fr": "Kubernetes v1.36 introduit le sharding.",
            "long_description_en": "Kubernetes v1.36 introduces sharding.",
            "keywords_fr": ["Kubernetes", "DevOps", "Cloud", "k8s"],
            "keywords_en": ["Kubernetes", "DevOps", "Cloud", "k8s"],
            "category": "DevOps",
        },
    ]

    import json
    monkeypatch.setattr(gemini_processor, "_call_llm",
                        lambda prompt, models, thinking=True: json.dumps(mock_response))

    results = gemini_processor.enrich_articles_batch(SAMPLE_ARTICLES)
    assert len(results) == 2

    for a in results:
        assert a["title_fr"], "title_fr vide"
        assert a["title_en"], "title_en vide"
        assert a["short_description_fr"], "short_description_fr vide"
        assert a["short_description_en"], "short_description_en vide"
        assert a["long_description_fr"], "long_description_fr vide"
        assert a["long_description_en"], "long_description_en vide"
        assert a["category"] in CATEGORIES, f"Catégorie invalide : {a['category']}"
        assert isinstance(a["keywords_fr"], list), "keywords_fr doit être une liste"
        assert isinstance(a["keywords_en"], list), "keywords_en doit être une liste"
        assert len(a["keywords_fr"]) > 0, "keywords_fr vide"


def test_add_articles_no_cap_on_collection():
    """Le collector doit tout récupérer — pas de limite arbitraire de collecte."""
    all_raw: list[dict] = []
    seen_urls: set[str] = set()

    def already_exists_never(_url: str) -> bool:
        return False

    def _add_articles_to_batch(articles: list[dict]) -> None:
        for raw in articles:
            url = raw["article_url"]
            if url in seen_urls or already_exists_never(url):
                continue
            seen_urls.add(url)
            all_raw.append(raw)

    # Gmail : 25 articles uniques
    gmail_articles = [
        {"title": f"Gmail article {i}", "article_url": f"https://gmail.example.com/{i}"}
        for i in range(25)
    ]
    _add_articles_to_batch(gmail_articles)

    # Web : 15 articles uniques supplémentaires
    web_articles = [
        {"title": f"Web article {i}", "article_url": f"https://web.example.com/{i}"}
        for i in range(15)
    ]
    _add_articles_to_batch(web_articles)

    assert len(all_raw) == 40, (
        f"Toutes les sources doivent être collectées sans plafond, attendu 40, obtenu {len(all_raw)}"
    )


def test_add_articles_dedup_only():
    """La déduplication par URL est le seul filtre — pas de limite de volume."""
    all_raw: list[dict] = []
    seen_urls: set[str] = set()
    in_firestore = {"https://already.example.com/1", "https://already.example.com/2"}

    def already_exists(url: str) -> bool:
        return url in in_firestore

    def _add_articles_to_batch(articles: list[dict]) -> None:
        for raw in articles:
            url = raw["article_url"]
            if url in seen_urls or already_exists(url):
                continue
            seen_urls.add(url)
            all_raw.append(raw)

    articles = [
        {"title": "Nouveau", "article_url": "https://new.example.com/1"},
        {"title": "Déjà en base 1", "article_url": "https://already.example.com/1"},
        {"title": "Déjà en base 2", "article_url": "https://already.example.com/2"},
        {"title": "Nouveau 2", "article_url": "https://new.example.com/2"},
        {"title": "Doublon run", "article_url": "https://new.example.com/1"},  # vu dans le run
    ]
    _add_articles_to_batch(articles)

    assert len(all_raw) == 2, f"Seuls les 2 nouveaux doivent passer, obtenu {len(all_raw)}"
    urls = [a["article_url"] for a in all_raw]
    assert "https://new.example.com/1" in urls
    assert "https://new.example.com/2" in urls


def test_enrich_articles_category_injected_in_keywords(monkeypatch):
    """La catégorie doit être en tête des mots-clés."""
    from processors import gemini_processor
    import json

    mock_response = [{
        "title_fr": "Test", "title_en": "Test",
        "short_description_fr": "Test.", "short_description_en": "Test.",
        "long_description_fr": "Test long.", "long_description_en": "Test long.",
        "keywords_fr": ["Kubernetes", "cluster"],
        "keywords_en": ["Kubernetes", "cluster"],
        "category": "DevOps",
    }]

    monkeypatch.setattr(gemini_processor, "_call_llm",
                        lambda prompt, models, thinking=True: json.dumps(mock_response))

    results = gemini_processor.enrich_articles_batch([SAMPLE_ARTICLES[1]])
    assert results[0]["keywords_fr"][0] == "DevOps", "Catégorie absente en tête des keywords_fr"
    assert results[0]["keywords_en"][0] == "DevOps", "Catégorie absente en tête des keywords_en"


# ─── Diagnostic des échecs LLM ────────────────────────────────────────────────
# Régression : la cascade signalait tous les échecs comme « quota épuisé » en
# ne journalisant que le nom de la classe d'exception. La vraie cause doit
# désormais remonter, et le mot « quota » ne doit apparaître que sur un 429.

def _fail_with(exc):
    """Construit un faux genai.GenerativeModel dont l'appel lève `exc`."""
    from unittest.mock import MagicMock
    model = MagicMock()
    model.generate_content = MagicMock(side_effect=exc)
    return lambda *a, **k: model


def test_call_llm_expose_le_message_derreur_reel(monkeypatch):
    """Un 404 doit être rapporté comme modèle introuvable, pas comme un quota."""
    from processors import gemini_processor
    from google.api_core import exceptions as gexc

    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel",
                        _fail_with(gexc.NotFound("models/modele-x is not found for API version v1beta")))

    with pytest.raises(gemini_processor.LLMCascadeError) as excinfo:
        gemini_processor._call_llm("prompt", ["modele-x"])

    message = str(excinfo.value)
    assert "404" in message, "le code HTTP réel doit être conservé"
    assert "is not found for API version" in message, "le message brut de l'API doit être conservé"
    assert "quota" not in message.lower(), "un 404 ne doit jamais être présenté comme un quota"


def test_call_llm_signale_un_vrai_quota(monkeypatch):
    """Un 429 — et lui seul — doit être qualifié de dépassement de quota."""
    from processors import gemini_processor
    from google.api_core import exceptions as gexc

    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel",
                        _fail_with(gexc.ResourceExhausted("Quota exceeded for quota metric")))

    with pytest.raises(gemini_processor.LLMCascadeError) as excinfo:
        gemini_processor._call_llm("prompt", ["modele-x"])

    assert "429" in str(excinfo.value)
    assert "QUOTA" in str(excinfo.value)


def test_call_llm_cumule_les_echecs_de_toute_la_cascade(monkeypatch):
    """Chaque modèle essayé doit apparaître dans l'erreur finale."""
    from processors import gemini_processor
    from google.api_core import exceptions as gexc

    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel",
                        _fail_with(gexc.PermissionDenied("API not enabled")))

    with pytest.raises(gemini_processor.LLMCascadeError) as excinfo:
        gemini_processor._call_llm("prompt", ["modele-a", "modele-b"])

    assert [m for m, _ in excinfo.value.failures] == ["modele-a", "modele-b"]
    assert "403" in str(excinfo.value)


def test_call_llm_retente_sans_thinking_config_si_non_supporte(monkeypatch):
    """Le SDK rejette `thinking_config` côté client : on retente sans, et ça marche."""
    from unittest.mock import MagicMock
    from processors import gemini_processor

    configs_recus = []

    def fake_model(model_name, generation_config=None):
        model = MagicMock()

        def generate(prompt):
            configs_recus.append(generation_config or {})
            if "thinking_config" in (generation_config or {}):
                raise ValueError("Unknown field for GenerationConfig: thinking_config")
            response = MagicMock()
            response.text = '{"ok": true}'
            return response

        model.generate_content = generate
        return model

    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel", fake_model)

    assert gemini_processor._call_llm("prompt", ["modele-a"], thinking=True) == '{"ok": true}'
    assert len(configs_recus) == 2, "un essai avec thinking, puis un sans"
    assert "thinking_config" not in configs_recus[1]


def test_call_llm_ne_masque_pas_une_erreur_api_derriere_le_fallback_thinking(monkeypatch):
    """Une erreur API ne doit pas être confondue avec `thinking_config` non supporté."""
    from processors import gemini_processor
    from google.api_core import exceptions as gexc

    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel",
                        _fail_with(gexc.BadRequest("Invalid JSON payload")))

    with pytest.raises(gemini_processor.LLMCascadeError) as excinfo:
        gemini_processor._call_llm("prompt", ["modele-a"], thinking=True)

    assert "Invalid JSON payload" in str(excinfo.value)


def test_call_llm_explicite_une_reponse_sans_texte(monkeypatch):
    """Réponse tronquée (MAX_TOKENS) : la raison doit être lisible, pas opaque."""
    from unittest.mock import MagicMock, PropertyMock
    from processors import gemini_processor

    response = MagicMock()
    type(response).text = PropertyMock(side_effect=ValueError("no Part"))
    candidat = MagicMock()
    candidat.finish_reason = "MAX_TOKENS"
    response.candidates = [candidat]

    model = MagicMock()
    model.generate_content = MagicMock(return_value=response)
    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel", lambda *a, **k: model)

    with pytest.raises(gemini_processor.LLMCascadeError) as excinfo:
        gemini_processor._call_llm("prompt", ["modele-a"], thinking=False)

    assert "MAX_TOKENS" in str(excinfo.value)


def test_generate_run_report_rapporte_la_cause_reelle(monkeypatch):
    """Le fallback du rapport ne doit plus affirmer « hors quota » sans preuve."""
    from processors import gemini_processor
    from google.api_core import exceptions as gexc

    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel",
                        _fail_with(gexc.NotFound("models/modele-x is not found")))

    rapport = gemini_processor.generate_run_report("des logs", ["modele-x"])

    assert "hors quota" not in rapport
    assert "modele-x" in rapport
    assert "404" in rapport


# ─── Blocage au niveau du compte (facturation) ────────────────────────────────
# Google renvoie 429 aussi bien pour un débit dépassé que pour un solde prépayé
# épuisé. Les deux ne se traitent pas pareil : le second bloque tous les modèles.

_ERREUR_FACTURATION = (
    "429 Your prepayment credits are depleted. Please go to AI Studio at "
    "https://ai.studio/projects to manage your project and billing."
)


def test_429_de_facturation_nest_pas_presente_comme_un_quota(monkeypatch):
    """Solde prépayé épuisé : le message doit désigner la facturation, pas le quota."""
    from processors import gemini_processor
    from google.api_core import exceptions as gexc

    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel",
                        _fail_with(gexc.ResourceExhausted(_ERREUR_FACTURATION)))

    with pytest.raises(gemini_processor.LLMCascadeError) as excinfo:
        gemini_processor._call_llm("prompt", ["modele-a"])

    message = str(excinfo.value)
    assert "FACTURATION BLOQUÉE" in message
    assert "DÉBIT OU QUOTA DÉPASSÉ" not in message, "à ne pas confondre avec un débit dépassé"
    assert "ai.studio/projects" in message, "l'action corrective doit rester lisible"


def test_429_de_debit_reste_un_quota(monkeypatch):
    """Un vrai dépassement de débit garde son libellé et n'interrompt pas la cascade."""
    from processors import gemini_processor
    from google.api_core import exceptions as gexc

    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel",
                        _fail_with(gexc.ResourceExhausted("429 Quota exceeded for quota metric 'requests'")))

    with pytest.raises(gemini_processor.LLMCascadeError) as excinfo:
        gemini_processor._call_llm("prompt", ["modele-a", "modele-b"])

    assert "DÉBIT OU QUOTA DÉPASSÉ" in str(excinfo.value)
    assert excinfo.value.aborted is False
    assert len(excinfo.value.failures) == 2, "tous les modèles doivent être essayés"


def test_facturation_bloquee_interrompt_la_cascade(monkeypatch):
    """Inutile de marteler les modèles suivants : le blocage est au niveau du compte."""
    from processors import gemini_processor
    from google.api_core import exceptions as gexc

    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel",
                        _fail_with(gexc.ResourceExhausted(_ERREUR_FACTURATION)))

    with pytest.raises(gemini_processor.LLMCascadeError) as excinfo:
        gemini_processor._call_llm("prompt", ["modele-a", "modele-b", "modele-c"])

    assert excinfo.value.aborted is True
    assert [m for m, _ in excinfo.value.failures] == ["modele-a"], "un seul modèle essayé"


def test_generate_run_report_interrompt_aussi_la_cascade(monkeypatch):
    """Le rapport ne doit pas non plus rejouer 5 fois le même échec de facturation."""
    from unittest.mock import MagicMock
    from processors import gemini_processor
    from google.api_core import exceptions as gexc

    appels = []

    def fake_model(model_name, *a, **k):
        appels.append(model_name)
        model = MagicMock()
        model.generate_content = MagicMock(side_effect=gexc.ResourceExhausted(_ERREUR_FACTURATION))
        return model

    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel", fake_model)

    rapport = gemini_processor.generate_run_report("des logs", ["modele-a", "modele-b", "modele-c"])

    assert appels == ["modele-a"], "cascade non interrompue"
    assert "FACTURATION BLOQUÉE" in rapport


def test_select_relevant_articles_interrompt_aussi_la_cascade(monkeypatch):
    """Même court-circuit sur l'étape de sélection de la synthèse."""
    from unittest.mock import MagicMock
    from processors import gemini_processor
    from google.api_core import exceptions as gexc

    appels = []

    def fake_model(model_name, *a, **k):
        appels.append(model_name)
        model = MagicMock()
        model.generate_content = MagicMock(side_effect=gexc.ResourceExhausted(_ERREUR_FACTURATION))
        return model

    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel", fake_model)

    resultat = gemini_processor.select_relevant_articles(
        [{"id": "a1", "title": "Test", "long_description": "Test."}],
        "kubernetes",
        ["modele-a", "modele-b", "modele-c"],
    )

    assert resultat is None
    assert appels == ["modele-a"], "cascade non interrompue"


# ─── Ordre de la cascade de modèles ───────────────────────────────────────────
# Régression : l'ordre stocké en Firestore l'emportait sans condition, si bien
# qu'une modification de DEFAULT_MODEL_PRIORITY restait sans effet en prod.

# Coût entrée/sortie en $ par million de tokens, au 3 août 2026.
PRIX_PAR_MTOK = {
    "gemma-4-26b-a4b-it": (0.070, 0.300),
    "gemma-4-31b-it": (0.090, 0.340),
    "gemini-3.1-flash-lite": (0.250, 1.500),
    "gemini-3-flash-preview": (0.250, 1.500),
    "gemini-3.5-flash": (1.500, 9.000),
}


# Les Gemma sont les moins chers du catalogue mais rendent des descriptions
# trop courtes pour la fiche article : ils sont relégués en repli.
MODELES_DE_REPLI = ("gemma-4-31b-it", "gemma-4-26b-a4b-it")


def test_le_moins_cher_des_modeles_retenus_est_en_tete():
    """Parmi les modèles qui tiennent la qualité, le moins cher passe d'abord."""
    from processors.gemini_processor import DEFAULT_MODEL_PRIORITY

    retenus = [m for m in DEFAULT_MODEL_PRIORITY if m not in MODELES_DE_REPLI]
    couts = [PRIX_PAR_MTOK[m] for m in retenus]
    assert couts == sorted(couts), f"cascade non triée par coût : {retenus}"
    assert retenus[0] == "gemini-3.1-flash-lite"


def test_les_modeles_de_repli_sont_en_fin_de_cascade():
    """Sollicités seulement si aucun modèle Gemini n'est disponible."""
    from processors.gemini_processor import DEFAULT_MODEL_PRIORITY

    assert DEFAULT_MODEL_PRIORITY[-2:] == list(MODELES_DE_REPLI)


def test_a_prix_egal_le_modele_stable_precede_le_preview():
    from processors.gemini_processor import DEFAULT_MODEL_PRIORITY

    assert DEFAULT_MODEL_PRIORITY.index("gemini-3.1-flash-lite") < \
        DEFAULT_MODEL_PRIORITY.index("gemini-3-flash-preview")


def test_backend_et_collector_partagent_le_meme_ordre():
    """Les copies dupliquées de la liste ne doivent pas diverger."""
    import re
    from pathlib import Path
    from processors.gemini_processor import DEFAULT_MODEL_PRIORITY

    racine = Path(__file__).resolve().parents[1]
    # Une seule copie côté backend depuis que admin.py importe le service.
    source = (racine / "backend/app/services/article_summarizer.py").read_text()
    bloc = re.search(r"DEFAULT_MODEL_PRIORITY = \[(.*?)\]", source, re.S).group(1)
    assert re.findall(r'"([^"]+)"', bloc) == DEFAULT_MODEL_PRIORITY, "le backend a divergé du collector"

    assert "DEFAULT_MODEL_PRIORITY = [" not in (racine / "backend/app/routers/admin.py").read_text(), \
        "admin.py doit importer la liste, pas la redéfinir"


def test_lordre_de_ladmin_est_applique_litteralement():
    """Règle absolue : l'ordre choisi dans la page admin est utilisé tel quel."""
    from processors.gemini_processor import resolve_model_priority

    choix_admin = [
        "gemini-3.5-flash", "gemma-4-26b-a4b-it", "gemini-3.1-flash-lite",
        "gemini-3-flash-preview", "gemma-4-31b-it",
    ]
    assert resolve_model_priority(choix_admin) == choix_admin


def test_aucun_modele_nest_insere_ni_retire():
    """Ni tri, ni purge, ni insertion : le code ne déduit rien."""
    from processors.gemini_processor import resolve_model_priority

    # Un seul modèle choisi : on ne complète pas la liste.
    assert resolve_model_priority(["gemini-3.5-flash"]) == ["gemini-3.5-flash"]

    # Un modèle hors catalogue est conservé — c'est le choix de l'admin.
    exotique = ["modele-maison", "gemini-3.1-flash-lite"]
    assert resolve_model_priority(exotique) == exotique


def test_liste_vide_amorce_sur_le_defaut():
    """Seul cas où le code décide : un projet neuf, sans ordre encore choisi."""
    from processors.gemini_processor import resolve_model_priority, DEFAULT_MODEL_PRIORITY

    assert resolve_model_priority([]) == DEFAULT_MODEL_PRIORITY
    assert resolve_model_priority(None) == DEFAULT_MODEL_PRIORITY


def test_resolve_ne_renvoie_pas_la_constante_elle_meme():
    """L'appelant ne doit pas pouvoir muter DEFAULT_MODEL_PRIORITY par accident."""
    from processors.gemini_processor import resolve_model_priority, DEFAULT_MODEL_PRIORITY

    resultat = resolve_model_priority(None)
    resultat.append("intrus")
    assert "intrus" not in DEFAULT_MODEL_PRIORITY


# ─── Motif de la montée en gamme ──────────────────────────────────────────────
# La cascade est triée du moins cher au plus cher : on ne monte d'un cran que
# lorsque le modèle courant refuse. Un JSON illisible doit compter comme un
# refus — sinon un petit modèle bavard fait tomber tout le run.

def test_json_malforme_fait_monter_dun_cran(monkeypatch):
    """Le modèle bon marché répond du texte libre : on doit passer au suivant."""
    from unittest.mock import MagicMock
    from processors import gemini_processor

    appels = []

    def fake_model(model_name, *a, **k):
        appels.append(model_name)
        model = MagicMock()
        response = MagicMock()
        response.text = ("Bien sûr ! Voici les articles :" if model_name == "pas-cher"
                         else '{"ok": true}')
        model.generate_content = MagicMock(return_value=response)
        return model

    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel", fake_model)

    resultat = gemini_processor._call_llm("prompt", ["pas-cher", "plus-cher"])

    assert resultat == '{"ok": true}'
    assert appels == ["pas-cher", "plus-cher"], "la cascade n'est pas montée d'un cran"


def test_json_malforme_partout_leve_une_erreur_de_cascade(monkeypatch):
    """Si aucun modèle ne produit du JSON, l'échec doit être explicite."""
    from unittest.mock import MagicMock
    from processors import gemini_processor

    model = MagicMock()
    response = MagicMock()
    response.text = "désolé, je ne peux pas"
    model.generate_content = MagicMock(return_value=response)
    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel", lambda *a, **k: model)

    with pytest.raises(gemini_processor.LLMCascadeError) as excinfo:
        gemini_processor._call_llm("prompt", ["a", "b"])

    assert "JSON" in str(excinfo.value)
    assert len(excinfo.value.failures) == 2


def test_depassement_et_anomalie_sont_journalises_differemment(monkeypatch, caplog):
    """Le rapport doit distinguer une montée par conception d'un défaut à corriger."""
    import logging
    from unittest.mock import MagicMock
    from processors import gemini_processor
    from google.api_core import exceptions as gexc

    erreurs = {
        "sur-quota": gexc.ResourceExhausted("429 Quota exceeded for quota metric 'requests'"),
        "inconnu": gexc.NotFound("404 model not found"),
    }

    def fake_model(model_name, *a, **k):
        model = MagicMock()
        if model_name in erreurs:
            model.generate_content = MagicMock(side_effect=erreurs[model_name])
        else:
            response = MagicMock()
            response.text = '{"ok": true}'
            model.generate_content = MagicMock(return_value=response)
        return model

    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel", fake_model)

    with caplog.at_level(logging.WARNING):
        gemini_processor._call_llm("prompt", ["sur-quota", "inconnu", "bon"])

    journal = caplog.text
    assert "dépassement sur sur-quota" in journal
    assert "anomalie sur inconnu" in journal


# ─── 429 de débit vs 429 de facturation ───────────────────────────────────────
# Régression : le marqueur « billing » était trop large. TOUS les 429 de Gemini
# contiennent « check your plan and billing details », y compris un simple
# dépassement de débit — la cascade s'interrompait donc à tort au premier modèle.

MESSAGE_429_DEBIT_REEL = (
    "429 You exceeded your current quota, please check your plan and billing details. "
    "For more information on this error, head to: "
    "https://ai.google.dev/gemini-api/docs/rate-limits. To monitor your current usage, "
    "head to: https://ai.dev/rate-limit. * Quota exceeded for metric: "
    "generativelanguage.googleapis.com/generate_content_free_tier_requests"
)


def test_un_429_de_debit_nest_pas_pris_pour_un_compte_bloque(monkeypatch):
    """Message réel de production : doit faire monter d'un cran, pas tout arrêter."""
    from unittest.mock import MagicMock
    from processors import gemini_processor
    from google.api_core import exceptions as gexc

    appels = []

    def fake_model(model_name, *a, **k):
        appels.append(model_name)
        model = MagicMock()
        if model_name == "sature":
            model.generate_content = MagicMock(
                side_effect=gexc.ResourceExhausted(MESSAGE_429_DEBIT_REEL))
        else:
            response = MagicMock()
            response.text = '{"ok": true}'
            model.generate_content = MagicMock(return_value=response)
        return model

    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel", fake_model)

    assert gemini_processor._call_llm("prompt", ["sature", "suivant"]) == '{"ok": true}'
    assert appels == ["sature", "suivant"], "la cascade a été interrompue à tort"


def test_le_message_de_debit_ne_parle_pas_de_facturation():
    """Le libellé ne doit pas envoyer l'utilisateur recharger un compte crédité."""
    from processors import gemini_processor
    from google.api_core import exceptions as gexc

    describe = gemini_processor._describe_llm_error(
        gexc.ResourceExhausted(MESSAGE_429_DEBIT_REEL))

    assert "FACTURATION BLOQUÉE" not in describe
    assert "DÉBIT OU QUOTA DÉPASSÉ" in describe


def test_le_vrai_message_de_facturation_reste_detecte():
    """Le cas d'origine ne doit pas régresser."""
    from processors import gemini_processor
    from google.api_core import exceptions as gexc

    exc = gexc.ResourceExhausted(
        "429 Your prepayment credits are depleted. Please go to AI Studio at "
        "https://ai.studio/projects to manage your project and billing.")

    assert gemini_processor._is_account_level_failure(exc, 429) is True
    assert "FACTURATION BLOQUÉE" in gemini_processor._describe_llm_error(exc)


# ─── Rapport d'exécution : brouillon du modèle ────────────────────────────────
# Régression : certains modèles restituent leur cheminement (consignes
# reformulées, brouillons, auto-corrections) avant la réponse finale. Le
# rapport lu par l'administrateur devenait illisible.

SORTIE_AVEC_BROUILLON = """Assistant writing a summary report of a technological watch collection.
French. Structured, clear, concise, readable in 30 seconds, use emojis.

    *   *Settings:* LLM=True, Thinking=True.
    *   *Self-Correction:* The logs say "Synthèse sauvegardée". *Wait*, the logs
        show "0 source(s) active(s)". I'll report what the log says.

    *Structure draft:*
    **Sources sollicitées**
    - brouillon à jeter

    *   Readable in 30s? Yes.
Voici le rapport :

**Sources sollicitées**
* TLDR (gmail) : active

**Collecte emails**
* 3 emails, 12 articles extraits

**Traitement LLM**
* Modèle utilisé : gemini-3.1-flash-lite

**Résultat**
* 12 articles sauvegardés

**Anomalies**
* Aucune
"""


def test_le_brouillon_du_modele_est_retire_du_rapport():
    from processors.gemini_processor import _clean_report_output

    rapport = _clean_report_output(SORTIE_AVEC_BROUILLON, "modele-bavard")

    assert rapport.startswith("**Sources sollicitées**")
    assert "Self-Correction" not in rapport
    assert "brouillon à jeter" not in rapport
    assert "Readable in 30s" not in rapport
    assert "12 articles sauvegardés" in rapport, "le vrai rapport doit être conservé"


def test_une_reponse_sans_sections_est_un_echec_de_modele(monkeypatch):
    """Pas de rapport exploitable : on doit monter d'un cran, pas publier du bruit."""
    from unittest.mock import MagicMock
    from processors import gemini_processor

    appels = []

    def fake_model(model_name, *a, **k):
        appels.append(model_name)
        model = MagicMock()
        response = MagicMock()
        response.text = ("Je réfléchis à la structure du rapport..." if model_name == "bavard"
                         else SORTIE_AVEC_BROUILLON)
        model.generate_content = MagicMock(return_value=response)
        return model

    monkeypatch.setattr(gemini_processor.genai, "GenerativeModel", fake_model)

    rapport = gemini_processor.generate_run_report("des logs", ["bavard", "correct"])

    assert appels == ["bavard", "correct"], "la cascade n'est pas montée d'un cran"
    assert rapport.startswith("**Sources sollicitées**")


def test_le_rapport_est_borne_en_taille():
    """Le rapport doit rester lisible en 30 secondes."""
    from processors.gemini_processor import REPORT_GENERATION_CONFIG

    assert REPORT_GENERATION_CONFIG["max_output_tokens"] <= 4_000
    assert REPORT_GENERATION_CONFIG["temperature"] <= 0.3, "mise en forme, pas création"


def test_les_plafonds_de_troncature_sont_reellement_appliques():
    """Régression : MAX_REPORT_LOGS et MAX_GMAIL_CONTENT_FOR_PROMPT étaient
    déclarés mais le code utilisait des littéraux — les régler ne faisait rien."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1]
              / "collector/processors/gemini_processor.py").read_text()

    assert "logs[:MAX_REPORT_LOGS]" in source
    assert "content[:MAX_GMAIL_CONTENT_FOR_PROMPT]" in source
    assert "[:8000]" not in source and "[:50000]" not in source


# ─── Traçabilité du build ─────────────────────────────────────────────────────
# On a passé deux itérations à se demander « ce run a-t-il tourné sur le
# nouveau code ? ». Le job était déployé sur le tag :latest, donc indéterminable
# après coup. Le SHA est désormais journalisé et persisté hors LLM.

def test_le_build_est_persiste_avec_le_rapport():
    """Le SHA doit être écrit en dur dans reports/latest, pas rédigé par le LLM."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "collector/main.py").read_text()
    assert '"build": BUILD' in source, "le build doit accompagner le rapport"
    assert 'logger.info(f"Collector — build {BUILD}")' in source, "build absent des logs"


def test_le_build_retombe_sur_inconnu_hors_ci():
    """En local, sans GIT_SHA, le collector ne doit pas planter."""
    import os
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "collector/main.py").read_text()
    # Reproduit l'expression sans importer main.py (qui ouvre une connexion Firestore).
    ligne = next(l for l in source.splitlines() if l.startswith("BUILD = "))
    contexte = {"os": os}
    env_sans_sha = {k: v for k, v in os.environ.items() if k != "GIT_SHA"}
    with_patched = os.environ
    try:
        os.environ = env_sans_sha  # type: ignore[assignment]
        exec(ligne, contexte)
    finally:
        os.environ = with_patched  # type: ignore[assignment]
    assert contexte["BUILD"] == "inconnu"


def test_le_job_est_deploye_sur_un_tag_immuable():
    """`:latest` rend le build indéterminable après coup — on tague par SHA."""
    from pathlib import Path

    ci = (Path(__file__).resolve().parents[1] / ".github/workflows/ci-cd.yml").read_text()
    # Portée : les deux Cloud Run *Jobs* (collector, log-analyzer). Les services
    # backend/frontend gardent :latest — une révision Cloud Run en conserve le
    # digest, ils restent donc traçables ; un Job, non.
    blocs = ci.split("gcloud run jobs update")[1:]
    assert len(blocs) == 2, "collector + log-analyzer attendus"

    for bloc in blocs:
        commande = bloc.split("--quiet")[0]
        image = next(l for l in commande.splitlines() if "--image=" in l)
        assert ":latest" not in image, f"job déployé sur un tag mouvant : {image.strip()}"
        assert "github.sha" in image, f"tag non traçable : {image.strip()}"
        assert "--update-env-vars=GIT_SHA=" in commande, "GIT_SHA non injecté"
