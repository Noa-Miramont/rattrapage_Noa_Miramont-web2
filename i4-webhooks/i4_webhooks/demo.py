"""Démonstration de bout en bout contre les deux serveurs lancés : python -m i4_webhooks.demo

À lancer depuis i4-webhooks/, après avoir démarré dans deux autres terminaux :
  uvicorn i4_webhooks.partenaire:creer_app --factory --port 8001
  uvicorn i4_webhooks.recepteur:creer_app --factory --port 8000 --env-file .env
Le secret est lu dans MATRICE_WEBHOOK_SECRET, sinon dans le fichier .env.
Code retour 0 si chaque résultat observé est celui attendu, 1 sinon.
"""

import argparse
import json
import os
import sys
import time
import uuid

import httpx2
from dotenv import dotenv_values

from i4_webhooks.signature import signer

# mode du partenaire -> (statut final attendu, nombre de tentatives attendu)
ATTENDUS = {
    "ok": ("delivered", 1),
    "flaky": ("delivered", 2),
    "down": ("quarantine", 3),
    "slow": ("quarantine", 3),
    "reject": ("quarantine", 1),
}


def construire_evenement(event_id, **session):
    return {
        "event_id": event_id,
        "type": "session.updated",
        "occurred_at": "2026-10-19T08:30:00+02:00",
        "session": {
            "id": "s01",
            "date": "2026-10-19",
            "period": "am",
            "group": "A",
            "mode": "DG",
            "title": "React composants",
            "domain": "web",
            "teacherId": "t1",
            "status": "confirmed",
            **session,
        },
    }


