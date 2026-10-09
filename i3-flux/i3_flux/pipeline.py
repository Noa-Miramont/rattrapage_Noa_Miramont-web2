"""Pipeline I3 : lecture -> validation -> normalisation -> déduplication -> sortie.

Usage mémoire
-------------
Le fichier d'entrée est itéré ligne par ligne et chaque résultat est écrit aussitôt dans
son fichier de sortie : une seule ligne est en mémoire à la fois, quelle que soit la
taille du fichier. La seule structure qui grandit est `ids_acceptes`, indispensable à la
déduplication. Sa taille suit le nombre d'id distincts acceptés, pas le nombre de lignes :
rejets et doublons n'y ajoutent rien. Limite : une ligne isolée très longue est chargée
entière avant d'être décodée.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from i3_flux.regles import SeanceInvalide, valider_seance

FICHIER_ACCEPTES = "acceptes.ndjson"
FICHIER_REJETS = "rejets.ndjson"
FICHIER_STATS = "stats.json"

ACCEPTE = "accepte"
REJET = "rejet"
DOUBLON = "doublon"


class LigneIllisible(ValueError):
    """La ligne ne contient pas un objet JSON exploitable."""


@dataclass(frozen=True)
class Resultat:
    source_line: int
    statut: str
    id: str | None = None
    seance: dict | None = None
    motif: str | None = None


@dataclass
class Stats:
    lus: int = 0
    acceptes: int = 0
    rejets: int = 0
    doublons: int = 0

    def compter(self, resultat):
        self.lus += 1
        if resultat.statut == ACCEPTE:
            self.acceptes += 1
        elif resultat.statut == REJET:
            self.rejets += 1
        else:
            self.doublons += 1

    def verifier_invariant(self):
        if self.lus != self.acceptes + self.rejets + self.doublons:
            raise RuntimeError(f"invariant rompu : {self.en_dict()}")

    def en_dict(self):
        return {"lus": self.lus, "acceptes": self.acceptes, "rejets": self.rejets, "doublons": self.doublons}


def _refuser_constante(nom):
    raise ValueError(f"{nom} n'est pas du JSON standard")


def decoder_ligne(brut, premiere=False):
    """Octets d'une ligne -> dict, ou LigneIllisible avec le motif du rejet."""
    try:
        texte = brut.decode("utf-8")
    except UnicodeDecodeError:
        raise LigneIllisible("encodage UTF-8 invalide") from None
    if premiere:
        texte = texte.removeprefix("\ufeff")
    texte = texte.rstrip("\r\n")
    if not texte.strip():
        raise LigneIllisible("ligne vide")
    try:
        # NaN et Infinity sont acceptés par défaut par le module json mais ne sont pas du JSON.
        objet = json.loads(texte, parse_constant=_refuser_constante)
    except (ValueError, RecursionError):
        raise LigneIllisible("JSON malformé") from None
    if not isinstance(objet, dict):
        raise LigneIllisible("objet JSON attendu")
    return objet


def _id_lisible(objet):
    if isinstance(objet, dict) and isinstance(objet.get("id"), str):
        return objet["id"]
    return None


def traiter(lignes):
    """Produit un Resultat par ligne, dans l'ordre. `lignes` est un itérable d'octets.

    La validation précède la déduplication : une ligne invalide est un rejet, jamais un
    doublon, et seule la première occurrence valide d'un id est acceptée.
    """
    ids_acceptes = set()
    for numero, brut in enumerate(lignes, start=1):
        objet = None
        try:
            objet = decoder_ligne(brut, premiere=numero == 1)
            seance = valider_seance(objet)
        except (LigneIllisible, SeanceInvalide) as erreur:
            yield Resultat(numero, REJET, id=_id_lisible(objet), motif=str(erreur))
            continue
        if seance["id"] in ids_acceptes:
            yield Resultat(numero, DOUBLON, id=seance["id"])
        else:
            ids_acceptes.add(seance["id"])
            yield Resultat(numero, ACCEPTE, id=seance["id"], seance=seance)


def _ligne_json(objet):
    return json.dumps(objet, ensure_ascii=False, separators=(",", ":")) + "\n"


def executer(entree, dossier_sortie, observateur=None):
    """Traite le fichier `entree` et écrit acceptes.ndjson, rejets.ndjson et stats.json.

    Les sorties sont d'abord écrites en .tmp puis renommées une fois l'invariant vérifié :
    un échec en cours de route ne laisse jamais un mélange d'anciennes et de nouvelles sorties.
    `observateur`, s'il est fourni, reçoit chaque Resultat (utilisé par le mode --details).
    """
    dossier = Path(dossier_sortie)
    dossier.mkdir(parents=True, exist_ok=True)
    finaux = [dossier / nom for nom in (FICHIER_ACCEPTES, FICHIER_REJETS, FICHIER_STATS)]
    temporaires = [chemin.with_name(chemin.name + ".tmp") for chemin in finaux]
    stats = Stats()
    try:
        with (
            open(entree, "rb") as lecture,
            open(temporaires[0], "w", encoding="utf-8", newline="\n") as acceptes,
            open(temporaires[1], "w", encoding="utf-8", newline="\n") as rejets,
        ):
            for resultat in traiter(lecture):
                stats.compter(resultat)
                if observateur is not None:
                    observateur(resultat)
                if resultat.statut == ACCEPTE:
                    acceptes.write(_ligne_json({"source_line": resultat.source_line, **resultat.seance}))
                elif resultat.statut == REJET:
                    rejets.write(
                        _ligne_json({"source_line": resultat.source_line, "id": resultat.id, "motif": resultat.motif})
                    )
        stats.verifier_invariant()
        temporaires[2].write_text(json.dumps(stats.en_dict(), indent=2) + "\n", encoding="utf-8", newline="\n")
        for temporaire, final in zip(temporaires, finaux):
            os.replace(temporaire, final)
    finally:
        for temporaire in temporaires:
            temporaire.unlink(missing_ok=True)
    return stats
