# Sources et usages de l'IA

## Outil utilisé

- **Cursor** (éditeur de code), en mode agent, avec le modèle **Claude Opus 5.5**.
- Usages : analyse du sujet, génération du code, des tests et de la documentation

## Démarche

1. **Analyse et plan** : le PDF du sujet a été fourni à l'agent en mode plan. Le plan (structure, contrat de chaque module, étapes et messages de commit) a été relu et validé avant toute écriture de code.
2. **Décisions prises personnellement** pendant la planification et la réalisation :
   - stockage en mémoire pour I4, plutôt que SQLite, puisque le sujet l'autorise si la limite au redémarrage est documentée ;
   - ajout d'une CI GitHub Actions non exigée ;
   - séparation du projet en deux dossiers indépendants, un par module ;
   - organisation Git en branches `main` / `dev`, une branche et une pull request par étape, `dev` fusionnée dans `main` à la fin de chaque module.
3. **Réalisation par étapes** : chaque étape correspond à une branche et à un commit, et les tests sont lancés à chaque étape avant de passer à la suivante.


## I3 — Structuration de flux

| Fichier | Apport de l'IA | Adaptations et vérifications |
|---|---|---|
| `i3-flux/data/seances.ndjson` | Transcription des deux tableaux du sujet en NDJSON | Contrôlé par `tests/test_donnees.py` : 11 lignes comparées aux tableaux, ligne 12 identique au sujet et bien malformée |
| `i3-flux/i3_flux/regles.py` | Validation et normalisation des champs | Première version réécrite pour parcourir les champs dans un ordre fixe (motifs stables) ; `[0-9]` au lieu de `\d` pour refuser les chiffres non ASCII ; normalisation NFC de `après-midi` |
| `i3-flux/i3_flux/pipeline.py` | Lecture en flux, déduplication, écriture des sorties | Lecture binaire pour qu'un octet invalide ne stoppe pas le flux ; refus de `NaN` / `Infinity` ; écriture atomique ; commentaire sur l'usage mémoire |
| `i3-flux/i3_flux/__main__.py` | Commande `python -m i3_flux` | Ajout de l'option `--details` pour tracer la décision de chaque ligne dans les preuves |
| `i3-flux/i3_flux/mesure_memoire.py` | Mesure du pic mémoire avec `tracemalloc` | Exécuté ; tailles réduites pour une durée d'environ 15 s ; résultat dans `preuves/i3/memoire.txt` |
| `i3-flux/tests/*.py` | Tests unitaires, d'intégration, de la commande et des preuves | 119 tests exécutés avec Python 3.14.2 et 3.11.16 |
| `.github/workflows/tests.yml` | Workflow de CI | Déclenché sur les pull requests et sur les pushes vers `main` et `dev`, pour éviter deux exécutions identiques par branche ; YAML validé localement |
| `README.md`, `JUSTIFICATIONS.md`, `SOURCES_IA.md` | Rédaction | Relus ; chiffres de la mesure mémoire recopiés depuis l'exécution réelle |

Vérifications effectuées sur I3 :

- résultat attendu calculé à la main à partir du sujet (6 acceptés : lignes 1, 2, 3, 5, 6, 11 ; 4 rejets : lignes 7, 8, 9, 12 ; 2 doublons : lignes 4 et 10), puis comparé à la sortie réelle de la commande ;
- exécution de la suite de tests sous Python 3.14 et 3.11 (version minimale annoncée) ;
- contrôle qu'aucun chemin local ni donnée personnelle n'apparaît dans `preuves/`.

## I4 — Webhooks & API tierce

