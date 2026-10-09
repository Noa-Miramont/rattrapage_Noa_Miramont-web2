import json
from pathlib import Path

import pytest

from i3_flux.pipeline import ACCEPTE, DOUBLON, REJET, executer, traiter

JEU_FOURNI = Path(__file__).resolve().parents[1] / "data" / "seances.ndjson"


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


def en_lignes(*elements):
    """Objets -> lignes JSON encodées ; chaînes et octets passent tels quels (lignes brutes)."""
    lignes = []
    for element in elements:
        if isinstance(element, dict):
            element = json.dumps(element, ensure_ascii=False)
        if isinstance(element, str):
            element = element.encode("utf-8")
        lignes.append(element + b"\n")
    return lignes


def statuts(resultats):
    return [(r.source_line, r.statut) for r in resultats]


def lire_ndjson(chemin):
    return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines()]


def test_ligne_valide_acceptee_et_normalisee():
    [resultat] = traiter(en_lignes(seance(date="19/10/2026", period="matin", status="confirme")))

    assert resultat.statut == ACCEPTE
    assert resultat.source_line == 1
    assert resultat.seance == seance()


def test_ligne_invalide_rejetee_sans_interrompre_les_suivantes():
    resultats = list(traiter(en_lignes(seance(id="a"), seance(id="b", period="soir"), seance(id="c"))))

    assert statuts(resultats) == [(1, ACCEPTE), (2, REJET), (3, ACCEPTE)]
    assert resultats[1].id == "b"
    assert resultats[1].motif == "period invalide: soir"


def test_doublon_seule_la_premiere_occurrence_est_retenue():
    resultats = list(traiter(en_lignes(seance(title="Original"), seance(title="Copie"))))

    assert statuts(resultats) == [(1, ACCEPTE), (2, DOUBLON)]
    assert resultats[0].seance["title"] == "Original"
    assert resultats[1].id == "s01"


def test_doublon_detecte_apres_normalisation_des_formats():
    resultats = traiter(en_lignes(seance(date="19/10/2026"), seance(date="2026-10-19")))

    assert statuts(resultats) == [(1, ACCEPTE), (2, DOUBLON)]


def test_validation_avant_deduplication_premiere_occurrence_invalide():
    resultats = traiter(en_lignes(seance(id="s07", date="2026-02-30"), seance(id="s07")))

    assert statuts(resultats) == [(1, REJET), (2, ACCEPTE)]


def test_occurrence_invalide_apres_une_valide_est_un_rejet_et_non_un_doublon():
    resultats = traiter(en_lignes(seance(), seance(group="Z")))

    assert statuts(resultats) == [(1, ACCEPTE), (2, REJET)]


def test_json_malforme_rejete_puis_la_ligne_suivante_est_traitee():
    resultats = list(traiter(en_lignes('{"id":"bad4","title":"JSON tronqué"', seance())))

    assert statuts(resultats) == [(1, REJET), (2, ACCEPTE)]
    assert resultats[0].motif == "JSON malformé"
    assert resultats[0].id is None


@pytest.mark.parametrize("brute", ["[1, 2]", '"texte"', "42", "null", "true"])
def test_json_valide_mais_pas_un_objet(brute):
    [resultat] = traiter(en_lignes(brute))

    assert (resultat.statut, resultat.motif) == (REJET, "objet JSON attendu")


@pytest.mark.parametrize("constante", ["NaN", "Infinity", "-Infinity"])
def test_constantes_non_standard_refusees(constante):
    [resultat] = traiter(en_lignes('{"id": "s01", "x": ' + constante + "}"))

    assert (resultat.statut, resultat.motif) == (REJET, "JSON malformé")


@pytest.mark.parametrize("brute", ["", "   ", "\t"])
def test_ligne_vide_comptee_comme_rejet(brute):
    resultats = list(traiter(en_lignes(brute, seance())))

    assert statuts(resultats) == [(1, REJET), (2, ACCEPTE)]
    assert resultats[0].motif == "ligne vide"


