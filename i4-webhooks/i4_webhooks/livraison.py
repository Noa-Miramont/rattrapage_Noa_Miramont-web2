"""Livraison d'un événement au partenaire : POST /tickets, timeout, reprises bornées, quarantaine.

Politique :
- chaque tentative est coupée au bout de `timeout_s` (2 s au plus) ;
- on réessaie sur timeout, erreur réseau, 429 et 5xx, qui peuvent être passagers ;
- on ne réessaie pas sur les autres réponses : un 400 restera un 400 ;
- 3 tentatives au plus, séparées par 0,2 puis 0,4 s ; échec final -> quarantaine.
L'en-tête Idempotency-Key (= event_id) permet au partenaire d'ignorer une tentative répétée
dont la précédente avait abouti chez lui sans que la réponse nous parvienne (timeout).
"""

import asyncio
import logging

import httpx2

from i4_webhooks.config import ATTENTES_ENTRE_TENTATIVES_S, TENTATIVES_MAX
from i4_webhooks.journal import tracer
from i4_webhooks.stockage import LIVREE, QUARANTAINE


def est_reessayable(statut_http):
    return statut_http == 429 or statut_http >= 500


async def _tenter(client, event_id, corps, timeout_s):
    """Une tentative. Retourne (succès, réessayable, description du résultat)."""
    try:
        # asyncio.timeout borne la durée totale de la tentative, quel que soit le transport.
        async with asyncio.timeout(timeout_s):
            reponse = await client.post(
                "/tickets",
                content=corps,
                headers={"Idempotency-Key": event_id, "Content-Type": "application/json"},
                timeout=timeout_s,
            )
    except (TimeoutError, httpx2.TimeoutException):
        return False, True, "timeout"
    except httpx2.TransportError as erreur:
        return False, True, f"erreur réseau ({type(erreur).__name__})"
    if 200 <= reponse.status_code < 300:
        return True, False, f"http {reponse.status_code}"
    return False, est_reessayable(reponse.status_code), f"http {reponse.status_code}"


async def livrer(livraison, corps, client, timeout_s, attendre=asyncio.sleep):
    """Livre `corps` (les octets reçus, inchangés) et met à jour `livraison` au fil des tentatives."""
    try:
        for tentative in range(1, TENTATIVES_MAX + 1):
            livraison.tentatives = tentative
            succes, reessayable, resultat = await _tenter(client, livraison.event_id, corps, timeout_s)
            tracer("livraison.tentative", event_id=livraison.event_id, tentative=tentative, resultat=resultat)
            if succes:
                livraison.statut = LIVREE
                livraison.derniere_erreur = None
                tracer("livraison.livree", event_id=livraison.event_id, tentatives=tentative)
                return livraison
            livraison.derniere_erreur = resultat
            if not reessayable or tentative == TENTATIVES_MAX:
                break
            attente = ATTENTES_ENTRE_TENTATIVES_S[tentative - 1]
            tracer("livraison.reprise", event_id=livraison.event_id, tentative=tentative, attente_s=attente)
            await attendre(attente)
    except Exception as erreur:
        # Filet de sécurité : une erreur imprévue ne doit pas laisser la livraison "pending" pour toujours.
        livraison.derniere_erreur = f"erreur interne ({type(erreur).__name__})"
    livraison.statut = QUARANTAINE
    tracer(
        "livraison.quarantaine",
        niveau=logging.WARNING,
        event_id=livraison.event_id,
        tentatives=livraison.tentatives,
        raison=livraison.derniere_erreur,
    )
    return livraison
