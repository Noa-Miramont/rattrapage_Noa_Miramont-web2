import json
import time

import pytest
from fastapi.testclient import TestClient

from i4_webhooks.partenaire import creer_app

CORPS = json.dumps({"event_id": "evt-1", "session": {"id": "s01"}})


def client(mode="ok", **options):
    return TestClient(creer_app(mode=mode, **options))


def poster(partenaire, cle="evt-1"):
    en_tetes = {"Content-Type": "application/json"}
    if cle is not None:
        en_tetes["Idempotency-Key"] = cle
    return partenaire.post("/tickets", content=CORPS, headers=en_tetes)


def test_ok_cree_un_ticket():
    partenaire = client("ok")

    reponse = poster(partenaire)

    assert reponse.status_code == 201
    assert reponse.json() == {"ticket_id": "T-0001", "idempotency_key": "evt-1", "session_id": "s01"}


def test_meme_idempotency_key_meme_ticket_sans_doublon():
    partenaire = client("ok")

    premier = poster(partenaire)
    second = poster(partenaire)

    assert second.status_code == 200
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.json() == premier.json()
    assert len(partenaire.get("/tickets").json()) == 1


def test_cles_differentes_tickets_differents():
    partenaire = client("ok")

    poster(partenaire, "evt-1")
    poster(partenaire, "evt-2")

    assert [t["ticket_id"] for t in partenaire.get("/tickets").json()] == ["T-0001", "T-0002"]


def test_idempotency_key_obligatoire():
    reponse = poster(client("ok"), cle=None)

    assert reponse.status_code == 400
    assert "Idempotency-Key" in reponse.json()["detail"]


def test_flaky_premiere_tentative_503_puis_succes():
    partenaire = client("flaky")

    assert poster(partenaire).status_code == 503
    assert poster(partenaire).status_code == 201
    assert poster(partenaire, "evt-2").status_code == 503


def test_appels_comptes_par_idempotency_key():
    partenaire = client("flaky")

    poster(partenaire, "evt-1")
    poster(partenaire, "evt-1")
    poster(partenaire, "evt-2")

    assert partenaire.get("/appels").json() == {"evt-1": 2, "evt-2": 1}
    assert len(partenaire.get("/tickets").json()) == 1


def test_down_503_permanent_sans_ticket():
    partenaire = client("down")

    assert [poster(partenaire).status_code for _ in range(4)] == [503, 503, 503, 503]
    assert partenaire.get("/tickets").json() == []


def test_reject_400_permanent_sans_ticket():
    partenaire = client("reject")

    assert [poster(partenaire).status_code for _ in range(3)] == [400, 400, 400]
    assert partenaire.get("/tickets").json() == []


def test_slow_repond_apres_le_delai():
    partenaire = client("slow", delai_slow_s=0.2)

    debut = time.monotonic()
    reponse = poster(partenaire)

    assert reponse.status_code == 201
    assert time.monotonic() - debut >= 0.2


def test_delai_slow_par_defaut_de_3_secondes():
    from i4_webhooks.partenaire import DELAI_SLOW_S

    assert DELAI_SLOW_S == 3.0


def test_changement_de_mode_a_chaud():
    partenaire = client("down")

    assert partenaire.put("/mode", json={"mode": "ok"}).json() == {"mode": "ok"}
    assert partenaire.get("/health").json() == {"status": "ok", "mode": "ok"}
    assert poster(partenaire).status_code == 201


def test_mode_inconnu_refuse():
    assert client("ok").put("/mode", json={"mode": "panne"}).status_code == 422
    with pytest.raises(ValueError, match="mode inconnu"):
        creer_app(mode="panne")


def test_mode_initial_lu_dans_l_environnement(monkeypatch):
    monkeypatch.setenv("PARTENAIRE_MODE", "reject")

    assert TestClient(creer_app()).get("/health").json()["mode"] == "reject"


def test_corps_illisible_n_empeche_pas_le_ticket():
    reponse = client("ok").post("/tickets", content=b"pas du json", headers={"Idempotency-Key": "evt-9"})

    assert reponse.status_code == 201
    assert reponse.json()["session_id"] is None