def test_utf8_invalide_rejete_sans_interrompre():
    resultats = list(traiter(en_lignes(b'{"id": "\xff"}', seance())))

    assert statuts(resultats) == [(1, REJET), (2, ACCEPTE)]
    assert resultats[0].motif == "encodage UTF-8 invalide"


def test_bom_et_fins_de_ligne_windows_toleres():
    premiere = b"\xef\xbb\xbf" + json.dumps(seance(id="a")).encode() + b"\r\n"
    seconde = json.dumps(seance(id="b")).encode() + b"\r\n"

    assert statuts(traiter([premiere, seconde])) == [(1, ACCEPTE), (2, ACCEPTE)]


def test_derniere_ligne_sans_retour_chariot_lue():
    assert statuts(traiter([json.dumps(seance()).encode()])) == [(1, ACCEPTE)]


def test_fichier_vide(tmp_path):
    entree = tmp_path / "vide.ndjson"
    entree.write_bytes(b"")

    stats = executer(entree, tmp_path / "sortie")

    assert stats.en_dict() == {"lus": 0, "acceptes": 0, "rejets": 0, "doublons": 0}
    assert (tmp_path / "sortie" / "acceptes.ndjson").read_bytes() == b""
    assert (tmp_path / "sortie" / "rejets.ndjson").read_bytes() == b""
    assert json.loads((tmp_path / "sortie" / "stats.json").read_text()) == stats.en_dict()


def test_jeu_fourni_resultat_attendu(tmp_path):
    stats = executer(JEU_FOURNI, tmp_path)

    assert stats.en_dict() == {"lus": 12, "acceptes": 6, "rejets": 4, "doublons": 2}
    assert stats.lus == stats.acceptes + stats.rejets + stats.doublons
    assert json.loads((tmp_path / "stats.json").read_text()) == stats.en_dict()

    acceptes = lire_ndjson(tmp_path / "acceptes.ndjson")
    assert [(a["source_line"], a["id"]) for a in acceptes] == [
        (1, "s01"), (2, "s02"), (3, "s03"), (5, "s04"), (6, "s05"), (11, "s06"),
    ]
    assert acceptes[0] == {"source_line": 1, **seance()}
    assert acceptes[-1] == {
        "source_line": 11, "id": "s06", "date": "2026-10-20", "period": "pm", "group": "Promotion",
        "mode": "AUTO", "title": "Travail autonome", "domain": "projet", "teacherId": None, "status": "proposed",
    }

    assert lire_ndjson(tmp_path / "rejets.ndjson") == [
        {"source_line": 7, "id": "bad1", "motif": "title vide"},
        {"source_line": 8, "id": "bad2", "motif": "date invalide: 2026-02-30"},
        {"source_line": 9, "id": "bad3", "motif": "period invalide: soir"},
        {"source_line": 12, "id": None, "motif": "JSON malformé"},
    ]


def test_jeu_fourni_doublons_lignes_4_et_10():
    with open(JEU_FOURNI, "rb") as fichier:
        doublons = [(r.source_line, r.id) for r in traiter(fichier) if r.statut == DOUBLON]

    assert doublons == [(4, "s01"), (10, "s02")]


def test_meme_fichier_meme_resultat_octet_pour_octet(tmp_path):
    executer(JEU_FOURNI, tmp_path / "premier")
    executer(JEU_FOURNI, tmp_path / "second")

    for nom in ("acceptes.ndjson", "rejets.ndjson", "stats.json"):
        assert (tmp_path / "premier" / nom).read_bytes() == (tmp_path / "second" / nom).read_bytes()


def test_sorties_precedentes_remplacees_sans_fichier_temporaire(tmp_path):
    (tmp_path / "acceptes.ndjson").write_text("ancienne sortie\n")

    executer(JEU_FOURNI, tmp_path)

    assert "ancienne sortie" not in (tmp_path / "acceptes.ndjson").read_text()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["acceptes.ndjson", "rejets.ndjson", "stats.json"]


def test_observateur_recoit_chaque_ligne(tmp_path):
    vus = []

    executer(JEU_FOURNI, tmp_path, observateur=vus.append)

    assert [r.source_line for r in vus] == list(range(1, 13))
