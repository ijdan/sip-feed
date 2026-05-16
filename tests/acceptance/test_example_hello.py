from pytest_bdd import scenarios, given, when, then, parsers
import pytest

from backend.app.features.example_hello import saluer

scenarios("../../features/example-hello.feature")


@pytest.fixture
def contexte():
    return {}


@given("the system is running")
def le_systeme_est_en_marche(contexte):
    contexte["pret"] = True


@when("I request a greeting")
def je_demande_un_salut(contexte):
    assert contexte.get("pret") is True
    contexte["reponse"] = saluer()


@then(parsers.parse('I receive "{message}"'))
def je_recois_le_message(contexte, message):
    assert contexte["reponse"] == message
