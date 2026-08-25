# Documentation de référence

Pour une prise en main rapide, voir le [README](../README.md). Ce document décrit
le fonctionnement en détail : formats acceptés, options, API, et les recettes qui
servent en pratique.

## Table des matières

- [1. Le modèle mental](#1-le-modèle-mental)
- [2. Les entrées](#2-les-entrées)
- [3. La ligne de commande](#3-la-ligne-de-commande)
- [4. L'API Python](#4-lapi-python)
- [5. Le cadrage](#5-le-cadrage)
- [6. Les couleurs](#6-les-couleurs)
- [7. La mise en page](#7-la-mise-en-page)
- [8. Diagnostic](#8-diagnostic)
- [9. Recettes](#9-recettes)
- [10. Migration depuis la version 2020](#10-migration-depuis-la-version-2020)

## 1. Le modèle mental

```text
photos/*.jpg  ─┐
               ├─ appariement positionnel ─┐
liste.csv     ─┘                           │
                                           ▼
                        ┌──── passe 1 : détecter → recadrer → mesurer
                        │
                        │     (référence du lot : illuminant et luminance médians)
                        │
                        └──── passe 2 : corriger → écrire les portraits
                                           │
                                           ▼
                                    grille paginée → PDF
```

Deux points de conception méritent d'être connus.

**L'appariement est résolu avant toute détection.** Photos et personnes sont
associées par position, une fois pour toutes. Un échec de détection ultérieur ne
peut donc pas décaler les personnes suivantes.

**Le traitement se fait en deux passes.** La correction couleur a besoin de
connaître tout le lot avant de corriger quoi que ce soit : la référence est la
médiane des mesures. Conséquence pratique : les portraits recadrés sont gardés en
mémoire entre les deux passes, environ 360 Ko par personne à la taille par
défaut.

## 2. Les entrées

### 2.1 Le dossier de photos

Les fichiers sont triés par **nom de fichier**, insensiblement à la casse. Le
tri définit l'ordre, donc l'appariement : nommez vos photos de façon à ce que
l'ordre lexicographique corresponde à celui de votre liste. `01.jpg`, `02.jpg`…
plutôt que `1.jpg`, `2.jpg`, `10.jpg` — sinon `10` se glisse entre `1` et `2`.

Extensions lues : `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tif`, `.tiff`, `.webp`, et
`.heic` / `.heif` si `pillow-heif` est installé (`pip install
'trombinoscope[heic]'`).

Les sous-dossiers et les fichiers cachés sont ignorés, ce qui permet de laisser
`portraits/` et `detections/` dans le même dossier sans qu'ils soient repris en
entrée à la relance suivante.

### 2.2 La liste

CSV ou JSON. Le séparateur du CSV est détecté automatiquement parmi `,`, `;`,
tabulation et `|`, et le BOM des exports Excel est retiré.

| Colonne | Alias reconnus | Rôle |
| --- | --- | --- |
| `nom` | `lastname`, `last_name`, `name`, `surname`, `famille` | **Obligatoire** |
| `prenom` | `firstname`, `first_name`, `given`, `prenoms` | Affiché sous le nom |
| `tags` | `tag`, `options`, `etiquettes`, `labels` | Gouttière gauche |
| `groupes` | `groupe`, `groups`, `group` | Gouttière droite |
| `badge` | `etoile`, `star`, `cube`, `flag` | Étoile en coin |

Les en-têtes sont normalisés : casse, accents, espaces et tirets sont ignorés,
donc `Prénom`, `PRENOM` et `first-name` désignent la même colonne. **Les colonnes
inconnues sont simplement ignorées**, ce qui permet de donner un export complet
sans le retailler.

Dans `tags` et `groupes`, les étiquettes sont séparées par `;` — ou par `,` si la
cellule n'en contient pas, auquel cas il faut penser à guillemeter la cellule.

`badge` accepte `1`, `true`, `vrai`, `oui`, `yes`, `x` — insensiblement à la
casse. Tout le reste vaut faux.

L'ordre du fichier est conservé : c'est lui qui définit l'ordre d'affichage.

### 2.3 Depuis une base SQLite

`load_sqlite` prend une requête libre et interprète ses colonnes comme celles
d'un CSV. Nommez-les avec `AS` pour traduire un schéma métier sans toucher à la
base, qui est d'ailleurs ouverte en lecture seule.

```python
from trombinoscope import load_sqlite

people = load_sqlite(
    "base.db",
    """
    SELECT nom, prenom, cube AS badge,
           option || ';' || LV1 AS tags,
           'Gr' || groupe AS groupes
    FROM eleves ORDER BY nom
    """,
)
```

L'ordre de la requête définit l'appariement : pensez à un `ORDER BY`. Pour des
noms français, retriez ensuite avec `remove_accents`, l'ordre SQL comparant les
points de code et plaçant « Étienne » après « Zola ».

Un exemple complet, branché sur une vraie base de classe préparatoire, est dans
[`examples/03_sqlite_prepa.py`](../examples/03_sqlite_prepa.py).

## 3. La ligne de commande

### 3.1 `trombinoscope build`

```bash
trombinoscope build PHOTOS LISTE -o SORTIE.pdf [options]
```

Codes de retour : `0` si tout va bien, `1` si le rapport signale un problème
(personne sans photo, photo sans personne, visage non détecté), `2` sur une
erreur de fichier ou d'argument. Le PDF est produit dans tous les cas où c'est
possible — un code `1` ne signifie pas qu'il manque.

#### Général

| Option | Défaut | Effet |
| --- | --- | --- |
| `--title` | `Trombinoscope` | Titre en tête de chaque page |
| `--subtitle` | — | Ligne sous le titre |
| `--absent NOM…` | — | Présents dans la liste, sans photo. Insensible à la casse |
| `--logo CHEMIN` | — | Image placée en bas à droite |
| `--portraits DOSSIER` | `PHOTOS/portraits` | Où écrire les portraits recadrés |
| `--debug-dir DOSSIER` | — | Images de détection annotées |
| `--open` | — | Ouvre le PDF à la fin |
| `--interactive` | — | Pause après chaque avertissement, pour un suivi pas à pas |
| `-v`, `-vv` | — | Journal en niveau info, puis debug |

#### Détection

| Option | Défaut | Effet |
| --- | --- | --- |
| `--backend` | `yunet` | `yunet` ou `haar` (OpenCV 4.x seulement) |
| `--confidence` | `0.6` | Score minimal d'une détection retenue |
| `--pick NOM=INDEX` | — | Visage à retenir. Répétable. `-1` : aucun |

#### Cadrage

| Option | Défaut | Effet |
| --- | --- | --- |
| `--face-ratio` | `0.55` | Largeur du visage ÷ largeur du cadre |
| `--aspect-ratio` | `1.333` | Hauteur ÷ largeur du portrait |
| `--face-y` | `0.5` | Position verticale du visage, 0 en haut, 1 en bas |
| `--portrait-width` | `300` | Largeur du portrait produit, en pixels |
| `--align-eyes` | — | Redresse la ligne des yeux (backend `yunet`) |

#### Couleur

| Option | Défaut | Effet |
| --- | --- | --- |
| `--white-balance` | `shades-of-gray` | `none`, `grayworld`, `shades-of-gray`, `white-patch` |
| `--minkowski-p` | `6.0` | Exposant de `shades-of-gray` |
| `--strength` | `1.0` | Intensité de la correction de teinte, de 0 à 1 |
| `--max-gain` | `2.0` | Gain maximal par canal |
| `--auto-levels PCT` | `0` (désactivé) | Étalement d'histogramme |
| `--no-harmonize` | — | Corrige chaque photo isolément |

#### Mise en page

| Option | Défaut | Effet |
| --- | --- | --- |
| `-c`, `--columns` | `5` | Nombre de colonnes |
| `--padding` | `0.2` | Blanc par colonne, en fraction |
| `--line-skip` | `8.0` | Espace entre lignes, en points |
| `--font-size` | `12.0` | Taille des noms, en points |
| `--landscape` | — | Page en paysage |
| `--no-center-last-row` | — | Aligne la dernière ligne à gauche |
| `--no-tags`, `--no-groups`, `--no-badges` | — | Masque une série d'annotations |

`GridConfig` expose des réglages sans équivalent en ligne de commande :

| Champ | Défaut | Effet |
| --- | --- | --- |
| `annotation_layout` | `"gutters"` | `"gutters"` : `tags` à gauche, `groups` à droite. `"left"` : les deux dans la gouttière gauche, `tags` partant du bas et `groups` calé sur le haut |
| `badge_corner` | `"top-right"` | Coin de la photo portant l'étoile |
| `badge_inset` | `0.0` | Décalage de l'étoile vers l'intérieur, en mm. À `0` elle est centrée sur le coin et déborde de moitié |
| `logo_position` | `"top-right"` | Coin de la page portant le logo |
| `logo_width` | `30.0` | Largeur du logo, en mm |
| `logo_margin` | `5.0` | Distance au bord de la zone de contenu, en mm |
| `logo_offset` | `(0.0, 0.0)` | Décalage fin en mm (`x` vers la droite, `y` vers le haut), pour faire mordre le logo sur la marge |
| `title_top` | `0.0` | Blanc au-dessus du titre, en **hauteurs de ligne** (multiples de `font_size`) |
| `title_skip` | `1.0` | Blanc entre le bas du titre et la première rangée, en hauteurs de ligne |

Ces deux derniers se comptent en hauteurs de ligne et non en millimètres, pour
que l'espacement suive la taille du titre quand on la change. Le bas du titre
inclut le `spaceAfter` de son style, comme le ferait un flowable ReportLab.

### 3.2 `trombinoscope inspect`

Détecte les visages et écrit des images annotées, sans rien produire d'autre.
À lancer avant un build complet pour régler le seuil et repérer les photos à
plusieurs visages. Retourne `0` si toutes les photos ont exactement un visage.

```bash
trombinoscope inspect photos/ -o detections/ --confidence 0.7
```

L'index affiché sur chaque boîte est celui à passer à `--pick`.

### 3.3 `trombinoscope template`

Écrit un CSV d'exemple au bon format.

```bash
trombinoscope template classe.csv
```

## 4. L'API Python

### 4.1 Le pipeline complet

```python
from trombinoscope import BuildOptions, TrombinoscopeBuilder
from trombinoscope import ColorConfig, FramingConfig, GridConfig

options = BuildOptions(
    title="MP2 — 2026-2027",
    absent=("DUPONT", "MARTIN"),
    face_choice={"DURAND": 1, "PETIT": -1},
    framing=FramingConfig(face_ratio=0.5, align_eyes=True),
    color=ColorConfig(strength=0.75),
    grid=GridConfig(columns=6, landscape=True),
)

report = TrombinoscopeBuilder(options).build("photos/", "classe.csv", "trombi.pdf")

if not report.ok:
    print(report.summary())
    for path in report.multiple_faces:
        print(f"plusieurs visages : {path}")
```

### 4.2 Les briques séparément

Chaque étape est utilisable seule. C'est délibéré : le pipeline n'est qu'un
enchaînement.

```python
from trombinoscope import PortraitFramer, YuNetDetector, read_image, write_image

detector = YuNetDetector(confidence=0.7)
framer = PortraitFramer()

image = read_image("photo.jpg")
detections = detector.detect(image)
write_image("portrait.jpg", framer.frame(image, detections[0] if detections else None))
```

Harmoniser un lot d'images quelconques, sans détection ni PDF :

```python
from trombinoscope import BatchColorHarmonizer
from trombinoscope.models import ColorConfig

harmonizer = BatchColorHarmonizer(ColorConfig(estimate_on_face=False))
for image in images:
    harmonizer.measure(image, None)          # passe 1
corrected = [harmonizer.transform(i, None) for i in images]   # passe 2
```

La mise en page seule, à partir de portraits déjà préparés :

```python
from pathlib import Path
from trombinoscope import Person, render_pdf

people = [
    Person("HOPPER", "Grace", tags=("Maths",), badge=True, portrait=Path("g.jpg")),
    Person("KNUTH", "Donald", portrait=Path("d.jpg")),
]
render_pdf(people, "planche.pdf", title="Pionniers")
```

### 4.3 Brancher un autre détecteur

`FaceDetector` est un protocole : n'importe quel objet avec une méthode
`detect(image) -> list[Detection]` convient.

```python
from trombinoscope.models import Box, Detection

class MonDetecteur:
    def detect(self, image):
        # … votre modèle …
        return [Detection(box=Box(x0, y0, x1, y1), confidence=0.9)]

TrombinoscopeBuilder(options, detector=MonDetecteur()).build(...)
```

C'est aussi ce qui rend le pipeline testable sans modèle : la suite de tests
utilise un détecteur bouchon.

### 4.4 Journalisation

Le paquet écrit sur le logger standard `trombinoscope` et n'installe aucun
handler à l'import.

```python
import logging
from trombinoscope import configure, set_interactive

configure(verbosity=1)                       # handler console lisible
logging.getLogger("trombinoscope").setLevel(logging.DEBUG)   # ou à votre main
set_interactive(True)                        # pause après chaque avertissement
```

`set_interactive(False)` est le défaut : une bibliothèque importée ne doit jamais
bloquer sur `input()`.

## 5. Le cadrage

`face_ratio` est le réglage important. C'est la fraction de la **largeur du
cadre** occupée par la boîte du visage. Elle est constante pour tout le lot,
quelle que soit la distance de prise de vue — c'est précisément ce qui rend les
portraits comparables.

| Valeur | Rendu |
| --- | --- |
| 0,35 | Plan large, buste et épaules |
| 0,55 | Portrait classique *(défaut)* |
| 0,70 | Serré, style photo d'identité |

`face_y` place le visage verticalement : 0 le colle en haut, 1 en bas, 0,5 le
centre. Pour un rendu de photo d'identité, `face_y` autour de 0,4 laisse un peu
plus d'espace sous le menton.

Quand le cadre déborde de la photo source, la zone manquante est remplie avec
`FramingConfig.fill` (blanc par défaut). Aucune exception n'est levée.

**Sans visage détecté**, la photo entière est mise au format demandé, avec des
bandes de remplissage. C'est délibéré : mieux vaut un portrait mal cadré mais
entier qu'un recadrage arbitraire qui décapiterait le sujet.

`align_eyes` fait pivoter l'image pour horizontaliser la ligne des yeux. Cela
demande les points caractéristiques, donc le backend `yunet`. Sur des photos
prises appareil à main levée, le gain est net ; sur un studio bien réglé, c'est
inutile et cela introduit des coins vides.

## 6. Les couleurs

Le détail complet, avec les mesures, est dans [color.md](color.md). En pratique :

- **le défaut convient** pour une séance photo unique dont l'éclairage varie un
  peu — c'est le cas d'usage visé, et la dispersion chromatique y chute de 78 % ;
- **si le résultat paraît sur-corrigé**, baissez `--strength` à 0,6 ou 0,7 ;
- **si le lot n'est pas une séance** (photos d'origines et d'époques diverses),
  l'harmonisation a moins de sens : `--white-balance none` est un choix
  raisonnable ;
- **`--no-harmonize`** corrige chaque photo vers le gris neutre indépendamment.
  Meilleure neutralité par image, mais aucune cohérence d'exposition entre les
  photos.

## 7. La mise en page

Le nombre de lignes par page est calculé à partir de la hauteur disponible et de
la taille des photos, elle-même déduite du nombre de colonnes. Augmenter
`--columns` réduit donc les photos et augmente le nombre de lignes par page.

`--padding` est la fraction de la largeur de colonne laissée vide autour de
chaque photo. C'est aussi ce qui crée les gouttières où s'écrivent les
annotations : en dessous de 0,15, elles deviennent illisibles.

**La dernière ligne est centrée** quand elle est incomplète, et sa disposition
dépend des parités. Avec cinq colonnes et deux photos, la colonne médiane reste
vide pour préserver la symétrie — `. P . P .` plutôt que `. P P . .`. Quand
aucune disposition symétrique n'existe (colonnes paires, photos impaires), le
bloc est centré au mieux, à une demi-colonne près.

Les **annotations pivotées** occupent les gouttières : `tags` à gauche, `groupes`
à droite, lues de bas en haut. L'étoile de `badge` va dans le coin supérieur
droit de la photo. Aucune troncature automatique pour l'instant : une étiquette
trop longue déborde silencieusement.

## 8. Diagnostic

`BuildReport` porte tout ce qui a posé problème :

| Attribut | Contenu |
| --- | --- |
| `unmatched_people` | Noms sans photo |
| `unmatched_photos` | Photos sans personne |
| `no_face` | Photos où aucun visage n'a été détecté |
| `multiple_faces` | Photos à plusieurs visages |
| `ok` | `True` si aucune des trois premières listes n'est remplie |
| `summary()` | Phrase récapitulative |

**Plusieurs visages détectés.** Lancez `inspect`, regardez l'image annotée, notez
l'index du bon visage, puis `--pick NOM=INDEX`. Un index négatif conserve la
photo entière sans recadrage.

**Aucun visage détecté.** Baissez `--confidence` (jusqu'à 0,3). Si la photo est
un profil marqué ou très sombre, YuNet peut échouer : `--pick NOM=-1` conserve
la photo telle quelle.

**Décalage de l'appariement.** Vérifiez le tri des noms de fichiers, et que
`--absent` liste bien tout le monde. Le rapport signale les surplus des deux
côtés.

## 9. Recettes

Trombinoscope de classe, format serré, six colonnes :

```bash
trombinoscope build photos/ classe.csv -o trombi.pdf \
    --columns 6 --face-ratio 0.6 --padding 0.15 --title "MP2"
```

Planche paysage pour affichage en salle :

```bash
trombinoscope build photos/ classe.csv -o mur.pdf \
    --landscape --columns 8 --no-tags --no-groups --font-size 10
```

Photos prises appareil à main levée, éclairage variable :

```bash
trombinoscope build photos/ classe.csv -o trombi.pdf \
    --align-eyes --strength 0.8 -v
```

Régler la détection avant de lancer le build :

```bash
trombinoscope inspect photos/ -o detections/ --confidence 0.7 \
  && trombinoscope build photos/ classe.csv -o trombi.pdf --confidence 0.7
```

Convertir des HEIC d'iPhone au passage :

```bash
pip install 'trombinoscope[heic]'
trombinoscope build photos/ classe.csv -o trombi.pdf
```

## 10. Migration depuis la version 2020

Le module personnel dont ce paquet est issu n'a jamais été publié ; cette section
n'intéresse que son auteur, mais elle documente les ruptures d'API. La revue
technique de ce module — ce qui a motivé chaque changement — est dans
[legacy-review.md](legacy-review.md).

| Avant | Maintenant |
| --- | --- |
| `Eleve(nom, prenom, cube, LV1, LV2, option, groupe, groupecolle)` | `Person(last_name, first_name, tags, groups, badge)` |
| `search_and_detect_faces(folder, eleves, seuil, …)` | `TrombinoscopeBuilder(options).build(photos, roster, output)` |
| `make_pdf(eleves, file, year, titre, pdf_kwargs)` | `render_pdf(people, path, title=…, config=GridConfig(…))` |
| Base SQLite privée | CSV ou JSON |
| `trombinoscope.logging` | `trombinoscope.log`, sur la stdlib |
| `visualise(file)` | `open_with_system_viewer(path)` |
| `detect_faces(file, seuil)` | `YuNetDetector(confidence=…).detect(image)` |
| SSD ResNet-10 Caffe, 10 Mo | YuNet ONNX, 227 Ko |

Les champs de prépa (`cube`, `LV1`, `LV2`, `option`, `groupe`, `groupecolle`) se
transposent sans perte :

```python
Person(
    last_name=nom,
    first_name=prenom,
    tags=(option, lv1, lv2),      # gouttière gauche, comme avant
    groups=(f"Gr{groupe}", f"Tr{groupecolle}"),
    badge=cube,
)
```

Points de vigilance :

- `warning()` ne bloque plus sur `input()`. Passez `--interactive` ou
  `set_interactive(True)` pour retrouver l'ancien comportement.
- `pkg_resources` a disparu de Python 3.12 : l'ancien module ne s'importe plus du
  tout sur les versions récentes.
- La correction couleur produit désormais un résultat. Elle n'en produisait
  aucun — voir [color.md](color.md), section 1.
