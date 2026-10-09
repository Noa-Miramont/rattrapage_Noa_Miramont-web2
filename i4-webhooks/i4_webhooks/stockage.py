"""Registre en mémoire des livraisons, indexé par event_id.

Limite assumée (autorisée par le sujet) : tout est perdu au redémarrage du processus
(event_id déjà vus, statuts, livraisons en cours), et le registre n'est pas partagé
entre plusieurs processus uvicorn.
"""

from dataclasses import dataclass

EN_ATTENTE = "pending"
LIVREE = "delivered"
QUARANTAINE = "quarantine"


@dataclass
class Livraison:
    event_id: str
    statut: str = EN_ATTENTE
    tentatives: int = 0
    derniere_erreur: str | None = None

    def en_dict(self):
        return {
            "event_id": self.event_id,
            "status": self.statut,
            "attempts": self.tentatives,
            "last_error": self.derniere_erreur,
        }


class Registre:
    def __init__(self):
        self._livraisons = {}

    def enregistrer_si_nouveau(self, event_id):
        """Retourne (livraison, nouvelle). Sans aucun await entre la recherche et l'insertion,
        deux requêtes simultanées traitées par la même boucle asyncio ne peuvent pas créer
        deux livraisons pour le même event_id."""
        existante = self._livraisons.get(event_id)
        if existante is not None:
            return existante, False
        livraison = Livraison(event_id)
        self._livraisons[event_id] = livraison
        return livraison, True

    def obtenir(self, event_id):
        return self._livraisons.get(event_id)
