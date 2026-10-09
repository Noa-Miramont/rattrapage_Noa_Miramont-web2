"""Mesure de l'usage mémoire du pipeline : python -m i3_flux.mesure_memoire

Pic d'allocation Python (tracemalloc) pendant `executer`, d'abord avec 10 id distincts
quel que soit le nombre de lignes, puis avec un id différent par ligne.
"""

import json
import tempfile
import tracemalloc
from pathlib import Path

from i3_flux.pipeline import executer

NOMBRES_DE_LIGNES = (10_000, 100_000, 200_000)


def generer(chemin, lignes, ids_distincts):
    with open(chemin, "w", encoding="utf-8") as fichier:
        for numero in range(lignes):
            seance = {
                "id": f"s{numero % ids_distincts}",
                "date": "19/10/2026",
                "period": "matin",
                "group": "A",
                "mode": "DG",
                "title": "React composants",
                "domain": "web",
                "teacherId": "t1",
                "status": "confirme",
            }
            fichier.write(json.dumps(seance, ensure_ascii=False) + "\n")


def pic_memoire(entree, sortie):
    tracemalloc.start()
    try:
        executer(entree, sortie)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def main():
    print(f"{'lignes':>8}  {'fichier':>9}  {'id distincts':>12}  {'pic mémoire':>11}")
    with tempfile.TemporaryDirectory() as dossier:
        dossier = Path(dossier)
        for lignes in NOMBRES_DE_LIGNES:
            for ids_distincts in (10, lignes):
                entree = dossier / "entree.ndjson"
                generer(entree, lignes, ids_distincts)
                pic = pic_memoire(entree, dossier / "sortie")
                taille = entree.stat().st_size
                print(f"{lignes:>8}  {taille / 2**20:>6.1f} Mo  {ids_distincts:>12}  {pic / 2**10:>8.0f} Ko")


if __name__ == "__main__":
    main()
