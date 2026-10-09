import logging

import pytest

from fabriques import MAINTENANT, SECRET, evenement, octets, seance
from i4_webhooks.config import ConfigurationInvalide, TAILLE_MAX_CORPS
from i4_webhooks.journal import NOM_JOURNAL, FormateurJson
from i4_webhooks.recepteur import creer_app
from i4_webhooks.signature import signer


def livraison(r, event_id="evt-1"):
    return r.client.get(f"/deliveries/{event_id}")


def evenement_de_taille(taille):
    sans_titre = len(octets(evenement(session=seance(title=""))))
    corps = octets(evenement(session=seance(title="x" * (taille - sans_titre))))
    assert len(corps) == taille
    return corps


def test_health(recepteur):
    reponse = recepteur().client.get("/health")

    assert (reponse.status_code, reponse.json()) == (200, {"status": "ok"})


# --- Signature ---------------------------------------------------------------------------


def test_signature_valide_accepte_puis_livre(recepteur):
    r = recepteur()

    reponse = r.poster(evenement())

    assert (reponse.status_code, reponse.json()) == (202, {"event_id": "evt-1", "duplicate": False})
    assert livraison(r).json() == {"event_id": "evt-1", "status": "delivered", "attempts": 1, "last_error": None}
    assert r.partenaire.state.tickets["evt-1"]["session_id"] == "s01"


def test_signature_avec_un_autre_secret_refusee(recepteur):
    r = recepteur()

    reponse = r.poster(evenement(), secret="autre-secret")

    assert (reponse.status_code, reponse.json()) == (401, {"detail": "signature invalide"})
    assert livraison(r).status_code == 404
    assert r.partenaire.state.appels == {}


def test_corps_modifie_apres_signature_refuse(recepteur):
    r = recepteur()
    signature = signer(SECRET, str(MAINTENANT), octets(evenement()))

    reponse = r.poster(evenement(event_id="evt-pirate"), signature=signature)

    assert reponse.status_code == 401
    assert livraison(r, "evt-pirate").status_code == 404


@pytest.mark.parametrize(
    ("en_tetes", "detail"),
    [
        ({"X-Signature": None}, "en-tête X-Signature absent"),
        ({"X-Timestamp": None}, "en-tête X-Timestamp absent"),
        ({"X-Signature": "abc"}, "X-Signature doit être de la forme sha256=<64 caractères hexadécimaux>"),
        ({"X-Timestamp": "demain"}, "X-Timestamp doit être un nombre entier de secondes Unix"),
    ],
)
def test_en_tetes_absents_ou_mal_formes_refuses(recepteur, en_tetes, detail):
    reponse = recepteur().poster(evenement(), en_tetes=en_tetes)

    assert (reponse.status_code, reponse.json()) == (401, {"detail": detail})


# --- Ancienneté --------------------------------------------------------------------------


@pytest.mark.parametrize("decalage", [-301, 301, 86_400])
def test_horodatage_hors_fenetre_refuse(recepteur, decalage):
    r = recepteur()

    reponse = r.poster(evenement(), horodatage=MAINTENANT - decalage)

    assert (reponse.status_code, reponse.json()) == (401, {"detail": "X-Timestamp hors de la fenêtre de 300 s"})
    assert livraison(r).status_code == 404


@pytest.mark.parametrize("decalage", [-300, 0, 300])
def test_horodatage_a_la_limite_accepte(recepteur, decalage):
    assert recepteur().poster(evenement(), horodatage=MAINTENANT - decalage).status_code == 202


# --- Taille ------------------------------------------------------------------------------


def test_corps_de_64_ko_accepte(recepteur):
    assert recepteur().poster(evenement_de_taille(TAILLE_MAX_CORPS)).status_code == 202


def test_corps_de_64_ko_plus_un_octet_refuse(recepteur):
    r = recepteur()

    reponse = r.poster(evenement_de_taille(TAILLE_MAX_CORPS + 1))

    assert reponse.status_code == 413
    assert r.partenaire.state.appels == {}


def test_corps_trop_grand_refuse_avant_l_authentification(recepteur):
    reponse = recepteur().poster(b"x" * (TAILLE_MAX_CORPS + 1), signature="sha256=" + "0" * 64)

    assert reponse.status_code == 413


def test_corps_trop_grand_sans_content_length(recepteur):
    r = recepteur()
    corps = b"x" * (TAILLE_MAX_CORPS + 1)
    horodatage = str(MAINTENANT)

    reponse = r.client.post(
        "/webhooks/planning",
        content=iter([corps[:40_000], corps[40_000:]]),
        headers={"X-Timestamp": horodatage, "X-Signature": signer(SECRET, horodatage, corps)},
    )

    assert "content-length" not in reponse.request.headers
    assert reponse.status_code == 413


# --- Corps authentifié invalide ----------------------------------------------------------


@pytest.mark.parametrize(
    ("corps", "premiere_erreur"),
    [
        (b'{"event_id":"evt-1"', "corps: Invalid JSON"),
        (octets(evenement(type="session.created")), "type:"),
        (octets(evenement(event_id="")), "event_id:"),
        (octets(evenement(occurred_at="2026-10-19T08:30:00")), "occurred_at:"),
        (octets(evenement(session=seance(mode="AUTO", teacherId="t1", status="proposed"))), "session:"),
        (octets(evenement(session=seance(teacherId=None))), "session:"),
        (octets(evenement(session=seance(date="2026-02-30"))), "session.date:"),
    ],
)
def test_corps_authentifie_invalide_400(recepteur, corps, premiere_erreur):
    r = recepteur()

    reponse = r.poster(corps)

    assert reponse.status_code == 400
    assert reponse.json()["detail"] == "événement invalide"
    assert reponse.json()["erreurs"][0].startswith(premiere_erreur)
    assert r.partenaire.state.appels == {}


