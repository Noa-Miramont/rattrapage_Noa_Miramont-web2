"""Authentification du webhook : HMAC-SHA256 de `X-Timestamp + "." + corps brut`.

Le corps est signé tel qu'il a été reçu, octet pour octet : le JSON n'est jamais
resérialisé, car un simple espace ou un ordre de clés différent changerait la signature.
"""

import hashlib
import hmac
import re

PREFIXE = "sha256="

# Secondes Unix en chiffres ASCII ; 12 chiffres suffisent jusqu'à l'an 33 000.
_HORODATAGE = re.compile(r"[0-9]{1,12}")
_SIGNATURE = re.compile(r"sha256=[0-9a-fA-F]{64}")


class AuthentificationRefusee(Exception):
    """Raison d'un refus 401. Le message ne contient jamais le secret ni la signature attendue."""


def signer(secret, horodatage, corps):
    message = horodatage.encode("ascii") + b"." + corps
    return PREFIXE + hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verifier(secret, horodatage, signature, corps, maintenant, fenetre_s):
    """Ne retourne rien si la requête est authentique et récente, lève AuthentificationRefusee sinon."""
    if horodatage is None:
        raise AuthentificationRefusee("en-tête X-Timestamp absent")
    if not _HORODATAGE.fullmatch(horodatage):
        raise AuthentificationRefusee("X-Timestamp doit être un nombre entier de secondes Unix")
    if signature is None:
        raise AuthentificationRefusee("en-tête X-Signature absent")
    if not _SIGNATURE.fullmatch(signature):
        raise AuthentificationRefusee("X-Signature doit être de la forme sha256=<64 caractères hexadécimaux>")

    # compare_digest prend le même temps quel que soit le premier octet différent :
    # un attaquant ne peut pas deviner la signature octet par octet en mesurant les réponses.
    if not hmac.compare_digest(signer(secret, horodatage, corps), signature.lower()):
        raise AuthentificationRefusee("signature invalide")

    if abs(maintenant - int(horodatage)) > fenetre_s:
        raise AuthentificationRefusee(f"X-Timestamp hors de la fenêtre de {fenetre_s} s")
