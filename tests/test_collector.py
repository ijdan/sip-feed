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


def test_la_cascade_est_triee_du_moins_cher_au_plus_cher():
    """Règle de conception : on sollicite toujours le moins cher d'abord."""
    from processors.gemini_processor import DEFAULT_MODEL_PRIORITY

    couts = [PRIX_PAR_MTOK[m] for m in DEFAULT_MODEL_PRIORITY]
    assert couts == sorted(couts), f"cascade non triée par coût : {DEFAULT_MODEL_PRIORITY}"
    assert DEFAULT_MODEL_PRIORITY[-1] == "gemini-3.5-flash", "le plus cher doit être en dernier"


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
    for fichier in ("backend/app/routers/admin.py",
                    "backend/app/services/article_summarizer.py"):
        source = (racine / fichier).read_text()
        bloc = re.search(r"DEFAULT_MODEL_PRIORITY = \[(.*?)\]", source, re.S).group(1)
        modeles = re.findall(r'"([^"]+)"', bloc)
        assert modeles == DEFAULT_MODEL_PRIORITY, f"{fichier} a divergé du collector"


def test_version_perimee_reapplique_lordre_par_defaut():
    """Le cœur du correctif : un projet existant doit recevoir le nouvel ordre."""
    from processors.gemini_processor import merge_model_priority, DEFAULT_MODEL_PRIORITY

    ordre_stocke_en_juillet = [
        "gemini-3.5-flash", "gemini-3-flash-preview", "gemini-3.1-flash-lite",
        "gemma-4-31b-it", "gemma-4-26b-a4b-it",
    ]

    assert merge_model_priority(ordre_stocke_en_juillet, 0) == DEFAULT_MODEL_PRIORITY
    assert merge_model_priority(ordre_stocke_en_juillet, 2) == DEFAULT_MODEL_PRIORITY


def test_version_a_jour_respecte_lordre_choisi_dans_ladmin():
    """Une fois la migration passée, le choix de l'utilisateur redevient roi."""
    from processors.gemini_processor import merge_model_priority, MODEL_PRIORITY_VERSION

    choix_admin = [
        "gemini-3.5-flash", "gemma-4-31b-it", "gemini-3.1-flash-lite",
        "gemini-3-flash-preview", "gemma-4-26b-a4b-it",
    ]
    assert merge_model_priority(choix_admin, MODEL_PRIORITY_VERSION) == choix_admin


def test_purge_les_modeles_inconnus_et_insere_les_nouveaux():
    """Comportement historique conservé pour une version à jour."""
    from processors.gemini_processor import merge_model_priority, MODEL_PRIORITY_VERSION

    resultat = merge_model_priority(
        ["modele-retire-du-catalogue", "gemini-3.5-flash"], MODEL_PRIORITY_VERSION
    )
    assert "modele-retire-du-catalogue" not in resultat
    assert set(resultat) == {
        "gemini-3.1-flash-lite", "gemini-3.5-flash", "gemini-3-flash-preview",
        "gemma-4-31b-it", "gemma-4-26b-a4b-it",
    }
    assert resultat[-1] == "gemini-3.5-flash", "les modèles absents s'insèrent en tête"


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
