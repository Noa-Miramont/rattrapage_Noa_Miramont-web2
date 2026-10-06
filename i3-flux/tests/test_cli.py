import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RACINE_MODULE = Path(__file__).resolve().parents[1]
JEU_FOURNI = RACINE_MODULE / "data" / "seances.ndjson"
SORTIES = ("acceptes.ndjson", "rejets.ndjson", "stats.json")


def lancer(*arguments, fuseau=None):
    env = dict(os.environ)
    if fuseau is not None:
        env["TZ"] = fuseau
    return subprocess.run(
        [sys.executable, "-m", "i3_flux", *map(str, arguments)],
        cwd=RACINE_MODULE,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_commande_sur_le_jeu_fourni(tmp_path):
    execution = lancer(JEU_FOURNI, "--sortie", tmp_path)

    assert execution.returncode == 0, execution.stderr
    assert execution.stdout.splitlines()[0] == "lus=12 acceptes=6 rejets=4 doublons=2"
    assert json.loads((tmp_path / "stats.json").read_text()) == {
        "lus": 12, "acceptes": 6, "rejets": 4, "doublons": 2,
    }
    assert len((tmp_path / "acceptes.ndjson").read_text(encoding="utf-8").splitlines()) == 6
    assert len((tmp_path / "rejets.ndjson").read_text(encoding="utf-8").splitlines()) == 4


def test_option_details_trace_chaque_ligne(tmp_path):
    execution = lancer(JEU_FOURNI, "--sortie", tmp_path, "--details")
    lignes = execution.stdout.splitlines()

    assert execution.returncode == 0, execution.stderr
    assert lignes[3] == "ligne   4  doublon   s01"
    assert lignes[6] == "ligne   7  rejet     bad1  (title vide)"
    assert lignes[11] == "ligne  12  rejet     -  (JSON malformé)"
    assert lignes[12] == "lus=12 acceptes=6 rejets=4 doublons=2"


@pytest.mark.parametrize("fuseau", ["UTC", "Pacific/Kiritimati", "America/Anchorage"])
def test_resultat_independant_du_fuseau_de_la_machine(tmp_path, fuseau):
    reference = tmp_path / "reference"
    assert lancer(JEU_FOURNI, "--sortie", reference, fuseau="Europe/Paris").returncode == 0
    assert lancer(JEU_FOURNI, "--sortie", tmp_path / fuseau, fuseau=fuseau).returncode == 0

    for nom in SORTIES:
        assert (tmp_path / fuseau / nom).read_bytes() == (reference / nom).read_bytes()


def test_fichier_vide(tmp_path):
    entree = tmp_path / "vide.ndjson"
    entree.write_bytes(b"")

    execution = lancer(entree, "--sortie", tmp_path / "sortie")

    assert execution.returncode == 0, execution.stderr
    assert execution.stdout.splitlines()[0] == "lus=0 acceptes=0 rejets=0 doublons=0"


def test_dossier_de_sortie_cree_si_absent(tmp_path):
    sortie = tmp_path / "a" / "b"

    assert lancer(JEU_FOURNI, "--sortie", sortie).returncode == 0
    assert sorted(p.name for p in sortie.iterdir()) == sorted(SORTIES)


def test_entree_introuvable(tmp_path):
    execution = lancer(tmp_path / "absent.ndjson", "--sortie", tmp_path / "sortie")

    assert execution.returncode == 2
    assert "introuvable" in execution.stderr
    assert not (tmp_path / "sortie").exists()
