"""Commande : python -m i3_flux ENTREE [--sortie DOSSIER] [--details]"""

import argparse
import sys
from pathlib import Path

from i3_flux.pipeline import FICHIER_ACCEPTES, FICHIER_REJETS, FICHIER_STATS, REJET, executer


def construire_parseur():
    parseur = argparse.ArgumentParser(
        prog="python -m i3_flux",
        description="Valide, normalise et déduplique un fichier NDJSON de séances.",
    )
    parseur.add_argument("entree", type=Path, help="fichier NDJSON à traiter")
    parseur.add_argument(
        "--sortie",
        type=Path,
        default=Path("sortie"),
        help="dossier où écrire acceptes.ndjson, rejets.ndjson et stats.json (défaut : sortie)",
    )
    parseur.add_argument("--details", action="store_true", help="affiche la décision prise pour chaque ligne")
    return parseur


def afficher_resultat(resultat):
    ligne = f"ligne {resultat.source_line:>3}  {resultat.statut:<8}  {resultat.id or '-'}"
    if resultat.statut == REJET:
        ligne += f"  ({resultat.motif})"
    print(ligne)


def main(argv=None):
    parseur = construire_parseur()
    arguments = parseur.parse_args(argv)
    if not arguments.entree.is_file():
        parseur.error(f"fichier d'entrée introuvable : {arguments.entree}")

    try:
        stats = executer(
            arguments.entree,
            arguments.sortie,
            observateur=afficher_resultat if arguments.details else None,
        )
    except OSError as erreur:
        print(f"erreur : {erreur}", file=sys.stderr)
        return 1

    print("lus={lus} acceptes={acceptes} rejets={rejets} doublons={doublons}".format(**stats.en_dict()))
    for nom in (FICHIER_ACCEPTES, FICHIER_REJETS, FICHIER_STATS):
        print(arguments.sortie / nom)
    return 0


if __name__ == "__main__":
    sys.exit(main())
