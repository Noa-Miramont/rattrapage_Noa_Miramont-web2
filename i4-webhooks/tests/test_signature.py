import pytest

from i4_webhooks.signature import AuthentificationRefusee, signer, verifier

SECRET = "matrice-local-only"
MAINTENANT = 1_790_000_000
HORODATAGE = str(MAINTENANT)
CORPS = b'{"event_id":"evt-1"}'

# printf '%s' '1790000000.{"event_id":"evt-1"}' | openssl dgst -sha256 -hmac matrice-local-only
SIGNATURE_OPENSSL = "sha256=2de474e18011475aa65dd7ab6e887599ce7b9083dfc82df478eb17e8c8d0dda8"


def verifier_avec(horodatage=HORODATAGE, signature=None, corps=CORPS, maintenant=MAINTENANT, secret=SECRET):
    if signature is None:
        signature = signer(SECRET, horodatage, corps) if horodatage is not None else SIGNATURE_OPENSSL
    verifier(secret, horodatage, signature, corps, maintenant, 300)


def refus(**arguments):
    with pytest.raises(AuthentificationRefusee) as exc:
        verifier_avec(**arguments)
    return str(exc.value)


def test_signature_identique_a_openssl():
    assert signer(SECRET, HORODATAGE, CORPS) == SIGNATURE_OPENSSL


def test_signature_valide_acceptee():
    verifier_avec(signature=SIGNATURE_OPENSSL)


def test_signature_en_majuscules_acceptee():
    verifier_avec(signature="sha256=" + SIGNATURE_OPENSSL.removeprefix("sha256=").upper())


def test_mauvais_secret_refuse():
    assert refus(secret="autre-secret", signature=SIGNATURE_OPENSSL) == "signature invalide"


def test_corps_modifie_apres_signature_refuse():
    assert refus(signature=SIGNATURE_OPENSSL, corps=b'{"event_id":"evt-2"}') == "signature invalide"


def test_json_reserialise_refuse():
    # Même objet JSON, octets différents : seule la signature du corps brut fait foi.
    assert refus(signature=SIGNATURE_OPENSSL, corps=b'{"event_id": "evt-1"}') == "signature invalide"


def test_horodatage_modifie_apres_signature_refuse():
    assert refus(horodatage=str(MAINTENANT - 1), signature=SIGNATURE_OPENSSL) == "signature invalide"


def test_en_tetes_absents_refuses():
    assert refus(horodatage=None) == "en-tête X-Timestamp absent"
    with pytest.raises(AuthentificationRefusee, match="X-Signature absent"):
        verifier(SECRET, HORODATAGE, None, CORPS, MAINTENANT, 300)


@pytest.mark.parametrize("horodatage", ["", "abc", "-1790000000", "1790000000.5", "1e9", " 1790000000", "١٧٩٠٠٠٠٠٠٠"])
def test_horodatage_mal_forme_refuse(horodatage):
    assert "secondes Unix" in refus(horodatage=horodatage, signature=SIGNATURE_OPENSSL)


@pytest.mark.parametrize(
    "signature",
    [
        "",
        SIGNATURE_OPENSSL.removeprefix("sha256="),
        "sha1=" + SIGNATURE_OPENSSL.removeprefix("sha256="),
        SIGNATURE_OPENSSL[:-1],
        SIGNATURE_OPENSSL + "0",
        SIGNATURE_OPENSSL[:-1] + "z",
    ],
)
def test_signature_mal_formee_refusee(signature):
    assert "sha256=" in refus(signature=signature)


@pytest.mark.parametrize("ecart", [0, 1, 299, 300, -300])
def test_horodatage_dans_la_fenetre_accepte(ecart):
    verifier_avec(horodatage=str(MAINTENANT - ecart))


@pytest.mark.parametrize("ecart", [301, 3600, -301])
def test_horodatage_hors_fenetre_refuse(ecart):
    assert refus(horodatage=str(MAINTENANT - ecart)) == "X-Timestamp hors de la fenêtre de 300 s"


def test_horloge_avec_fraction_de_seconde():
    verifier_avec(maintenant=MAINTENANT + 300.0)
    assert "fenêtre" in refus(maintenant=MAINTENANT + 300.001)


def test_les_messages_de_refus_ne_contiennent_pas_le_secret():
    messages = [
        refus(secret="x", signature=SIGNATURE_OPENSSL),
        refus(horodatage="abc", signature=SIGNATURE_OPENSSL),
        refus(horodatage=str(MAINTENANT - 301)),
    ]

    for message in messages:
        assert SECRET not in message
        assert SIGNATURE_OPENSSL.removeprefix("sha256=") not in message
