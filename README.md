# Rattrapage WEB2 — MATRiCE — Noa MIRAMONT

[![Tests](https://github.com/Noa-Miramont/rattrapage_Noa_Miramont-web2/actions/workflows/tests.yml/badge.svg)](https://github.com/Noa-Miramont/rattrapage_Noa_Miramont-web2/actions/workflows/tests.yml)

Rattrapage individuel WEB2. Seuls les deux modules attribués sont réalisés. Chacun vit dans son propre dossier, avec ses dépendances, son environnement virtuel et ses tests, sans aucun import de l'autre module :

- **I3 — Structuration de flux** ([`i3-flux/`](i3-flux/)) : pipeline en ligne de commande qui lit `seances.ndjson`, valide, normalise et déduplique les séances, puis produit `acceptes.ndjson`, `rejets.ndjson` et `stats.json`.
- **I4 — Webhooks & API tierce** (`i4-webhooks/`) : en cours de réalisation, ajouté dans les prochains commits.

Aucun autre module (I2, B1, dashboard, base de données, backend applicatif, React) n'est requis ni réalisé.

Documents associés : [`JUSTIFICATIONS.md`](JUSTIFICATIONS.md) (choix, alternatives, preuves, limites) et [`SOURCES_IA.md`](SOURCES_IA.md) (usages de l'IA et autres sources).

## Prérequis

- Python 3.11 ou plus récent, avec `venv` et `pip` (testé avec Python 3.11 et 3.14).
- Git.
- Aucune base de données, aucun service externe, aucun accès réseau pendant les tests.

Les commandes sont données pour macOS et Linux. Sous Windows (PowerShell), remplacer `python3` par `py` et `source .venv/bin/activate` par `.venv\Scripts\Activate.ps1`.

## Structure du dépôt

```text
.
├── README.md
├── JUSTIFICATIONS.md
├── SOURCES_IA.md
├── .github/workflows/tests.yml    CI : tests à chaque pull request et à chaque push sur main et dev
├── i3-flux/                       module I3, autonome
│   ├── requirements.txt           pytest uniquement (le pipeline n'utilise que la bibliothèque standard)
│   ├── pytest.ini
│   ├── data/seances.ndjson        jeu de données du sujet (12 lignes)
│   ├── i3_flux/
│   │   ├── __main__.py            commande : python -m i3_flux
│   │   ├── regles.py              validation et normalisation d'une séance (fonctions pures)
│   │   ├── pipeline.py            lecture en flux, déduplication, écriture des sorties
│   │   └── mesure_memoire.py      mesure du pic mémoire selon la taille du fichier
│   └── tests/                     test_donnees.py, test_regles.py, test_pipeline.py, test_cli.py, test_preuves.py
└── preuves/
    └── i3/                        sorties, trace de la commande, des tests et de la mesure mémoire
```

## I3 — Structuration de flux

### Installation

```bash
cd i3-flux
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### Lancement

Depuis `i3-flux/`, environnement activé :

```bash
python -m i3_flux data/seances.ndjson --sortie sortie
```

Sortie attendue :

```text
lus=12 acceptes=6 rejets=4 doublons=2
sortie/acceptes.ndjson
sortie/rejets.ndjson
sortie/stats.json
```

Options :

- `--sortie DOSSIER` : dossier des trois fichiers produits, créé s'il n'existe pas (défaut : `sortie/`, ignoré par git).
- `--details` : affiche la décision prise pour chaque ligne (`accepte`, `rejet` avec son motif, `doublon`).

Codes retour : `0` si le fichier a été traité (même avec des rejets), `1` en cas d'erreur d'entrée/sortie (dossier de sortie impossible à créer, disque plein...), `2` si le fichier d'entrée est introuvable ou si les arguments sont invalides.

### Tests

Depuis `i3-flux/`, environnement activé :

```bash
python -m pytest -v
```

Scénarios demandés par le sujet et tests correspondants :

- jeu de données conforme aux deux tableaux du sujet et ligne 12 recopiée telle quelle : `tests/test_donnees.py` ;
- ligne valide : `test_ligne_valide_acceptee_et_normalisee`, `test_seance_valide_normalisee_dans_l_ordre_des_champs` ;
- ligne invalide sans interrompre les suivantes : `test_ligne_invalide_rejetee_sans_interrompre_les_suivantes`, `test_valeur_invalide_rejetee_avec_motif` ;
- doublon : `test_doublon_seule_la_premiere_occurrence_est_retenue`, `test_validation_avant_deduplication_premiere_occurrence_invalide` ;
- JSON malformé : `test_json_malforme_rejete_puis_la_ligne_suivante_est_traitee` ;
- vide : `test_fichier_vide` (pipeline et commande), `test_ligne_vide_comptee_comme_rejet` ;
- jeu complet et invariant : `test_jeu_fourni_resultat_attendu`, `test_jeu_fourni_doublons_lignes_4_et_10` ;
- même fichier, même résultat, sans dépendance au fuseau : `test_meme_fichier_meme_resultat_octet_pour_octet`, `test_resultat_independant_du_fuseau_de_la_machine` ;
- preuves versionnées identiques à une exécution réelle : `tests/test_preuves.py`.

### Résultat sur le jeu fourni

| Ligne | id | Décision | Motif |
|---|---|---|---|
| 1 | s01 | accepté | |
| 2 | s02 | accepté | |
| 3 | s03 | accepté | |
| 4 | s01 | doublon | première occurrence valide en ligne 1 |
| 5 | s04 | accepté | |
| 6 | s05 | accepté | |
| 7 | bad1 | rejet | `title vide` |
| 8 | bad2 | rejet | `date invalide: 2026-02-30` |
| 9 | bad3 | rejet | `period invalide: soir` |
| 10 | s02 | doublon | première occurrence valide en ligne 2 |
| 11 | s06 | accepté | |
| 12 | — | rejet | `JSON malformé` |

Invariant : `lus 12 = acceptes 6 + rejets 4 + doublons 2`.

### Formats produits

`acceptes.ndjson` : une séance normalisée par ligne, précédée de son numéro de ligne d'origine.

```json
{"source_line":1,"id":"s01","date":"2026-10-19","period":"am","group":"A","mode":"DG","title":"React composants","domain":"web","teacherId":"t1","status":"confirmed"}
```

`rejets.ndjson` : numéro de ligne, `id` s'il a pu être lu (sinon `null`) et motif.

```json
{"source_line":8,"id":"bad2","motif":"date invalide: 2026-02-30"}
```

`stats.json` :

```json
{
  "lus": 12,
  "acceptes": 6,
  "rejets": 4,
  "doublons": 2
}
```

### Usage mémoire

Le fichier est lu ligne à ligne et chaque résultat est écrit immédiatement : la mémoire ne dépend pas de la taille du fichier, seulement du nombre d'`id` distincts acceptés (conservés pour la déduplication). Explication détaillée dans [`JUSTIFICATIONS.md`](JUSTIFICATIONS.md#usage-mémoire) et mesure reproductible (environ 15 secondes) :

```bash
python -m i3_flux.mesure_memoire
```

### Preuves

Le dossier [`preuves/i3/`](preuves/i3/) contient :

- `commande.txt` : la commande exécutée avec `--details` et sa sortie ;
- `acceptes.ndjson`, `rejets.ndjson`, `stats.json` : les fichiers produits sur le jeu fourni ;
- `tests.txt` : la sortie de `python -m pytest -v` ;
- `memoire.txt` : la sortie de `python -m i3_flux.mesure_memoire`.

Pour les régénérer depuis `i3-flux/` : `python -m i3_flux data/seances.ndjson --sortie ../preuves/i3`. Le test `tests/test_preuves.py` relance le pipeline et vérifie que les trois fichiers versionnés sont identiques, octet pour octet, à une exécution réelle ; la CI le rejoue sur Linux.

## I4 — Webhooks & API tierce

En cours de réalisation.

## Organisation Git

- `main` : version livrée. Elle ne reçoit que des pull requests depuis `dev`, une fois un module terminé (I3, puis I4). Seul le tout premier commit (`.gitignore`) y a été créé directement, pour pouvoir en dériver `dev`.
- `dev` : branche d'intégration. Elle ne reçoit que des pull requests.
- Une branche par étape, créée depuis `dev` et nommée `type/module-sujet` (`feat/i3-regles`, `docs/i3-preuves`, `ci/tests`...). Elle contient le commit de l'étape, puis elle est fusionnée dans `dev` par pull request (commit de fusion conservé) une fois la CI au vert.
- Messages de commit au format [Conventional Commits](https://www.conventionalcommits.org/fr/) : `feat`, `fix`, `test`, `docs`, `ci`, `chore`, avec le module entre parenthèses.

L'historique complet est visible avec `git log --oneline --graph --all`, et chaque étape dans l'onglet *Pull requests* du dépôt.
