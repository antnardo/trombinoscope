# trombinoscope

[![CI](https://github.com/antnardo/trombinoscope/actions/workflows/ci.yml/badge.svg)](https://github.com/antnardo/trombinoscope/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/trombinoscope.svg)](https://pypi.org/project/trombinoscope/)
[![Python](https://img.shields.io/pypi/pyversions/trombinoscope.svg)](https://pypi.org/project/trombinoscope/)
[![Licence MIT](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

Un dossier de photos brutes, une liste CSV, un PDF prêt à imprimer.

```bash
pip install trombinoscope
trombinoscope build photos/ classe.csv -o trombinoscope.pdf
```

Le paquet détecte le visage sur chaque photo, recadre au même endroit et à la
même taille pour tout le monde, homogénéise les couleurs **à l'échelle du lot**,
puis compose une grille paginée.

## Ce qu'il fait

- **Recadrage à proportion de visage constante.** Que la photo ait été prise à
  deux mètres ou à cinquante centimètres, le visage occupe la même fraction du
  cadre. C'est ce qui rend une planche regardable.
- **Homogénéisation colorimétrique du lot.** Chaque portrait est ramené vers
  l'illuminant et la luminance *médians de la séance*, pas vers un gris neutre
  arbitraire. Sur une séance dont la balance des blancs dérive, la dispersion
  chromatique chute de 78 %. C'est la seule chose que ce paquet fait et que les
  bibliothèques de correction couleur existantes ne font pas — elles travaillent
  toutes image par image. Voir [docs/color.md](docs/color.md).
- **Appariement positionnel.** Les photos triées par nom de fichier suivent
  l'ordre de la liste. Aucun renommage manuel.
- **Mise en page soignée.** Pagination automatique, dernière ligne centrée,
  étiquettes pivotées dans les gouttières, silhouette de remplacement pour les
  absents.
- **Aucune dépendance système.** Ni LaTeX, ni LibreOffice, ni ImageMagick : que
  des roues Python. Installable en conteneur et en CI.
- **Détecteur léger et remplaçable.** YuNet en ONNX, 227 Ko, embarqué dans la
  roue. Le détecteur est un protocole : branchez le vôtre si vous préférez.

## Ce qu'il ne fait pas

Il ne fait **pas de reconnaissance faciale**. Il détecte qu'il y a un visage et
où, jamais qui c'est. C'est une frontière volontaire.

Il ne ramène **pas les carnations vers une teinte de référence** : cela
reviendrait à modifier la couleur de peau des personnes photographiées. Seul
l'illuminant — une propriété de l'éclairage — est estimé.

## Démarrage

```bash
# 1. Un modèle de liste, pour voir le format attendu
trombinoscope template classe.csv

# 2. Vérifier la détection avant de tout lancer
trombinoscope inspect photos/ -o detections/

# 3. Produire le PDF
trombinoscope build photos/ classe.csv -o trombi.pdf \
    --title "MP2 — 2026-2027" --columns 6 --align-eyes
```

Le fichier de liste :

```csv
nom,prenom,tags,groupes,badge
HOPPER,Grace,Maths;LV2 ALL,Gr1;Tr3,1
JOHNSON,Katherine,Info,Gr2;Tr1,
```

Seule la colonne `nom` est obligatoire. `tags` s'affiche dans la gouttière
gauche, `groupes` dans la gouttière droite, `badge` place une étoile en coin.
Les en-têtes sont reconnus sans tenir compte de la casse ni des accents, et les
colonnes inconnues sont ignorées : donnez directement votre export d'ENT.

### Depuis Python

```python
from trombinoscope import BuildOptions, TrombinoscopeBuilder, FramingConfig, GridConfig

options = BuildOptions(
    title="Promotion 2026",
    absent=("DUPONT",),                       # dans la liste, mais pas photographié
    face_choice={"MARTIN": 1},                # deux visages sur sa photo : prendre le second
    framing=FramingConfig(face_ratio=0.5, align_eyes=True),
    grid=GridConfig(columns=6, landscape=True),
)

report = TrombinoscopeBuilder(options).build("photos/", "classe.csv", "trombi.pdf")
print(report.summary())
```

`build` renvoie toujours un `BuildReport` : personnes sans photo, photos sans
personne, photos sans visage détecté, photos à plusieurs visages. Rien n'est
avalé silencieusement.

Les briques s'utilisent aussi séparément — `PortraitFramer` pour recadrer sans
produire de PDF, `BatchColorHarmonizer` pour harmoniser un lot d'images
quelconques, `GridPaginator` pour la mise en page seule.

La liste peut aussi venir d'une base SQLite, via une requête libre dont les
colonnes sont nommées avec `AS` :

```python
from trombinoscope import load_sqlite

people = load_sqlite("base.db", "SELECT nom, prenom, redoublant AS badge FROM eleves ORDER BY nom")
```

Les [`examples/`](examples/) vont du minimal en trois lignes au tour complet des
options, jusqu'à un cas réel branché sur une base SQLite.

## Quand utiliser autre chose

Ce paquet occupe une case étroite. L'[étude d'originalité](docs/prior-art.md) est
détaillée et n'édulcore rien ; en résumé :

| Votre besoin | Préférez |
| --- | --- |
| Une interface graphique, sans écrire de code | [WhosWho](https://framagit.org/Yvan-Masson/WhosWho) |
| Vos photos sont déjà dans PRONOTE | Le trombinoscope de PRONOTE |
| Seulement recadrer des portraits sur le visage | [autocrop](https://github.com/leblancfg/autocrop) |
| Des photos d'identité aux normes, fond détouré | [HivisionIDPhotos](https://github.com/Zeyi-Lin/HivisionIDPhotos) |
| Une planche image en une ligne de shell | `montage` d'ImageMagick |
| **Un PDF reproductible depuis un script ou une CI** | **`trombinoscope`** |

[WhosWho](https://framagit.org/Yvan-Masson/WhosWho) mérite d'être mentionné
d'emblée : c'est un logiciel libre, vivant, qui couvre l'essentiel du même
besoin. Si une application de bureau vous convient, utilisez-la. Les différences
réelles sont l'absence d'harmonisation colorimétrique inter-photos de son côté,
et l'absence d'interface graphique du nôtre.

## Documentation

- [DOC.md](docs/DOC.md) — référence complète : options, API, formats, recettes
- [color.md](docs/color.md) — l'étude colorimétrique, mesures à l'appui
- [prior-art.md](docs/prior-art.md) — état de l'art et étude d'originalité
- [improvements.md](docs/improvements.md) — pistes examinées et décisions
- [legacy-review.md](docs/legacy-review.md) — revue du module de 2020 dont ce
  paquet est issu, et ce que la réécriture en a tiré
- [CREDITS.md](CREDITS.md) — modèles, images et travaux réutilisés

## Installation

```bash
pip install trombinoscope           # cœur
pip install 'trombinoscope[heic]'   # + lecture des .heic de l'iPhone
```

Python 3.11 et suivants, testé sur Linux, macOS et Windows.

La dépendance OpenCV est `opencv-python-headless` : aucune bibliothèque
graphique système n'est requise. Si votre environnement contient déjà
`opencv-python`, installez avec `--no-deps` pour éviter que les deux
distributions ne se disputent le module `cv2`.

## Développement

```bash
git clone https://github.com/antnardo/trombinoscope
cd trombinoscope
uv sync --group dev

uv run pytest -m "not integration"    # rapide, sans réseau
uv run ruff format src tests scripts
uv run ruff check src tests scripts

uv run python scripts/fetch_samples.py   # portraits d'exemple, non versionnés
uv run pytest -m integration
uv run python scripts/color_bench.py --output artifacts
```

Le dépôt ne contient **aucune photographie**. Les portraits utilisés par les
tests d'intégration sont téléchargés à la demande depuis Wikimedia Commons et la
CI vérifie qu'aucun fichier image n'apparaît ni dans le dépôt ni dans la roue.

## Licence

MIT — voir [LICENSE](LICENSE). Les composants tiers embarqués ou téléchargés ont
leurs propres licences, toutes recensées dans [CREDITS.md](CREDITS.md).
