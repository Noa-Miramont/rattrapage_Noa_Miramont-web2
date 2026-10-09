import pytest

from fabriques import evenement, octets, seance
from i4_webhooks.modeles import EvenementInvalide, analyser_evenement


def erreurs_de(corps):
    with pytest.raises(EvenementInvalide) as exc:
        analyser_evenement(corps)
    return exc.value.erreurs


def test_evenement_valide():
    resultat = analyser_evenement(octets(evenement()))

    assert resultat.event_id == "evt-1"
    assert resultat.session.teacherId == "t1"


@pytest.mark.parametrize(
    "instant",
    ["2026-10-19T06:30:00Z", "2026-10-19T08:30:00+02:00", "2026-10-19T08:30:00.123-05:00", "2026-10-19 08:30:00+00:00"],
)
def test_occurred_at_avec_fuseau_accepte(instant):
    assert analyser_evenement(octets(evenement(occurred_at=instant))).occurred_at == instant


@pytest.mark.parametrize("instant", ["2026-10-19T08:30:00", "2026-10-19"])
def test_occurred_at_sans_fuseau_refuse(instant):
    assert erreurs_de(octets(evenement(occurred_at=instant))) == [
        "occurred_at: Value error, le fuseau est obligatoire (Z ou ±HH:MM)"
    ]


@pytest.mark.parametrize("instant", ["19/10/2026 08:30", "hier", "", 1790000000])
def test_occurred_at_non_iso_refuse(instant):
    assert erreurs_de(octets(evenement(occurred_at=instant)))[0].startswith("occurred_at:")


@pytest.mark.parametrize("event_id", ["", "   ", 42, None])
def test_event_id_non_vide_obligatoire(event_id):
    assert erreurs_de(octets(evenement(event_id=event_id)))[0].startswith("event_id:")


@pytest.mark.parametrize("type_", ["session.created", "SESSION.UPDATED", "", None])
def test_type_session_updated_obligatoire(type_):
    assert erreurs_de(octets(evenement(type=type_)))[0].startswith("type:")


@pytest.mark.parametrize("champ", ["event_id", "type", "occurred_at", "session"])
def test_champ_obligatoire(champ):
    objet = evenement()
    del objet[champ]

    assert erreurs_de(octets(objet)) == [f"{champ}: Field required"]


@pytest.mark.parametrize(
    ("champ", "valeur"),
    [
        ("date", "19/10/2026"),
        ("date", "2026-02-30"),
        ("period", "matin"),
        ("status", "confirme"),
        ("group", "C"),
        ("mode", "auto"),
        ("teacherId", "t4"),
        ("title", ""),
        ("title", 42),
        ("domain", None),
        ("id", " "),
    ],
)
def test_session_non_conforme_refusee(champ, valeur):
    assert erreurs_de(octets(evenement(session=seance(**{champ: valeur}))))[0].startswith(f"session.{champ}:")


def test_auto_avec_formateur_refuse():
    corps = octets(evenement(session=seance(mode="AUTO", teacherId="t1", status="proposed")))

    assert erreurs_de(corps) == ["session: Value error, mode AUTO exige teacherId null et status proposed"]


def test_confirme_sans_formateur_refuse():
    corps = octets(evenement(session=seance(teacherId=None, status="confirmed")))

    assert erreurs_de(corps) == ["session: Value error, status confirmed exige un formateur"]


def test_auto_sans_formateur_et_propose_accepte():
    corps = octets(evenement(session=seance(mode="AUTO", teacherId=None, status="proposed")))

    assert analyser_evenement(corps).session.mode == "AUTO"


def test_teacher_id_null_doit_etre_explicite():
    session = seance()
    del session["teacherId"]

    assert erreurs_de(octets(evenement(session=session))) == ["session.teacherId: Field required"]


@pytest.mark.parametrize(
    "corps",
    [b'{"event_id":"evt-1"', b"", b"pas du json", b"\xff\xfe", b"[1, 2]", b'"texte"', b"null"],
)
def test_corps_qui_n_est_pas_un_objet_json_refuse(corps):
    assert erreurs_de(corps)


def test_cle_inconnue_ignoree():
    assert analyser_evenement(octets(evenement(source="planning", session=seance(salle="B12")))).event_id == "evt-1"


def test_toutes_les_erreurs_sont_listees():
    corps = octets(evenement(type="autre", session=seance(date="2026-02-30", period="soir")))

    assert [erreur.split(":")[0] for erreur in erreurs_de(corps)] == ["type", "session.date", "session.period"]
