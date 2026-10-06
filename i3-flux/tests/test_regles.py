import unicodedata

import pytest

from i3_flux.regles import (
    SeanceInvalide,
    normaliser_date,
    normaliser_periode,
    normaliser_statut,
    valider_seance,
)


def seance(**modifications):
    base = {
        "id": "s01",
        "date": "2026-10-19",
        "period": "am",
        "group": "A",
        "mode": "DG",
        "title": "React composants",
        "domain": "web",
        "teacherId": "t1",
        "status": "confirmed",
    }
    base.update(modifications)
    return base


def erreurs_de(objet):
    with pytest.raises(SeanceInvalide) as exc:
        valider_seance(objet)
    return exc.value.erreurs


@pytest.mark.parametrize(
    ("brute", "attendue"),
    [
        ("2026-10-19", "2026-10-19"),
        ("19/10/2026", "2026-10-19"),
        ("2028-02-29", "2028-02-29"),
        ("29/02/2028", "2028-02-29"),
    ],
)
def test_date_acceptee_et_normalisee(brute, attendue):
    assert normaliser_date(brute) == attendue


@pytest.mark.parametrize(
    "brute",
    [
        "2026-02-30",
        "30/02/2026",
        "2026-02-29",
        "2026-13-01",
        "2026-00-10",
        "2026/10/19",
        "19-10-2026",
        "2026-1-9",
        "20261019",
        " 2026-10-19",
        "2026-10-19T08:00:00",
        "٢٠٢٦-١٠-١٩",
        20261019,
        None,
    ],
)
def test_date_refusee(brute):
    assert normaliser_date(brute) is None


@pytest.mark.parametrize(
    ("brute", "attendue"),
    [
        ("matin", "am"),
        ("am", "am"),
        ("après-midi", "pm"),
        ("apres-midi", "pm"),
        ("pm", "pm"),
        (unicodedata.normalize("NFD", "après-midi"), "pm"),
    ],
)
def test_periode_normalisee(brute, attendue):
    assert normaliser_periode(brute) == attendue


@pytest.mark.parametrize("brute", ["soir", "Matin", "AM", "", None, 1, ["am"]])
def test_periode_refusee(brute):
    assert normaliser_periode(brute) is None


@pytest.mark.parametrize(
    ("brut", "attendu"),
    [
        ("propose", "proposed"),
        ("proposed", "proposed"),
        ("confirme", "confirmed"),
        ("confirmed", "confirmed"),
    ],
)
def test_statut_normalise(brut, attendu):
    assert normaliser_statut(brut) == attendu


@pytest.mark.parametrize("brut", ["confirmé", "draft", "", None, {"status": "proposed"}])
def test_statut_refuse(brut):
    assert normaliser_statut(brut) is None


def test_seance_valide_normalisee_dans_l_ordre_des_champs():
    brute = seance(date="19/10/2026", period="matin", status="confirme")

    assert valider_seance(brute) == seance()
    assert list(valider_seance(brute)) == [
        "id", "date", "period", "group", "mode", "title", "domain", "teacherId", "status",
    ]


def test_cle_inconnue_ignoree():
    assert valider_seance(seance(salle="B12")) == seance()


@pytest.mark.parametrize("groupe", ["A", "B", "Promotion"])
def test_groupes_acceptes(groupe):
    assert valider_seance(seance(group=groupe))["group"] == groupe


@pytest.mark.parametrize(
    ("champ", "valeur", "motif"),
    [
        ("group", "C", "group invalide: C"),
        ("group", "promotion", "group invalide: promotion"),
        ("mode", "auto", "mode invalide: auto"),
        ("mode", None, "mode invalide: null"),
        ("teacherId", "t4", "teacherId invalide: t4"),
        ("teacherId", "", "teacherId invalide: "),
        ("teacherId", 1, "teacherId invalide: 1"),
        ("date", "2026-02-30", "date invalide: 2026-02-30"),
        ("period", "soir", "period invalide: soir"),
        ("status", "annule", "status invalide: annule"),
        ("id", "", "id vide"),
        ("id", 7, "id doit être une chaîne"),
        ("title", "", "title vide"),
        ("title", "   ", "title vide"),
        ("domain", None, "domain doit être une chaîne"),
    ],
)
def test_valeur_invalide_rejetee_avec_motif(champ, valeur, motif):
    assert erreurs_de(seance(**{champ: valeur})) == [motif]


def test_champ_manquant():
    objet = seance()
    del objet["teacherId"]
    del objet["status"]

    assert erreurs_de(objet) == ["teacherId manquant", "status manquant"]


def test_toutes_les_erreurs_sont_reunies_dans_l_ordre_des_champs():
    objet = seance(date="2026-02-30", period="soir", title="")

    assert erreurs_de(objet) == ["date invalide: 2026-02-30", "period invalide: soir", "title vide"]


def test_auto_valide_sans_formateur_et_propose():
    resultat = valider_seance(seance(mode="AUTO", teacherId=None, status="propose"))

    assert (resultat["teacherId"], resultat["status"]) == (None, "proposed")


def test_auto_avec_formateur_rejete():
    assert erreurs_de(seance(mode="AUTO", teacherId="t1", status="proposed")) == [
        "mode AUTO exige teacherId null"
    ]


def test_auto_confirme_rejete():
    assert erreurs_de(seance(mode="AUTO", teacherId=None, status="confirmed")) == [
        "mode AUTO exige status proposed",
        "status confirmed exige un formateur",
    ]


def test_confirme_sans_formateur_rejete():
    assert erreurs_de(seance(mode="CE", teacherId=None, status="confirme")) == [
        "status confirmed exige un formateur"
    ]


def test_propose_sans_formateur_accepte_hors_auto():
    assert valider_seance(seance(mode="DG", teacherId=None, status="proposed"))["teacherId"] is None


def test_regle_croisee_ignoree_si_le_champ_est_deja_invalide():
    assert erreurs_de(seance(mode="AUTO", teacherId="t9", status="proposed")) == [
        "teacherId invalide: t9"
    ]
