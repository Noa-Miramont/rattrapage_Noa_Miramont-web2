"""Fabriques de données de test : une séance et un événement conformes, modifiables champ par champ."""

import json

SECRET = "matrice-local-only"
MAINTENANT = 1_790_000_000


def seance(**modifications):
    base = {
        "id": "s01",
        "date": "2026-10-19",
        "period": "am",
        "group": "A",
        "mode": "DG",
        "title": "React composants",
        "domain": "web",
        "teacherId": "t1",
        "status": "confirmed",
    }
    base.update(modifications)
    return base


def evenement(event_id="evt-1", session=None, **modifications):
    base = {
        "event_id": event_id,
        "type": "session.updated",
        "occurred_at": "2026-10-19T08:30:00+02:00",
        "session": seance() if session is None else session,
    }
    base.update(modifications)
    return base


def octets(objet):
    return json.dumps(objet, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
