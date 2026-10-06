import json
from pathlib import Path

import pytest

JEU_FOURNI = Path(__file__).resolve().parents[1] / "data" / "seances.ndjson"

CLES = ("id", "date", "period", "group", "mode", "title", "domain", "teacherId", "status")

# Les deux tableaux du sujet, fusionnés ligne par ligne.
TABLEAUX_DU_SUJET = [
    ("s01", "19/10/2026", "matin", "A", "DG", "React composants", "web", "t1", "confirme"),
    ("s02", "2026-10-19", "am", "B", "DG", "React événements", "web", "t2", "confirmed"),
    ("s03", "2026-10-19", "pm", "Promotion", "CE", "Données et SQL", "data", "t1", "confirmed"),
    ("s01", "2026-10-19", "am", "A", "DG", "Copie React", "web", "t1", "confirmed"),
    ("s04", "20/10/2026", "matin", "A", "DG", "Authentification", "cyber", "t2", "propose"),
    ("s05", "2026-10-20", "am", "B", "DG", "Revue de projet", "projet", "t3", "proposed"),
    ("bad1", "2026-10-20", "pm", "Promotion", "AUTO", "", "projet", None, "proposed"),
    ("bad2", "2026-02-30", "am", "A", "DG", "Date invalide", "web", "t1", "proposed"),
    ("bad3", "2026-10-20", "soir", "A", "DG", "Période invalide", "web", "t1", "proposed"),
    ("s02", "2026-10-19", "am", "B", "DG", "Copie B", "web", "t2", "confirmed"),
    ("s06", "2026-10-20", "après-midi", "Promotion", "AUTO", "Travail autonome", "projet", None, "proposed"),
]
LIGNE_12 = '{"id":"bad4","title":"JSON tronqué"'


def lignes_du_fichier():
    return JEU_FOURNI.read_text(encoding="utf-8").splitlines()


def test_le_fichier_contient_douze_lignes():
    assert len(lignes_du_fichier()) == 12


@pytest.mark.parametrize("numero", range(1, 12))
def test_lignes_1_a_11_conformes_aux_tableaux(numero):
    objet = json.loads(lignes_du_fichier()[numero - 1])

    assert tuple(objet) == CLES
    assert tuple(objet.values()) == TABLEAUX_DU_SUJET[numero - 1]


def test_ligne_12_recopiee_telle_quelle_et_malformee():
    ligne = lignes_du_fichier()[11]

    assert ligne == LIGNE_12
    with pytest.raises(json.JSONDecodeError):
        json.loads(ligne)
