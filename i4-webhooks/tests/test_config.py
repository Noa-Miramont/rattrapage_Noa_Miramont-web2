from pathlib import Path

import pytest

from i4_webhooks.config import (
    ATTENTES_ENTRE_TENTATIVES_S,
    FENETRE_HORODATAGE_S,
    TAILLE_MAX_CORPS,
    TENTATIVES_MAX,
    TIMEOUT_LIVRAISON_S,
    ConfigurationInvalide,
    Reglages,
    depuis_environnement,
)

SECRET = "matrice-local-only"


def test_valeurs_du_contrat():
    assert TAILLE_MAX_CORPS == 65_536
    assert FENETRE_HORODATAGE_S == 300
    assert TIMEOUT_LIVRAISON_S == 2.0
    assert TENTATIVES_MAX == 3
    assert ATTENTES_ENTRE_TENTATIVES_S == (0.2, 0.4)


def test_lecture_de_l_environnement():
    reglages = depuis_environnement({"MATRICE_WEBHOOK_SECRET": SECRET, "PARTENAIRE_URL": "http://partenaire:9000"})

    assert reglages.secret == SECRET
    assert reglages.url_partenaire == "http://partenaire:9000"
    assert reglages.timeout_livraison_s == 2.0


def test_url_partenaire_par_defaut():
    assert depuis_environnement({"MATRICE_WEBHOOK_SECRET": SECRET}).url_partenaire == "http://127.0.0.1:8001"


@pytest.mark.parametrize("environnement", [{}, {"MATRICE_WEBHOOK_SECRET": ""}])
def test_secret_obligatoire(environnement):
    with pytest.raises(ConfigurationInvalide, match="MATRICE_WEBHOOK_SECRET"):
        depuis_environnement(environnement)


@pytest.mark.parametrize("timeout", [0, -1, 2.5])
def test_timeout_borne_a_2_secondes(timeout):
    with pytest.raises(ConfigurationInvalide):
        Reglages(secret=SECRET, timeout_livraison_s=timeout)


def test_le_secret_n_apparait_pas_dans_la_representation():
    assert SECRET not in repr(Reglages(secret=SECRET))
    assert SECRET not in str(Reglages(secret=SECRET))


def test_env_example_contient_les_variables_attendues():
    contenu = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")

    assert f"MATRICE_WEBHOOK_SECRET={SECRET}" in contenu
    assert "PARTENAIRE_URL=http://127.0.0.1:8001" in contenu
