"""Contrat de l'événement reçu : type session.updated et séance conforme aux règles métier.

La séance est attendue sous sa forme canonique (2026-10-19, am, confirmed) : le webhook
transporte des données déjà normalisées, il n'accepte pas les alias d'un fichier brut.
Mode strict : aucune conversion implicite (un nombre n'est pas accepté à la place d'une chaîne).
Les clés inconnues sont ignorées, pour qu'un émetteur puisse ajouter un champ sans tout casser.
"""

import datetime
import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, ValidationError, model_validator

_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class EvenementInvalide(ValueError):
    def __init__(self, erreurs):
        super().__init__("; ".join(erreurs))
        self.erreurs = erreurs


def _non_vide(valeur):
    if not valeur.strip():
        raise ValueError("ne doit pas être vide")
    return valeur


def _date_du_calendrier(valeur):
    if not _DATE.fullmatch(valeur):
        raise ValueError("format attendu YYYY-MM-DD")
    try:
        datetime.date.fromisoformat(valeur)
    except ValueError:
        raise ValueError("date absente du calendrier") from None
    return valeur


def _iso_8601_avec_fuseau(valeur):
    try:
        instant = datetime.datetime.fromisoformat(valeur)
    except ValueError:
        raise ValueError("date et heure ISO 8601 attendues") from None
    if instant.tzinfo is None:
        raise ValueError("le fuseau est obligatoire (Z ou ±HH:MM)")
    return valeur


TexteNonVide = Annotated[str, AfterValidator(_non_vide)]
DateCalendaire = Annotated[str, AfterValidator(_date_du_calendrier)]
InstantAvecFuseau = Annotated[str, AfterValidator(_iso_8601_avec_fuseau)]


class Seance(BaseModel):
    model_config = ConfigDict(strict=True)

    id: TexteNonVide
    date: DateCalendaire
    period: Literal["am", "pm"]
    group: Literal["A", "B", "Promotion"]
    mode: Literal["DG", "CE", "AUTO"]
    title: TexteNonVide
    domain: TexteNonVide
    teacherId: Literal["t1", "t2", "t3"] | None
    status: Literal["proposed", "confirmed"]

    @model_validator(mode="after")
    def regles_croisees(self):
        if self.mode == "AUTO" and (self.teacherId is not None or self.status != "proposed"):
            raise ValueError("mode AUTO exige teacherId null et status proposed")
        if self.status == "confirmed" and self.teacherId is None:
            raise ValueError("status confirmed exige un formateur")
        return self


class Evenement(BaseModel):
    model_config = ConfigDict(strict=True)

    event_id: TexteNonVide
    type: Literal["session.updated"]
    occurred_at: InstantAvecFuseau
    session: Seance


def analyser_evenement(corps):
    """Octets bruts déjà authentifiés -> Evenement, ou EvenementInvalide avec la liste des erreurs."""
    try:
        return Evenement.model_validate_json(corps)
    except ValidationError as erreur:
        raise EvenementInvalide(
            [f"{'.'.join(map(str, detail['loc'])) or 'corps'}: {detail['msg']}" for detail in erreur.errors()]
        ) from None