def en_octets(objet):
    return json.dumps(objet, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class Demonstration:
    def __init__(self, url_recepteur, url_partenaire, secret):
        self.recepteur = httpx2.Client(base_url=url_recepteur, timeout=10)
        self.partenaire = httpx2.Client(base_url=url_partenaire, timeout=10)
        self.secret = secret
        self.suffixe = uuid.uuid4().hex[:6]
        self.verifications = []

    def verifier(self, libelle, observe, attendu):
        conforme = observe == attendu
        self.verifications.append(conforme)
        print(f"  [{'OK' if conforme else 'ECART'}] {libelle} : observé {observe}, attendu {attendu}")

    def envoyer(self, corps, decalage_s=0, secret=None):
        horodatage = str(int(time.time()) - decalage_s)
        signature = signer(secret or self.secret, horodatage, corps)
        return self.recepteur.post(
            "/webhooks/planning",
            content=corps,
            headers={"Content-Type": "application/json", "X-Timestamp": horodatage, "X-Signature": signature},
        )

    def suivre(self, event_id, limite_s=15):
        debut = time.monotonic()
        while True:
            etat = self.recepteur.get(f"/deliveries/{event_id}").json()
            if etat["status"] != "pending" or time.monotonic() - debut > limite_s:
                return etat, time.monotonic() - debut
            time.sleep(0.1)

    def sante(self):
        print("== Santé des deux services")
        print("  récepteur  GET /health ->", self.recepteur.get("/health").json())
        print("  partenaire GET /health ->", self.partenaire.get("/health").json())

    def livraisons(self):
        print("\n== Livraison d'un événement signé, pour chaque mode du partenaire")
        for mode, (statut_attendu, tentatives_attendues) in ATTENDUS.items():
            self.partenaire.put("/mode", json={"mode": mode})
            event_id = f"demo-{mode}-{self.suffixe}"
            reponse = self.envoyer(en_octets(construire_evenement(event_id)))
            etat, duree = self.suivre(event_id)
            print(f"- mode {mode} : POST -> {reponse.status_code} {reponse.json()}")
            print(f"  GET /deliveries/{event_id} -> {etat} (après {duree:.1f} s)")
            self.verifier("statut et tentatives", (etat["status"], etat["attempts"]), (statut_attendu, tentatives_attendues))
        self.partenaire.put("/mode", json={"mode": "ok"})

    def doublon(self):
        print("\n== Répétition d'un événement déjà accepté")
        event_id = f"demo-ok-{self.suffixe}"
        avant = self.partenaire.get("/appels").json().get(event_id)
        reponse = self.envoyer(en_octets(construire_evenement(event_id)))
        apres = self.partenaire.get("/appels").json().get(event_id)
        print(f"  POST {event_id} une seconde fois -> {reponse.status_code} {reponse.json()}")
        self.verifier("réponse", (reponse.status_code, reponse.json()["duplicate"]), (200, True))
        self.verifier("appels reçus par le partenaire (aucune nouvelle livraison)", apres, avant)

    def refus(self):
        print("\n== Requêtes refusées")
        corps = en_octets(construire_evenement(f"demo-refus-{self.suffixe}"))
        cas = [
            ("signature calculée avec un autre secret", self.envoyer(corps, secret="autre-secret"), 401),
            ("X-Timestamp vieux de 301 s", self.envoyer(corps, decalage_s=301), 401),
            ("corps de 64 Ko + 1 octet", self.envoyer(b"x" * (64 * 1024 + 1)), 413),
            (
                "séance AUTO avec un formateur",
                self.envoyer(en_octets(construire_evenement(f"demo-400-{self.suffixe}", mode="AUTO", status="proposed"))),
                400,
            ),
        ]
        for libelle, reponse, attendu in cas:
            print(f"  {libelle} -> {reponse.status_code} {reponse.json()}")
            self.verifier("code HTTP", reponse.status_code, attendu)

    def bilan_partenaire(self):
        print("\n== Côté partenaire : appels reçus et tickets créés (un ticket au plus par Idempotency-Key)")
        appels = self.partenaire.get("/appels").json()
        tickets = {t["idempotency_key"]: t["ticket_id"] for t in self.partenaire.get("/tickets").json()}
        for cle, nombre in appels.items():
            if cle.endswith(self.suffixe):
                print(f"  {cle:<22} {nombre} appel(s) -> ticket {tickets.get(cle, 'aucun')}")
        cle_slow = f"demo-slow-{self.suffixe}"
        print(
            "  Mode slow : le récepteur a abandonné chaque tentative au bout de 2 s, mais le partenaire a\n"
            "  terminé le traitement de son côté. Les 3 appels portaient la même Idempotency-Key : un seul ticket."
        )
        self.verifier(
            "mode slow, appels reçus et tickets créés",
            (appels.get(cle_slow), sum(1 for cle in tickets if cle == cle_slow)),
            (3, 1),
        )

    def executer(self):
        self.sante()
        self.livraisons()
        self.doublon()
        self.refus()
        self.bilan_partenaire()
        conformes = sum(self.verifications)
        print(f"\nBilan : {conformes}/{len(self.verifications)} vérifications conformes")
        return 0 if conformes == len(self.verifications) else 1


def main(argv=None):
    parseur = argparse.ArgumentParser(prog="python -m i4_webhooks.demo", description=__doc__.splitlines()[0])
    parseur.add_argument("--recepteur", default="http://127.0.0.1:8000")
    parseur.add_argument("--partenaire", default="http://127.0.0.1:8001")
    parseur.add_argument("--env-file", default=".env")
    arguments = parseur.parse_args(argv)

    secret = os.environ.get("MATRICE_WEBHOOK_SECRET") or dotenv_values(arguments.env_file).get("MATRICE_WEBHOOK_SECRET")
    if not secret:
        parseur.error("MATRICE_WEBHOOK_SECRET introuvable : copier .env.example en .env")
    try:
        return Demonstration(arguments.recepteur, arguments.partenaire, secret).executer()
    except httpx2.ConnectError as erreur:
        print(f"Serveur injoignable ({erreur}) : lancer d'abord le partenaire et le récepteur (voir README).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
