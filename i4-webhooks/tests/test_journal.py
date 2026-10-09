import io
import json
import logging

import pytest

from i4_webhooks.journal import NOM_JOURNAL, FormateurJson, configurer_journal, journal, tracer

SECRET = "matrice-local-only"


@pytest.fixture
def sortie():
    flux = io.StringIO()
    gestionnaire = logging.StreamHandler(flux)
    gestionnaire.setFormatter(FormateurJson())
    journal.addHandler(gestionnaire)
    journal.setLevel(logging.INFO)
    yield lambda: [json.loads(ligne) for ligne in flux.getvalue().splitlines()]
    journal.removeHandler(gestionnaire)


def test_une_ligne_json_par_evenement(sortie):
    tracer("livraison.tentative", event_id="evt-1", tentative=2, resultat="http 503")

    [ligne] = sortie()
    assert ligne["evenement"] == "livraison.tentative"
    assert ligne["niveau"] == "INFO"
    assert (ligne["event_id"], ligne["tentative"], ligne["resultat"]) == ("evt-1", 2, "http 503")
    assert ligne["horodatage"].endswith("+00:00")


def test_champs_hors_liste_blanche_jamais_ecrits(sortie):
    tracer(
        "webhook.rejete",
        statut_http=401,
        secret=SECRET,
        signature="sha256=" + "a" * 64,
        corps=b'{"event_id":"evt-1"}',
        en_tetes={"X-Signature": "sha256=..."},
    )

    [ligne] = sortie()
    assert set(ligne) == {"horodatage", "niveau", "evenement", "statut_http"}


def test_retour_a_la_ligne_dans_une_valeur_echappe(sortie):
    tracer("webhook.accepte", event_id='evt-1\n{"evenement":"faux"}')

    lignes = sortie()
    assert len(lignes) == 1
    assert lignes[0]["event_id"] == 'evt-1\n{"evenement":"faux"}'


def test_niveau_avertissement(sortie):
    tracer("livraison.quarantaine", niveau=logging.WARNING, event_id="evt-1")

    assert sortie()[0]["niveau"] == "WARNING"


def test_configuration_idempotente():
    avant = list(journal.handlers)
    flux = io.StringIO()
    try:
        configurer_journal(flux)
        configurer_journal(flux)
        ajoutes = [g for g in journal.handlers if g not in avant]
        assert len(ajoutes) == 1
        tracer("webhook.accepte", event_id="evt-1")
        assert json.loads(flux.getvalue())["event_id"] == "evt-1"
    finally:
        for gestionnaire in journal.handlers[:]:
            if gestionnaire not in avant:
                journal.removeHandler(gestionnaire)


def test_nom_du_journal():
    assert journal.name == NOM_JOURNAL