| Fichier | Apport de l'IA | Adaptations et vérifications |
|---|---|---|
| `i4-webhooks/i4_webhooks/config.py`, `.env.example` | Constantes du contrat, lecture de l'environnement | Secret sans valeur par défaut dans le code, masqué dans la représentation des réglages ; timeout borné à 2 s |
| `i4-webhooks/i4_webhooks/signature.py` | HMAC-SHA256 sur `timestamp + "." + corps brut`, fenêtre de 300 s | Signature de référence calculée indépendamment avec `openssl dgst -sha256 -hmac` et inscrite dans les tests ; comparaison en temps constant |
| `i4-webhooks/i4_webhooks/modeles.py` | Contrat Pydantic de l'événement et de la séance | Première version réécrite : la réutilisation de validateurs via un attribut `_...` est fragile en Pydantic v2, remplacée par des types `Annotated` + `AfterValidator` |
| `i4-webhooks/i4_webhooks/journal.py` | Journal JSON à liste blanche | Test qui passe volontairement `secret=` et `corps=` au journal pour vérifier qu'ils ne sont jamais écrits |
| `i4-webhooks/i4_webhooks/partenaire.py` | Partenaire simulé, cinq modes | Défaut trouvé pendant la démonstration réelle : en mode `slow`, le corps était lu après l'attente, alors que le client avait déjà abandonné (erreur `ClientDisconnect`). Corrigé en lisant le corps dès l'arrivée ; ajout de `GET /appels` pour montrer l'idempotence |
| `i4-webhooks/i4_webhooks/stockage.py`, `livraison.py` | Registre en mémoire, timeout, reprises, quarantaine | Timeout appliqué avec `asyncio.timeout` en plus du timeout HTTP, pour qu'il s'applique aussi au transport en mémoire des tests ; filet de sécurité contre une livraison bloquée en `pending` |
| `i4-webhooks/i4_webhooks/recepteur.py` | Application FastAPI | Corps lu à la main (pas de modèle Pydantic dans la route) pour vérifier la signature avant tout parsing et répondre 401/400 au lieu de 422 |
| `i4-webhooks/i4_webhooks/demo.py` | Scénario de bout en bout | Exécuté contre les deux serveurs uvicorn réels ; 12 vérifications conformes, trace dans `preuves/i4/` |
| `i4-webhooks/tests/*.py` | 176 tests | Exécutés avec Python 3.14.2 et 3.11.16 ; chaque étape testée seule, avec les seuls fichiers des étapes précédentes |
| `i4-webhooks/requirements.txt` | Versions figées | `httpx2` retenu au lieu de `httpx` : Starlette 1.7 signale `httpx` comme déprécié pour son `TestClient` |

Vérifications effectuées sur I4 :

- démonstration réelle (`python -m i4_webhooks.demo`) avec le partenaire sur le port 8001 et le récepteur sur le port 8000 : `delivered` pour `ok` et `flaky`, `quarantine` pour `down`, `slow` et `reject`, doublon sans nouvel appel, refus 401, 401, 413 et 400 ;
- recherche dans `preuves/i4/` du secret, d'une signature, du contenu d'un corps et de chemins locaux : aucune occurrence ;
- durées observées conformes au contrat : 0,6 s pour `down` (0,2 + 0,4), 6,6 s pour `slow` (3 × 2 s + 0,2 + 0,4).

## Autres sources

- Documentation Python : [`json`](https://docs.python.org/3/library/json.html) (paramètre `parse_constant`), [`datetime.date`](https://docs.python.org/3/library/datetime.html#date-objects), [`re`](https://docs.python.org/3/library/re.html), [`unicodedata.normalize`](https://docs.python.org/3/library/unicodedata.html#unicodedata.normalize), [`tracemalloc`](https://docs.python.org/3/library/tracemalloc.html), [`argparse`](https://docs.python.org/3/library/argparse.html), [`os.replace`](https://docs.python.org/3/library/os.html#os.replace).
- Format NDJSON / JSON Lines : [jsonlines.org](https://jsonlines.org/) et [ndjson-spec](https://github.com/ndjson/ndjson-spec).
- [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259) : grammaire JSON (pas de `NaN` ni d'`Infinity`).
- Documentation [pytest](https://docs.pytest.org/) : `parametrize`, `tmp_path`, `caplog`, `monkeypatch`.
- Documentation Python : [`hmac`](https://docs.python.org/3/library/hmac.html) (`compare_digest`), [`asyncio.timeout`](https://docs.python.org/3/library/asyncio-task.html#asyncio.timeout), [`logging`](https://docs.python.org/3/library/logging.html).
- Documentation [FastAPI](https://fastapi.tiangolo.com/) (`Request`, `BackgroundTasks`, `TestClient`), [Pydantic](https://docs.pydantic.dev/) (mode strict, validateurs `Annotated`), [httpx2](https://github.com/pydantic/httpx2) (`ASGITransport`, `MockTransport`), [uvicorn](https://www.uvicorn.org/) (`--factory`, `--env-file`).
- Pratiques de signature de webhooks (HMAC du corps brut, horodatage contre le rejeu) : documentations publiques des webhooks [GitHub](https://docs.github.com/webhooks/using-webhooks/validating-webhook-deliveries) et [Stripe](https://docs.stripe.com/webhooks#verify-events).
- En-tête `Idempotency-Key` : brouillon IETF [draft-ietf-httpapi-idempotency-key-header](https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/).
