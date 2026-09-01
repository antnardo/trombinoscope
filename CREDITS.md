# Crédits et licences des composants tiers

## Embarqué dans la distribution

### Modèle de détection YuNet

`src/trombinoscope/assets/models/face_detection_yunet_2023mar.onnx` — 227 Ko.

- Source : [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)
- Auteurs : Wei Wu, Weiyuan Peng, Shiqi Yu
- Licence : MIT
- Empreinte SHA-256 : `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`

La licence MIT du dépôt OpenCV Zoo couvre les poids comme le code, ce qui autorise
la redistribution dans une roue PyPI — contrairement, par exemple, aux poids
d'InsightFace ou de MODNet, réservés à un usage non commercial. Voir
[docs/improvements.md](docs/improvements.md), section 1.2.

### Silhouette de remplacement

`src/trombinoscope/assets/placeholder.png` est **dessinée par
`scripts/make_placeholder.py`**, pas téléchargée. C'est la seule façon d'être
certain qu'aucune œuvre tierce — et surtout aucun portrait de personne réelle —
ne se retrouve dans la distribution. Pour la régénérer :

```bash
uv run python scripts/make_placeholder.py
```

## Dépendances d'exécution

| Paquet | Licence |
| --- | --- |
| [NumPy](https://numpy.org/) | BSD-3-Clause |
| [opencv-python-headless](https://github.com/opencv/opencv-python) | Apache-2.0 (OpenCV), MIT (l'empaquetage) |
| [Pillow](https://python-pillow.org/) | MIT-CMU |
| [ReportLab](https://www.reportlab.com/) | BSD-3-Clause |
| [reportlab-layout](https://pypi.org/project/reportlab-layout/) | MIT |
| [pillow-heif](https://github.com/bigcat88/pillow_heif) *(extra `heic`)* | BSD-3-Clause / LGPL-3.0 pour libheif |

## Images de test

**Aucune de ces images n'est versionnée ni distribuée.** Elles sont téléchargées
à la demande par `scripts/fetch_samples.py`, dans `tests/data/portraits/`, un
dossier ignoré par git. Les tests unitaires — l'essentiel de la couverture —
n'en ont pas besoin et fonctionnent sur des images synthétiques.

Toutes proviennent de [Wikimedia Commons](https://commons.wikimedia.org/) et sont
sous licence libre. L'attribution ci-dessous est fournie parce que c'est correct
de le faire, et parce que trois d'entre elles l'exigent.

| Fichier local | Sujet | Licence | Auteur |
| --- | --- | --- | --- |
| `01-hopper.jpg` | Grace Hopper | Domaine public | James S. Davis, U.S. Navy |
| `02-johnson.jpg` | Katherine Johnson | Domaine public | NASA |
| `03-perlman.jpg` | Radia Perlman | Domaine public | Scientist-100 (Wikipédia anglophone) |
| `04-hamilton.jpg` | Margaret Hamilton | CC BY-SA 3.0 | Daphne Weld Nichols |
| `05-liskov.jpg` | Barbara Liskov | CC BY-SA 3.0 | Kenneth C. Zirkel |
| `06-vanrossum.jpg` | Guido van Rossum | CC BY-SA 4.0 | Daniel Stroud |
| `07-knuth.jpg` | Donald Knuth | CC BY-SA 2.5 | Jacob Appelbaum |
| `08-kay.jpg` | Alan Kay | CC BY 2.0 | Marcin Wichary |

Le manifeste écrit à côté des fichiers (`MANIFEST.json`) reprend ces informations
avec l'URL de la page Commons et l'empreinte SHA-256 de chaque téléchargement.

Note sur le partage à l'identique : les clauses SA des licences CC BY-SA
s'appliquent à la **distribution** d'œuvres dérivées. Les portraits recadrés
produits par les tests vivent dans un dossier temporaire et ne sont jamais
publiés ; aucune obligation de partage n'est donc déclenchée. Si vous
redistribuez ces images ou des dérivés, les clauses s'appliquent pleinement.

## Travaux antérieurs

Le paquet ne reprend le code d'aucun projet tiers, mais il s'appuie sur des idées
et des algorithmes publiés. L'[étude d'originalité](docs/prior-art.md) est
détaillée ; les dettes principales :

- **Shades of Gray** — G. Finlayson et E. Trezzi, *Shades of Gray and Colour
  Constancy*, Color Imaging Conference, 2004. L'estimateur d'illuminant par
  défaut est une implémentation directe de cet article.
- **Correction de von Kries** — J. von Kries, 1902, pour la correction diagonale
  par gains indépendants par canal.
- **Retinex / white patch** — E. Land, *The Retinex Theory of Color Vision*,
  Scientific American, 1977.
- **YuNet** — W. Wu, W. Peng, S. Yu, *YuNet: A Tiny Millisecond-level Face
  Detector*, Machine Intelligence Research, 2023.
- **[autocrop](https://github.com/leblancfg/autocrop)** (MIT) — le recadrage à
  proportion de visage constante (`--facePercent`) y préexiste. Aucun code n'en
  est repris, mais l'idée n'est pas de nous.
- **[WhosWho](https://framagit.org/Yvan-Masson/WhosWho)** (GPL-3.0) — le
  concurrent libre le plus abouti, et une référence utile pour ce qu'un
  générateur de trombinoscope doit savoir faire.

## Historique

Ce paquet est la réécriture d'un module personnel non publié, écrit en 2020 pour
produire les trombinoscopes d'une classe préparatoire. La structure du pipeline,
la logique de dernière ligne centrée et les annotations pivotées en viennent
directement. Le reste — modèle de détection, module colorimétrique, découpage en
modules, tests, CLI — a été refait. Voir [CHANGELOG.md](CHANGELOG.md).
