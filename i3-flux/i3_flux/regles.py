"""Règles métier d'une séance : validation et normalisation d'un objet JSON déjà décodé.

Fonctions pures, sans entrée/sortie ni horloge : le résultat ne dépend que de l'objet reçu.
"""

import json
import re
import unicodedata
from datetime import date

CHAMPS = ("id", "date", "period", "group", "mode", "title", "domain", "teacherId", "status")
CHAMPS_TEXTE = ("id", "title", "domain")

PERIODES = {"matin": "am", "am": "am", "après-midi": "pm", "apres-midi": "pm", "pm": "pm"}
STATUTS = {"propose": "proposed", "proposed": "proposed", "confirme": "confirmed", "confirmed": "confirmed"}
GROUPES = ("A", "B", "Promotion")
MODES = ("DG", "CE", "AUTO")
FORMATEURS = ("t1", "t2", "t3")

# [0-9] et non \d : \d accepterait aussi les chiffres non ASCII (arabes, devanagari...).
_DATE_ISO = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_DATE_FR = re.compile(r"([0-9]{2})/([0-9]{2})/([0-9]{4})")


class SeanceInvalide(ValueError):
    """Objet qui ne respecte pas les règles ; `erreurs` liste tous les motifs, dans l'ordre des champs."""

    def __init__(self, erreurs):
        super().__init__("; ".join(erreurs))
        self.erreurs = erreurs


def normaliser_date(valeur):
    """YYYY-MM-DD ou DD/MM/YYYY vers YYYY-MM-DD, None si la date n'existe pas au calendrier."""
    if not isinstance(valeur, str):
        return None
    correspondance = _DATE_ISO.fullmatch(valeur)
    if correspondance:
        annee, mois, jour = correspondance.groups()
    else:
        correspondance = _DATE_FR.fullmatch(valeur)
        if not correspondance:
            return None
        jour, mois, annee = correspondance.groups()
    try:
        return date(int(annee), int(mois), int(jour)).isoformat()
    except ValueError:
        return None


def normaliser_periode(valeur):
    if not isinstance(valeur, str):
        return None
    # "après-midi" peut arriver décomposé (e + accent combinant) selon l'outil qui a écrit le fichier.
    return PERIODES.get(unicodedata.normalize("NFC", valeur))


def normaliser_statut(valeur):
    if not isinstance(valeur, str):
        return None
    return STATUTS.get(valeur)


def normaliser_groupe(valeur):
    return valeur if isinstance(valeur, str) and valeur in GROUPES else None


def normaliser_mode(valeur):
    return valeur if isinstance(valeur, str) and valeur in MODES else None


NORMALISEURS = {
    "date": normaliser_date,
    "period": normaliser_periode,
    "group": normaliser_groupe,
    "mode": normaliser_mode,
    "status": normaliser_statut,
}


def _afficher(valeur):
    return valeur if isinstance(valeur, str) else json.dumps(valeur, ensure_ascii=False)


def valider_seance(objet):
    """Retourne la séance normalisée (clés dans l'ordre de CHAMPS) ou lève SeanceInvalide.

    Les clés inconnues sont ignorées et ne sont pas recopiées dans la sortie.
    """
    manquants = [f"{champ} manquant" for champ in CHAMPS if champ not in objet]
    if manquants:
        raise SeanceInvalide(manquants)

    seance = {}
    erreurs = []
    for champ in CHAMPS:
        valeur = objet[champ]
        if champ in CHAMPS_TEXTE:
            if not isinstance(valeur, str):
                erreurs.append(f"{champ} doit être une chaîne")
            elif not valeur.strip():
                erreurs.append(f"{champ} vide")
            else:
                seance[champ] = valeur
        elif champ == "teacherId":
            if valeur is None or (isinstance(valeur, str) and valeur in FORMATEURS):
                seance[champ] = valeur
            else:
                erreurs.append(f"teacherId invalide: {_afficher(valeur)}")
        else:
            normalisee = NORMALISEURS[champ](valeur)
            if normalisee is None:
                erreurs.append(f"{champ} invalide: {_afficher(valeur)}")
            else:
                seance[champ] = normalisee

    # Les règles croisées ne portent que sur des champs déjà valides,
    # pour ne pas ajouter un second motif qui découle du premier.
    if seance.get("mode") == "AUTO":
        if "teacherId" in seance and seance["teacherId"] is not None:
            erreurs.append("mode AUTO exige teacherId null")
        if "status" in seance and seance["status"] != "proposed":
            erreurs.append("mode AUTO exige status proposed")
    if seance.get("status") == "confirmed" and "teacherId" in seance and seance["teacherId"] is None:
        erreurs.append("status confirmed exige un formateur")

    if erreurs:
        raise SeanceInvalide(erreurs)
    return seance
