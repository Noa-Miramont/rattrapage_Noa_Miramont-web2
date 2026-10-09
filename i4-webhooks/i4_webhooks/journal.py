"""Journal du module I4 : une ligne JSON par événement, champs filtrés par liste blanche.

Un champ absent de CHAMPS_AUTORISES n'est jamais écrit : même un appel maladroit comme
tracer(..., secret=...) ou tracer(..., corps=...) ne peut pas faire fuiter une donnée sensible.
Les valeurs passent par json.dumps : un event_id contenant un retour à la ligne est échappé
et ne peut pas fabriquer une fausse ligne de journal.
"""

import datetime
import json
import logging
import sys

NOM_JOURNAL = "matrice.webhooks"

CHAMPS_AUTORISES = (
    "event_id",
    "statut_http",
    "raison",
    "tentative",
    "tentatives",
    "resultat",
    "attente_s",
    "mode",
    "ticket_id",
)

journal = logging.getLogger(NOM_JOURNAL)


def tracer(evenement, niveau=logging.INFO, **champs):
    retenus = {cle: valeur for cle, valeur in champs.items() if cle in CHAMPS_AUTORISES}
    journal.log(niveau, evenement, extra={"champs": retenus})


class FormateurJson(logging.Formatter):
    def format(self, enregistrement):
        horodatage = datetime.datetime.fromtimestamp(enregistrement.created, datetime.timezone.utc)
        ligne = {
            "horodatage": horodatage.isoformat(timespec="milliseconds"),
            "niveau": enregistrement.levelname,
            "evenement": enregistrement.getMessage(),
            **getattr(enregistrement, "champs", {}),
        }
        return json.dumps(ligne, ensure_ascii=False)


def configurer_journal(flux=None):
    """Écrit le journal sur stderr en JSON ; sans effet si c'est déjà fait."""
    if not any(isinstance(gestionnaire.formatter, FormateurJson) for gestionnaire in journal.handlers):
        gestionnaire = logging.StreamHandler(flux or sys.stderr)
        gestionnaire.setFormatter(FormateurJson())
        journal.addHandler(gestionnaire)
    journal.setLevel(logging.INFO)
