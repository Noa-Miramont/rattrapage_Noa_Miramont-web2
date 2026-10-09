# Justifications

Choix techniques, alternatives écartées, preuves et limites, module par module.

## Organisation du dépôt

- **Un dossier par module** (`i3-flux/`, puis `i4-webhooks/`). Chacun a ses dépendances, son environnement virtuel et ses tests, et aucun n'importe l'autre. Le sujet indique que chaque module est autonome et doit pouvoir être vérifié seul : un correcteur peut installer et tester I3 sans rien installer pour I4.
- **Python pour les deux modules.** La stack de référence cite FastAPI, choix naturel pour le service HTTP d'I4. Utiliser le même langage et le même outil de test (`pytest`) pour I3 évite deux chaînes d'outils. Alternative écartée : Node.js pour I3, qui n'apportait rien de plus pour un pipeline de lignes JSON.
- **CI GitHub Actions** (non exigée). Sur chaque pull request et chaque push sur `main` ou `dev`, elle installe chaque module sur une machine Linux vierge, avec Python 3.11 et 3.14, et lance les tests, dont celui qui compare les preuves versionnées à une exécution réelle. C'est une preuve d'exécution reproductible, en plus des traces.
- **Historique Git en branches** : `main` (livré), `dev` (intégration), puis une branche et une pull request par étape (détail dans le README). Le sujet évalue la cohérence de l'historique : chaque pull request isole une étape, montre la CI passée sur cette étape, et le graphe des fusions retrace la progression module par module. Alternative écartée : tout committer sur `main`, plus simple mais sans revue ni vérification avant intégration.

## I3 — Structuration de flux

### Interprétation du jeu de données

- **Noms des clés JSON** : `id`, `date`, `period`, `group`, `mode`, `title`, `domain`, `teacherId`, `status`. Les règles de normalisation emploient `period`, `group`, `mode`, `teacherId` et `status`, et la ligne 12 imposée emploie `id` et `title`. L'en-tête `domaine` devient donc `domain`, par cohérence (seule hypothèse sans appui direct dans le texte).
- `(chaîne vide)` devient `"title": ""` et `null` devient le `null` JSON.
- La ligne 12 est recopiée à l'octet près ; `tests/test_donnees.py` compare chaque ligne du fichier aux deux tableaux du sujet.

### Règles appliquées

Les règles explicites du sujet sont appliquées telles quelles. Les points que le sujet laisse ouverts ont été tranchés ainsi :

