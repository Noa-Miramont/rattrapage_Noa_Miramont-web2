from types import SimpleNamespace

import httpx2
import pytest
from fastapi.testclient import TestClient

from fabriques import MAINTENANT, SECRET, octets
from i4_webhooks.config import Reglages
from i4_webhooks.partenaire import creer_app as creer_partenaire
from i4_webhooks.recepteur import creer_app as creer_recepteur
from i4_webhooks.signature import signer


@pytest.fixture
def recepteur():
    """Fabrique un récepteur relié en mémoire à un partenaire simulé, avec une horloge fixe
    et des attentes enregistrées au lieu d'être dormies."""

    def fabriquer(mode="ok", timeout_s=2.0, delai_slow_s=3.0):
        partenaire = creer_partenaire(mode=mode, delai_slow_s=delai_slow_s)
        attentes = []

        async def attendre(secondes):
            attentes.append(secondes)

        app = creer_recepteur(
            Reglages(secret=SECRET, timeout_livraison_s=timeout_s),
            horloge=lambda: MAINTENANT,
            transport=httpx2.ASGITransport(app=partenaire),
            attendre=attendre,
        )
        client = TestClient(app)

        def poster(corps, horodatage=MAINTENANT, signature=None, secret=SECRET, en_tetes=None):
            corps = corps if isinstance(corps, bytes) else octets(corps)
            horodatage = str(horodatage)
            tetes = {
                "Content-Type": "application/json",
                "X-Timestamp": horodatage,
                "X-Signature": signature or signer(secret, horodatage, corps),
            }
            tetes.update(en_tetes or {})
            presents = {nom: valeur for nom, valeur in tetes.items() if valeur is not None}
            return client.post("/webhooks/planning", content=corps, headers=presents)

        return SimpleNamespace(app=app, client=client, partenaire=partenaire, attentes=attentes, poster=poster)

    return fabriquer
