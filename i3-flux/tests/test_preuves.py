from pathlib import Path

import pytest

from i3_flux.pipeline import executer

RACINE_MODULE = Path(__file__).resolve().parents[1]
PREUVES = RACINE_MODULE.parent / "preuves" / "i3"


@pytest.mark.parametrize("nom", ["acceptes.ndjson", "rejets.ndjson", "stats.json"])
def test_preuve_versionnee_identique_a_une_execution_reelle(tmp_path, nom):
    executer(RACINE_MODULE / "data" / "seances.ndjson", tmp_path)

    assert (tmp_path / nom).read_bytes() == (PREUVES / nom).read_bytes()