# --- Doublon -----------------------------------------------------------------------------


def test_repetition_valide_200_duplicate_sans_nouvelle_livraison(recepteur):
    r = recepteur()

    premiere = r.poster(evenement())
    seconde = r.poster(evenement(), horodatage=MAINTENANT - 10)

    assert premiere.status_code == 202
    assert (seconde.status_code, seconde.json()) == (200, {"event_id": "evt-1", "duplicate": True})
    assert r.partenaire.state.appels == {"evt-1": 1}
    assert len(r.partenaire.state.tickets) == 1
    assert livraison(r).json()["attempts"] == 1


def test_doublon_apres_une_quarantaine_ne_relance_pas_la_livraison(recepteur):
    r = recepteur(mode="down")

    r.poster(evenement())
    reponse = r.poster(evenement())

    assert reponse.json()["duplicate"] is True
    assert r.partenaire.state.appels == {"evt-1": 3}


def test_repetition_invalide_reste_un_400(recepteur):
    r = recepteur()
    r.poster(evenement())

    reponse = r.poster(evenement(session=seance(group="Z")))

    assert reponse.status_code == 400


# --- Livraison vers le partenaire --------------------------------------------------------


def test_503_puis_succes(recepteur):
    r = recepteur(mode="flaky")

    assert r.poster(evenement()).status_code == 202
    assert livraison(r).json() == {"event_id": "evt-1", "status": "delivered", "attempts": 2, "last_error": None}
    assert r.attentes == [0.2]


def test_erreur_persistante_quarantaine(recepteur):
    r = recepteur(mode="down")

    assert r.poster(evenement()).status_code == 202
    assert livraison(r).json() == {"event_id": "evt-1", "status": "quarantine", "attempts": 3, "last_error": "http 503"}
    assert r.attentes == [0.2, 0.4]


def test_400_sans_retry(recepteur):
    r = recepteur(mode="reject")

    assert r.poster(evenement()).status_code == 202
    assert livraison(r).json() == {"event_id": "evt-1", "status": "quarantine", "attempts": 1, "last_error": "http 400"}
    assert r.attentes == []
    assert r.partenaire.state.appels == {"evt-1": 1}


def test_partenaire_lent_timeout_puis_quarantaine(recepteur):
    r = recepteur(mode="slow", timeout_s=0.05, delai_slow_s=1.0)

    assert r.poster(evenement()).status_code == 202
    assert livraison(r).json() == {"event_id": "evt-1", "status": "quarantine", "attempts": 3, "last_error": "timeout"}
    assert r.attentes == [0.2, 0.4]


def test_idempotency_key_egale_a_event_id(recepteur):
    r = recepteur()

    r.poster(evenement(event_id="evt-42"))

    assert r.partenaire.state.tickets["evt-42"]["idempotency_key"] == "evt-42"


def test_livraison_inconnue_404(recepteur):
    reponse = livraison(recepteur(), "jamais-recu")

    assert (reponse.status_code, reponse.json()) == (404, {"detail": "livraison inconnue"})


def test_livraison_pending_avant_la_tache_de_fond(recepteur):
    r = recepteur()

    livraison_creee, nouvelle = r.app.state.registre.enregistrer_si_nouveau("evt-manuel")

    assert nouvelle
    assert livraison(r, "evt-manuel").json() == {
        "event_id": "evt-manuel", "status": "pending", "attempts": 0, "last_error": None,
    }


# --- Configuration et journal ------------------------------------------------------------


def test_secret_absent_le_recepteur_refuse_de_demarrer(monkeypatch):
    monkeypatch.delenv("MATRICE_WEBHOOK_SECRET", raising=False)

    with pytest.raises(ConfigurationInvalide):
        creer_app()


def test_les_logs_ne_contiennent_ni_secret_ni_signature_ni_corps(recepteur, caplog):
    corps = octets(evenement())
    signature = signer(SECRET, str(MAINTENANT), corps)

    with caplog.at_level(logging.INFO, logger=NOM_JOURNAL):
        r = recepteur(mode="flaky")
        r.poster(corps, signature=signature)
        r.poster(corps)
        r.poster(evenement(event_id="evt-2"), secret="mauvais-secret")
        r.poster(evenement(event_id="evt-3"), horodatage=MAINTENANT - 301)
        r.poster(evenement(event_id="evt-4", session=seance(group="Z")))

    formateur = FormateurJson()
    lignes = [formateur.format(enregistrement) for enregistrement in caplog.records if enregistrement.name == NOM_JOURNAL]
    journal = "\n".join(lignes)

    evenements = [ligne.split('"evenement": "')[1].split('"')[0] for ligne in lignes]
    assert "webhook.accepte" in evenements
    assert "webhook.doublon" in evenements
    assert "livraison.reprise" in evenements
    assert evenements.count("webhook.rejete") == 3
    assert SECRET not in journal
    assert "mauvais-secret" not in journal
    assert signature.removeprefix("sha256=") not in journal
    assert "React composants" not in journal
