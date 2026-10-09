import asyncio
import json
import time

import httpx2
import pytest

from i4_webhooks.livraison import est_reessayable, livrer
from i4_webhooks.partenaire import creer_app as creer_partenaire
from i4_webhooks.stockage import EN_ATTENTE, LIVREE, QUARANTAINE, Livraison, Registre

CORPS = json.dumps({"event_id": "evt-1", "session": {"id": "s01"}}, separators=(",", ":")).encode()


def executer(transport, timeout_s=2.0, attendre=None):
    attentes = []

    async def attendre_sans_dormir(secondes):
        attentes.append(secondes)

    async def scenario():
        async with httpx2.AsyncClient(transport=transport, base_url="http://partenaire") as client:
            return await livrer(Livraison("evt-1"), CORPS, client, timeout_s, attendre or attendre_sans_dormir)

    return asyncio.run(scenario()), attentes


def vers_partenaire(mode, timeout_s=2.0, **options):
    partenaire = creer_partenaire(mode=mode, **options)
    livraison, attentes = executer(httpx2.ASGITransport(app=partenaire), timeout_s=timeout_s)
    return livraison, attentes, partenaire


def reponses(*statuts):
    """Transport simulé qui renvoie les codes donnés dans l'ordre, puis le dernier en boucle."""
    restants = list(statuts)
    requetes = []

    def repondre(requete):
        requetes.append(requete)
        statut = restants.pop(0) if len(restants) > 1 else restants[0]
        return httpx2.Response(statut, json={})

    return httpx2.MockTransport(repondre), requetes


def test_ok_livre_en_une_tentative():
    livraison, attentes, partenaire = vers_partenaire("ok")

    assert (livraison.statut, livraison.tentatives, attentes) == (LIVREE, 1, [])
    assert list(partenaire.state.tickets) == ["evt-1"]


def test_503_puis_succes_livre_a_la_deuxieme_tentative():
    livraison, attentes, partenaire = vers_partenaire("flaky")

    assert (livraison.statut, livraison.tentatives, attentes) == (LIVREE, 2, [0.2])
    assert livraison.derniere_erreur is None
    assert partenaire.state.appels == {"evt-1": 2}
    assert len(partenaire.state.tickets) == 1


def test_erreur_persistante_trois_tentatives_puis_quarantaine():
    livraison, attentes, partenaire = vers_partenaire("down")

    assert (livraison.statut, livraison.tentatives, attentes) == (QUARANTAINE, 3, [0.2, 0.4])
    assert livraison.derniere_erreur == "http 503"
    assert partenaire.state.appels == {"evt-1": 3}


def test_400_sans_retry_puis_quarantaine():
    livraison, attentes, partenaire = vers_partenaire("reject")

    assert (livraison.statut, livraison.tentatives, attentes) == (QUARANTAINE, 1, [])
    assert livraison.derniere_erreur == "http 400"
    assert partenaire.state.appels == {"evt-1": 1}


def test_timeout_reessaye_puis_quarantaine():
    debut = time.monotonic()
    livraison, attentes, partenaire = vers_partenaire("slow", delai_slow_s=1.0, timeout_s=0.05)

    assert (livraison.statut, livraison.tentatives, attentes) == (QUARANTAINE, 3, [0.2, 0.4])
    assert livraison.derniere_erreur == "timeout"
    assert partenaire.state.appels == {"evt-1": 3}
    assert time.monotonic() - debut < 0.9


def test_429_reessaye():
    transport, requetes = reponses(429, 201)

    livraison, attentes = executer(transport)

    assert (livraison.statut, livraison.tentatives, attentes) == (LIVREE, 2, [0.2])
    assert len(requetes) == 2


@pytest.mark.parametrize("statut", [500, 502, 503, 504])
def test_5xx_reessayes_jusqu_a_la_quarantaine(statut):
    transport, requetes = reponses(statut)

    livraison, attentes = executer(transport)

    assert (livraison.statut, livraison.tentatives, attentes) == (QUARANTAINE, 3, [0.2, 0.4])
    assert livraison.derniere_erreur == f"http {statut}"


@pytest.mark.parametrize("statut", [400, 401, 403, 404, 409, 422])
def test_autres_4xx_sans_retry(statut):
    transport, requetes = reponses(statut)

    livraison, attentes = executer(transport)

    assert (livraison.statut, livraison.tentatives, attentes, len(requetes)) == (QUARANTAINE, 1, [], 1)


@pytest.mark.parametrize("statut", [200, 201, 202, 204])
def test_toute_reponse_2xx_est_un_succes(statut):
    transport, _ = reponses(statut)

    assert executer(transport)[0].statut == LIVREE


def test_erreur_reseau_reessayee():
    def refuser(requete):
        raise httpx2.ConnectError("connexion refusée", request=requete)

    livraison, attentes = executer(httpx2.MockTransport(refuser))

    assert (livraison.statut, livraison.tentatives, attentes) == (QUARANTAINE, 3, [0.2, 0.4])
    assert livraison.derniere_erreur == "erreur réseau (ConnectError)"


def test_erreur_imprevue_mise_en_quarantaine():
    def planter(requete):
        raise RuntimeError("bogue")

    livraison, _ = executer(httpx2.MockTransport(planter))

    assert (livraison.statut, livraison.derniere_erreur) == (QUARANTAINE, "erreur interne (RuntimeError)")


def test_idempotency_key_et_corps_transmis_sans_modification():
    transport, requetes = reponses(201)

    executer(transport)

    [requete] = requetes
    assert requete.method == "POST"
    assert requete.url.path == "/tickets"
    assert requete.headers["Idempotency-Key"] == "evt-1"
    assert requete.headers["Content-Type"] == "application/json"
    assert requete.content == CORPS


def test_attentes_reelles_par_defaut():
    transport, _ = reponses(503)

    debut = time.monotonic()
    livraison, _ = executer(transport, attendre=asyncio.sleep)

    assert livraison.statut == QUARANTAINE
    assert time.monotonic() - debut >= 0.6


def test_statut_pending_pendant_les_reprises():
    livraison = Livraison("evt-1")
    vus = []

    async def observer(secondes):
        vus.append((livraison.statut, livraison.tentatives))

    async def scenario():
        transport, _ = reponses(503, 201)
        async with httpx2.AsyncClient(transport=transport, base_url="http://partenaire") as client:
            await livrer(livraison, CORPS, client, 2.0, observer)

    asyncio.run(scenario())

    assert vus == [(EN_ATTENTE, 1)]
    assert livraison.statut == LIVREE


@pytest.mark.parametrize(("statut", "attendu"), [(429, True), (500, True), (599, True), (400, False), (404, False)])
def test_est_reessayable(statut, attendu):
    assert est_reessayable(statut) is attendu


def test_registre_ne_cree_qu_une_livraison_par_event_id():
    registre = Registre()

    premiere, nouvelle = registre.enregistrer_si_nouveau("evt-1")
    seconde, encore_nouvelle = registre.enregistrer_si_nouveau("evt-1")

    assert (nouvelle, encore_nouvelle) == (True, False)
    assert seconde is premiere
    assert registre.obtenir("evt-1").en_dict() == {
        "event_id": "evt-1", "status": "pending", "attempts": 0, "last_error": None,
    }
    assert registre.obtenir("inconnu") is None
