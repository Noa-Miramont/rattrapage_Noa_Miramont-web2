"""Partenaire simulé : POST /tickets, idempotent par Idempotency-Key, avec cinq modes de panne.

Lancement : uvicorn i4_webhooks.partenaire:creer_app --factory --port 8001
Le mode initial vient de PARTENAIRE_MODE (défaut ok) ; PUT /mode le change sans redémarrer.
GET /tickets et GET /appels (nombre de POST reçus par clé) servent à vérifier l'idempotence.
"""

import asyncio
import json
import logging
import os
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from i4_webhooks.journal import configurer_journal, tracer

MODES = ("ok", "flaky", "down", "slow", "reject")
DELAI_SLOW_S = 3.0


class ChangementDeMode(BaseModel):
    mode: Literal["ok", "flaky", "down", "slow", "reject"]


def _session_id(corps):
    try:
        return json.loads(corps)["session"]["id"]
    except (ValueError, KeyError, TypeError):
        return None


def creer_app(mode=None, delai_slow_s=DELAI_SLOW_S):
    mode = os.environ.get("PARTENAIRE_MODE", "ok") if mode is None else mode
    if mode not in MODES:
        raise ValueError(f"mode inconnu : {mode} (attendu : {', '.join(MODES)})")
    configurer_journal()

    app = FastAPI(title="Partenaire simulé MATRiCE")
    app.state.mode = mode
    app.state.tickets = {}
    app.state.appels = {}

    def refuser(statut, cle, raison):
        tracer("partenaire.refus", niveau=logging.WARNING, event_id=cle, statut_http=statut, mode=app.state.mode)
        return JSONResponse(status_code=statut, content={"detail": raison})

    @app.get("/health")
    async def sante():
        return {"status": "ok", "mode": app.state.mode}

    @app.put("/mode")
    async def changer_mode(changement: ChangementDeMode):
        app.state.mode = changement.mode
        tracer("partenaire.mode", mode=app.state.mode)
        return {"mode": app.state.mode}

    @app.get("/tickets")
    async def lister_tickets():
        return list(app.state.tickets.values())

    @app.get("/appels")
    async def compter_appels():
        return app.state.appels

    @app.post("/tickets")
    async def creer_ticket(request: Request):
        cle = request.headers.get("Idempotency-Key")
        if not cle:
            return refuser(400, None, "en-tête Idempotency-Key obligatoire")
        # Lu tout de suite : en mode slow, le client peut avoir abandonné avant la fin de l'attente,
        # mais le partenaire termine quand même le traitement, comme un vrai service distant.
        corps = await request.body()
        appel = app.state.appels.get(cle, 0) + 1
        app.state.appels[cle] = appel

        mode = app.state.mode
        if mode == "down":
            return refuser(503, cle, "partenaire indisponible")
        if mode == "reject":
            return refuser(400, cle, "ticket refusé par le partenaire")
        if mode == "flaky" and appel == 1:
            return refuser(503, cle, "indisponibilité passagère")
        if mode == "slow":
            await asyncio.sleep(delai_slow_s)

        ticket = app.state.tickets.get(cle)
        if ticket is not None:
            tracer("partenaire.ticket_rejoue", event_id=cle, ticket_id=ticket["ticket_id"])
            return JSONResponse(status_code=200, content=ticket, headers={"Idempotent-Replayed": "true"})

        ticket = {
            "ticket_id": f"T-{len(app.state.tickets) + 1:04d}",
            "idempotency_key": cle,
            "session_id": _session_id(corps),
        }
        app.state.tickets[cle] = ticket
        tracer("partenaire.ticket_cree", event_id=cle, ticket_id=ticket["ticket_id"])
        return JSONResponse(status_code=201, content=ticket)

    return app
