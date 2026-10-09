"""Réglages du récepteur : valeurs fixées par le contrat et variables d'environnement."""

import os
from dataclasses import dataclass, field

TAILLE_MAX_CORPS = 64 * 1024
FENETRE_HORODATAGE_S = 300
TIMEOUT_LIVRAISON_S = 2.0
TENTATIVES_MAX = 3
ATTENTES_ENTRE_TENTATIVES_S = (0.2, 0.4)

URL_PARTENAIRE_PAR_DEFAUT = "http://127.0.0.1:8001"


class ConfigurationInvalide(RuntimeError):
    pass


@dataclass(frozen=True)
class Reglages:
    # repr=False : un print ou un log des réglages n'affiche jamais le secret.
    secret: str = field(repr=False)
    url_partenaire: str = URL_PARTENAIRE_PAR_DEFAUT
    timeout_livraison_s: float = TIMEOUT_LIVRAISON_S

    def __post_init__(self):
        if not self.secret:
            raise ConfigurationInvalide("le secret HMAC est vide")
        if not 0 < self.timeout_livraison_s <= TIMEOUT_LIVRAISON_S:
            raise ConfigurationInvalide(f"le timeout de livraison doit être compris entre 0 et {TIMEOUT_LIVRAISON_S} s")


def depuis_environnement(environnement=None):
    environnement = os.environ if environnement is None else environnement
    secret = environnement.get("MATRICE_WEBHOOK_SECRET", "")
    if not secret:
        raise ConfigurationInvalide(
            "MATRICE_WEBHOOK_SECRET n'est pas défini : copier .env.example en .env et lancer uvicorn avec --env-file .env"
        )
    return Reglages(
        secret=secret,
        url_partenaire=environnement.get("PARTENAIRE_URL") or URL_PARTENAIRE_PAR_DEFAUT,
    )
