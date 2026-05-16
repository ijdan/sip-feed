from pytest_bdd import scenarios, given, when, then, parsers
import pytest

scenarios("../../features/example-hello.feature")


@pytest.fixture
def contexte():
    return {}


@given("the system is running")
def le_systeme_est_en_marche(contexte):
    raise NotImplementedError("Implémentation applicative à venir")


@when("I request a greeting")
def je_demande_un_salut(contexte):
    raise NotImplementedError("Implémentation applicative à venir")


@then(parsers.parse('I receive "{message}"'))
def je_recois_le_message(contexte, message):
    raise NotImplementedError("Implémentation applicative à venir")