"""Récepteur du webhook MATRiCE : GET /health, POST /webhooks/planning, GET /deliveries/{event_id}.

Lancement : uvicorn i4_webhooks.recepteur:creer_app --factory --port 8000 --env-file .env

Ordre des contrôles de POST /webhooks/planning :
  1. taille du corps     > 64 Ko                  -> 413 (avant de calculer quoi que ce soit)
  2. signature HMAC      absente ou fausse        -> 401
  3. X-Timestamp         écart > 300 s            -> 401
  4. corps authentifié   événement non conforme   -> 400
  5. event_id déjà vu                             -> 200 duplicate:true, sans nouvelle livraison
  6. sinon                                        -> 202 duplicate:false, livraison en tâche de fond
La route lit le corps elle-même (Request) au lieu de déclarer un modèle Pydantic : FastAPI
parserait sinon le JSON avant la vérification de la signature et répondrait 422 au lieu de 401 ou 400.
"""

import asyncio
import logging
import time

import httpx2
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from i4_webhooks.config import FENETRE_HORODATAGE_S, TAILLE_MAX_CORPS, depuis_environnement
from i4_webhooks.journal import configurer_journal, tracer
from i4_webhooks.livraison import livrer
from i4_webhooks.modeles import EvenementInvalide, analyser_evenement
from i4_webhooks.signature import AuthentificationRefusee, verifier
from i4_webhooks.stockage import Registre


class CorpsTropGrand(Exception):
    pass


async def lire_corps_borne(request, limite):
    """Lit le corps sans jamais garder plus de `limite` octets, même sans Content-Length (chunked)."""
    longueur = request.headers.get("content-length", "")
    if longueur.isdigit() and int(longueur) > limite:
        raise CorpsTropGrand
    morceaux = []
    taille = 0
    async for morceau in request.stream():
        taille += len(morceau)
        if taille > limite:
            raise CorpsTropGrand
        morceaux.append(morceau)
    return b"".join(morceaux)


def creer_app(reglages=None, horloge=time.time, transport=None, attendre=asyncio.sleep):
    """`horloge`, `transport` et `attendre` sont remplacés dans les tests ; en production :
    heure Unix de la machine, réseau réel vers le partenaire et vraies attentes."""
    reglages = depuis_environnement() if reglages is None else reglages
    configurer_journal()
    registre = Registre()

    app = FastAPI(title="Récepteur webhook MATRiCE")
    app.state.registre = registre

    def refuser(statut, raison, **details):
        tracer("webhook.rejete", niveau=logging.WARNING, statut_http=statut, raison=raison)
        return JSONResponse(status_code=statut, content={"detail": raison, **details})

    async def livrer_en_tache_de_fond(livraison, corps):
        async with httpx2.AsyncClient(base_url=reglages.url_partenaire, transport=transport) as client:
            await livrer(livraison, corps, client, reglages.timeout_livraison_s, attendre)

    @app.get("/health")
    async def sante():
        return {"status": "ok"}

    @app.post("/webhooks/planning")
    async def recevoir(request: Request, taches: BackgroundTasks):
        try:
            corps = await lire_corps_borne(request, TAILLE_MAX_CORPS)
        except CorpsTropGrand:
            return refuser(413, f"corps supérieur à {TAILLE_MAX_CORPS} octets")

        try:
            verifier(
                reglages.secret,
                request.headers.get("X-Timestamp"),
                request.headers.get("X-Signature"),
                corps,
                horloge(),
                FENETRE_HORODATAGE_S,
            )
        except AuthentificationRefusee as refus:
            return refuser(401, str(refus))

        try:
            evenement = analyser_evenement(corps)
        except EvenementInvalide as invalide:
            return refuser(400, "événement invalide", erreurs=invalide.erreurs)

        livraison, nouvelle = registre.enregistrer_si_nouveau(evenement.event_id)
        if not nouvelle:
            tracer("webhook.doublon", event_id=evenement.event_id)
            return JSONResponse(status_code=200, content={"event_id": evenement.event_id, "duplicate": True})

        tracer("webhook.accepte", event_id=evenement.event_id)
        taches.add_task(livrer_en_tache_de_fond, livraison, corps)
        return JSONResponse(status_code=202, content={"event_id": evenement.event_id, "duplicate": False})

    @app.get("/deliveries/{event_id}")
    async def consulter_livraison(event_id: str):
        livraison = registre.obtenir(event_id)
        if livraison is None:
            return JSONResponse(status_code=404, content={"detail": "livraison inconnue"})
        return livraison.en_dict()

    return app