- **`id`, `title` et `domain` doivent être des chaînes non vides.** Le sujet ne les cite pas dans les règles, mais la ligne 7 (`bad1`) n'a aucun autre défaut que son titre vide : la règle « valeur invalide = rejet » ne s'applique que si un titre vide est invalide. Le sujet ne donne aucune liste de domaines, donc `domain` n'est pas restreint à une liste fermée.
- **Valeurs comparées à la casse près** : `Matin` ou `auto` sont refusés. Le sujet liste des valeurs exactes ; les élargir serait inventer une règle. Seule exception : la normalisation Unicode NFC de `period`, car `après-midi` peut être encodé de deux façons (é précomposé ou e suivi d'un accent combinant) tout en étant le même texte.
- **Dates** : expression régulière stricte (`[0-9]` et non `\d`, qui accepterait des chiffres non ASCII), puis construction d'un `datetime.date` pour refuser les dates absentes du calendrier (`2026-02-30` refusé, `2028-02-29` accepté). Aucun appel à l'horloge ni au fuseau de la machine.
- **Règles croisées** (`AUTO` exige `teacherId` null et `proposed` ; `confirmed` exige un formateur) : évaluées sur les valeurs déjà normalisées (`confirme` compte comme `confirmed`) et seulement si les champs concernés sont valides, pour ne pas ajouter un motif qui découle d'une erreur déjà signalée.
- **Tous les motifs d'une ligne** sont réunis dans `motif`, séparés par `; `, dans l'ordre fixe des champs : un correcteur voit d'un coup tout ce qui ne va pas, et le texte est stable d'une exécution à l'autre.
- **Clés inconnues ignorées** et non recopiées : la sortie a toujours exactement les neuf champs du contrat.

### Pipeline

Les étapes demandées sont séparées dans le code : lecture des octets, décodage JSON (`decoder_ligne`), validation et normalisation (`valider_seance`), déduplication (`traiter`), sortie (`executer`).

- **Validation avant déduplication**, comme l'exige le sujet. Une ligne invalide est un rejet, jamais un doublon. Si la première occurrence d'un `id` est invalide, la suivante, valide, est acceptée (test `test_validation_avant_deduplication_premiere_occurrence_invalide`).
- **Déduplication sur l'`id` après normalisation** : deux lignes `s01` aux dates `19/10/2026` et `2026-10-19` sont bien la même séance, la seconde est un doublon. Seule la première occurrence valide est écrite.
- **Lecture en binaire puis décodage ligne par ligne.** En mode texte, un seul octet UTF-8 invalide lèverait une exception au milieu de l'itération et arrêterait tout le traitement, ce qui contredit « une ligne incorrecte ne doit pas interrompre les suivantes ». Ici, seule la ligne fautive est rejetée (`encodage UTF-8 invalide`).
- **Cas limites gérés sans arrêt** : JSON malformé, JSON valide qui n'est pas un objet (`[1, 2]`, `42`), constantes `NaN` et `Infinity` (acceptées par défaut par le module `json` de Python mais absentes du standard JSON), BOM en début de fichier, fins de ligne Windows, dernière ligne sans retour à la ligne.
- **Ligne vide** : comptée dans `lus` et rejetée avec le motif `ligne vide`. `source_line` reste ainsi le vrai numéro de ligne du fichier et l'invariant reste exact. Un fichier entièrement vide donne `0 / 0 / 0 / 0` et trois fichiers de sortie vides.
- **Rejets** : `source_line` et `motif` comme demandé, plus l'`id` lorsqu'il a pu être lu (`null` sinon), pour retrouver la séance concernée sans relire le fichier source.
- **Doublons** : le sujet demande leur nombre dans `stats.json`, pas un fichier dédié. Ils ne sont pas écrits, mais l'option `--details` les affiche avec leur numéro de ligne.
- **Invariant `lus = acceptes + rejets + doublons`** : chaque ligne lue produit exactement un résultat parmi les trois, et l'égalité est vérifiée avant l'écriture de `stats.json` (sinon une erreur est levée et aucune sortie n'est publiée).
- **Même fichier, même résultat** : ordre d'entrée conservé, ordre des clés fixe, séparateurs JSON fixes, UTF-8 sans échappement, fin de ligne `\n` forcée (y compris sous Windows), aucun horodatage, aucune lecture de l'horloge ou du fuseau. Vérifié par deux exécutions comparées octet pour octet, par des exécutions sous trois fuseaux différents (`TZ`), et par `tests/test_preuves.py`, qui compare, en CI sur Linux, une exécution réelle aux preuves générées sous macOS.
- **Écriture atomique** : les sorties sont écrites en `.tmp` puis renommées (`os.replace`) une fois l'invariant vérifié. Un échec en cours de route (disque plein, droits) ne laisse jamais un mélange d'anciennes et de nouvelles sorties.

### Usage mémoire

Le fichier d'entrée est itéré ligne par ligne (`for brut in fichier`) et chaque résultat est écrit aussitôt dans son fichier de sortie. À aucun moment le fichier entier, ni la liste des résultats, n'est en mémoire. La seule structure qui grandit est l'ensemble `ids_acceptes`, indispensable pour reconnaître un doublon : sa taille suit le **nombre d'`id` distincts acceptés**, pas le nombre de lignes. Les rejets et les doublons n'y ajoutent rien. Ce comportement est expliqué en tête de [`i3-flux/i3_flux/pipeline.py`](i3-flux/i3_flux/pipeline.py).

Mesure (`python -m i3_flux.mesure_memoire`, pic d'allocation Python via `tracemalloc`, trace complète dans [`preuves/i3/memoire.txt`](preuves/i3/memoire.txt)) :

| Lignes | Taille du fichier | `id` distincts | Pic mémoire |
|---|---|---|---|
| 10 000 | 1,6 Mo | 10 | 422 Ko |
| 100 000 | 16,1 Mo | 10 | 404 Ko |
| 200 000 | 32,2 Mo | 10 | 400 Ko |
| 10 000 | 1,6 Mo | 10 000 | 1 375 Ko |
| 100 000 | 16,5 Mo | 100 000 | 10 163 Ko |
| 200 000 | 33,1 Mo | 200 000 | 19 962 Ko |

Avec peu d'`id` distincts, le pic reste stable (environ 400 Ko, surtout les tampons d'entrée/sortie) alors que le fichier est multiplié par 20. Avec un `id` différent par ligne, il croît d'environ 100 octets par `id` retenu. Pour un fichier dont les `id` distincts ne tiendraient pas en mémoire, l'ensemble pourrait être remplacé par une table SQLite indexée sur disque, ou par un tri externe sur `id` qui conserve le numéro de ligne. Un filtre de Bloom est écarté : ses faux positifs feraient classer à tort des séances valides comme doublons.

### Alternatives écartées

- **pandas** : charge tout le fichier en mémoire, échoue sur la ligne 12 sans traitement ligne à ligne, et ajoute une dépendance lourde pour neuf champs.
- **Pydantic ou jsonschema** : possibles, mais les règles tiennent en une centaine de lignes. La bibliothèque standard garde I3 sans dépendance d'exécution et donne un contrôle total sur le texte des motifs.
- **`readlines()` ou `read().splitlines()`** : mémoire proportionnelle à la taille du fichier.
- **Dédupliquer avant de valider** : contraire au sujet, et une première occurrence invalide masquerait la suivante valide.

### Correspondance exigences, preuves

| Exigence du sujet | Où c'est fait | Preuve |
|---|---|---|
| Recréer `seances.ndjson` (lignes 1 à 11, puis ligne 12 telle quelle) | `i3-flux/data/seances.ndjson` | `tests/test_donnees.py` (12 lignes comparées aux tableaux) |
| Pipeline CLI lecture, validation, normalisation, déduplication, sortie | `i3_flux/pipeline.py`, `i3_flux/__main__.py` | `preuves/i3/commande.txt`, `tests/test_cli.py` |
| JSON malformé ou valeur invalide : rejet puis on continue | `decoder_ligne`, `valider_seance`, `traiter` | `test_json_malforme_rejete_puis_la_ligne_suivante_est_traitee`, `test_ligne_invalide_rejetee_sans_interrompre_les_suivantes` |
| Dates, périodes, groupes, modes, formateurs, statuts | `i3_flux/regles.py` | `tests/test_regles.py` (paramétrés) |
| AUTO exige `teacherId` null et `proposed` ; `confirmed` exige un formateur | `valider_seance` | `test_auto_*`, `test_confirme_sans_formateur_rejete` |
| Valider avant de dédupliquer, première occurrence valide retenue | `traiter` | `test_validation_avant_deduplication_premiere_occurrence_invalide`, `test_jeu_fourni_doublons_lignes_4_et_10` |
| `acceptes.ndjson` avec `source_line`, `rejets.ndjson` avec `source_line` et motif, `stats.json` | `executer` | `preuves/i3/*.ndjson`, `preuves/i3/stats.json` |
| Invariant `lus = acceptes + rejets + doublons` | `Stats.verifier_invariant` | `test_jeu_fourni_resultat_attendu` |
| Même fichier, même résultat, sans dépendance au fuseau | `executer`, aucune horloge | `test_meme_fichier_meme_resultat_octet_pour_octet`, `test_resultat_independant_du_fuseau_de_la_machine`, `test_preuves.py` en CI |
| Tests valide, invalide, doublon, JSON malformé, vide | `tests/` | `preuves/i3/tests.txt` |
| Commentaire sur l'usage mémoire | en-tête de `pipeline.py`, section ci-dessus | `preuves/i3/memoire.txt` |

### Limites

- Une ligne isolée très longue est chargée entière avant d'être décodée ; il n'y a pas de taille maximale de ligne.
- L'ensemble des `id` acceptés croît avec le nombre d'`id` distincts (voir la mesure ci-dessus).
- Les valeurs ne sont ni mises en minuscules ni débarrassées de leurs espaces : `"A "` ou `"Matin"` sont rejetés, faute de règle dans le sujet qui autorise ces variantes.
- Les doublons ne sont pas écrits dans un fichier, seulement comptés (et visibles avec `--details`).
- Le motif est un texte en français destiné à un humain, pas un code d'erreur stable pour une machine.
