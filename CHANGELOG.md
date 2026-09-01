# Journal des modifications

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le
versionnage sémantique.

## [Non publié]

## [0.1.1]

### Corrigé

- **`--font-size` n'avait aucun effet sur les noms.** L'option atteignait le
  canevas ReportLab — donc les `drawString` bruts — mais pas le style
  `Noms` utilisé pour le bloc nom/prénom, qui restait figé à 10 pt, la taille
  héritée de `Normal`. Le rendu dérive désormais son propre style de
  `styles["Noms"]` en y appliquant `font_size`, ce qui fait aussi varier la
  hauteur des rangées et donc la pagination. Signalé par un utilisateur qui
  cherchait à faire tenir des noms longs sur douze colonnes.

### Ajouté

- `GridConfig.name_leading` : interligne du bloc nom/prénom, en points.
  `None` prend `font_size × 1,25`.
- Validation de `font_size` et `name_leading`, tous deux strictement positifs.

### Modifié

- **`GridConfig.font_size` passe de 12 à 10 pt par défaut.** C'est la taille que
  les noms avaient en pratique en 0.1.0, quand l'option était inerte : le défaut
  ne déplace donc aucun rendu existant, seul un `--font-size` explicite agit.
- `PdfCanvas.draw_paragraph` et `paragraph_height` acceptent un `ParagraphStyle`
  en plus d'un nom de style.

## [0.1.0]

Première version publique. C'est la réécriture d'un module personnel de 2020,
jamais publié, qui produisait les trombinoscopes d'une classe préparatoire.

### Ajouté

- Interface en ligne de commande `trombinoscope` avec trois sous-commandes :
  `build`, `inspect` et `template`.
- `BatchColorHarmonizer` : harmonisation colorimétrique **à l'échelle du lot**,
  en deux passes, vers l'illuminant et la luminance médians de la séance. C'est
  la seule fonction que les bibliothèques de correction couleur existantes ne
  fournissent pas — elles travaillent toutes image par image. Sur une séance
  simulée, la dispersion chromatique chute de 78 %.
- Estimateurs d'illuminant `GrayWorldEstimator`, `ShadesOfGrayEstimator`
  (défaut, `p = 6`) et `WhitePatchEstimator`, calculés **en lumière linéaire**.
- `LuminanceMatcher` : normalisation d'exposition par correction gamma, mesurée
  sur le visage et non sur l'image entière.
- Paramètre `strength` pour atténuer la correction de teinte.
- `PortraitFramer` : recadrage à proportion de visage constante, et redressement
  optionnel de la ligne des yeux (`align_eyes`).
- Détection par YuNet, avec les cinq points caractéristiques. Le détecteur est un
  protocole injectable.
- `RosterLoader` : lecture CSV et JSON, séparateur détecté, en-têtes reconnus
  sans tenir compte de la casse ni des accents, colonnes inconnues ignorées.
- `load_sqlite` : liste chargée depuis une requête SQLite libre, base ouverte en
  lecture seule, colonnes nommées avec `AS` pour traduire un schéma métier.
- `GridConfig.title_top` et `title_skip` se comptent en **hauteurs de ligne**
  (multiples de `font_size`) et non en millimètres, de sorte que l'espacement du
  titre suive sa taille. `PdfCanvas.draw_paragraph` tient désormais compte des
  `spaceBefore` / `spaceAfter` du style, comme un flowable ReportLab.
- `GridConfig.annotation_layout`, `badge_corner`, `badge_inset`, `logo_position`,
  `logo_width`, `logo_margin` et `logo_offset` : placement des annotations
  pivotées, de l'étoile et du logo. Le logo se pose par défaut en haut à droite,
  et l'étoile est centrée sur le coin de la photo.
- `examples/` : trois exemples commentés — minimal, tour complet des options,
  et reproduction d'un trombinoscope de classe préparatoire depuis sa base
  SQLite avec la mise en page historique.
- `BuildReport` : rapport structuré des personnes sans photo, photos sans
  personne, photos sans visage et photos à plusieurs visages.
- `GridPaginator` : pagination testable indépendamment de ReportLab.
- Lecture des fichiers HEIC via l'extra `[heic]`.
- 322 tests, dont l'essentiel tourne sur des images synthétiques et un détecteur
  bouchon : ni réseau, ni modèle, ni photographie. Intégration continue sur
  Linux, macOS et Windows, en Python 3.11 à 3.14.
- Documentation : [étude colorimétrique](docs/color.md), [état de l'art et étude
  d'originalité](docs/prior-art.md), [pistes d'amélioration](docs/improvements.md),
  [revue du module de 2020](docs/legacy-review.md).

### Corrigé

Défauts de la version 2020. L'analyse détaillée, extraits de code à l'appui, est
dans [docs/legacy-review.md](docs/legacy-review.md) ; le code source, lui, ne
commente que ce qu'il fait.

- **La correction colorimétrique était inopérante.**
  `cv2.convertScaleAbs(image, alpha, beta)` place `alpha` en position `dst` et
  `beta` en position `alpha` — la signature réelle est
  `convertScaleAbs(src, dst, alpha, beta)`. Le gain calculé n'était jamais
  appliqué et les images ressortaient saturées. Un test de non-régression
  verrouille l'appel nommé. Détail dans [docs/color.md](docs/color.md).
- **L'appariement se décalait silencieusement.** Une photo sur laquelle aucun
  visage n'était trouvé faisait `continue` sans avancer l'indice de la personne :
  toutes les suivantes changeaient de photo. L'appariement est désormais résolu
  avant toute détection.
- **Les annotations se retrouvaient sous les mauvaises photos** quand la dernière
  ligne était centrée : placement et annotations recalculaient l'indice de la
  personne de deux façons incompatibles. Une `IndexError` était même possible sur
  une dernière ligne incomplète.
- **`UnboundLocalError`** lorsque les groupes étaient affichés sans étiquettes :
  la coordonnée `x` n'était calculée que dans la branche des étiquettes.
- **Exception sur les cadrages débordant** de la photo source, par recollage
  manuel de tranches de tableau.
- **Division par zéro** de l'étalement d'histogramme sur une image uniforme.
- **Étalement calculé sur l'image entière**, donc sur le fond plutôt que sur le
  sujet.
- **Chemins non-ASCII** : `cv2.imread` et `cv2.imwrite` échouent silencieusement
  sous Windows ; la lecture et l'écriture passent par `imdecode` / `imencode`.
- **`os.system` avec un chemin concaténé** dans l'ouverture du PDF : un espace ou
  une apostrophe cassait la commande.
- **Sensibilité à la casse du système de fichiers** devinée en écrivant un
  fichier temporaire dans le dossier de l'utilisateur, avec un cache partagé
  entre tous les dossiers.
- **Déduplication en O(n²)** par `os.path.samefile`.

### Modifié

- **Modèle de détection** : SSD ResNet-10 Caffe (10 Mo) remplacé par YuNet ONNX
  (227 Ko), qui fournit en plus les points caractéristiques. L'arborescence
  d'origine transportait 142 Mo de modèles, dont 132 Mo jamais chargés par le
  code — le prédicteur 68 points de dlib et un fichier PyTorch. `readNetFromCaffe`
  a par ailleurs disparu d'OpenCV 5 : l'ancienne approche n'était plus viable.
- **`Eleve` devient `Person`.** Les champs de prépa française (`cube`, `LV1`,
  `LV2`, `option`, `groupe`, `groupecolle`) laissent place à deux listes libres
  d'étiquettes, qui couvrent le cas d'origine sans imposer son vocabulaire. Table
  de correspondance dans [docs/DOC.md](docs/DOC.md), section 10.
- **`trombinoscope/logging.py` devient `trombinoscope/log.py`** et s'appuie sur
  la bibliothèque standard. L'ancien nom masquait `logging` pour tout import
  absolu depuis l'intérieur du paquet.
- **`warning()` ne bloque plus sur `input()`.** La pause interactive devient un
  choix explicite de l'appelant, désactivé par défaut.
- **Aucun modèle n'est chargé à l'import.** Le réseau était construit au niveau
  module : un simple `import trombinoscope` le payait, et échouait si le fichier
  manquait, même pour n'utiliser que la mise en page.
- **`pkg_resources` remplacé par `importlib.resources`** — le premier a disparu
  de Python 3.12.
- **Le module local `pdf_maker` (412 lignes, non publié) est réduit** à ce dont
  le trombinoscope a besoin. La grille est dessinée directement sur le canevas
  plutôt qu'avec des tableaux ReportLab imbriqués, ce qui rend la position des
  annotations traçable.
- **Dépendance `opencv-python-headless`** plutôt que `opencv-python` : aucune
  bibliothèque graphique système requise.
- **L'étalement d'histogramme est désactivé par défaut.** Une fois son bug
  corrigé, la mesure montre qu'il dégrade la cohérence du lot.
- **La rotation de redressement des yeux** utilisait l'opposé de l'inclinaison,
  ce qui l'aurait doublée au lieu de la corriger. Détecté par un test lors de la
  réécriture ; la fonctionnalité n'avait jamais été branchée dans la version
  d'origine.

### Supprimé

- Toutes les photographies personnelles : portraits d'élèves, PDF de
  trombinoscopes nominatifs, logo d'établissement. Le dépôt ne contient plus
  aucune image de personne, et la CI vérifie qu'il n'en apparaît ni dans le dépôt
  ni dans la roue. Les tests d'intégration téléchargent à la demande des
  portraits sous licence libre — voir [CREDITS.md](CREDITS.md).
- `FaceAligner` et le prédicteur 68 points de dlib (95 Mo), jamais utilisés : le
  redressement se fait maintenant avec les points de YuNet, dans la même
  transformation affine que le recadrage.
- Le fichier `HR18-300W.pth` (37 Mo), auquel aucun code ne faisait référence.
- Le cache `photos.pkl` écrit dans le dossier de l'utilisateur.
- Le guide ReportLab en PDF (548 Ko) versionné dans l'arborescence.

[Non publié]: https://github.com/antnardo/trombinoscope/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/antnardo/trombinoscope/releases/tag/v0.1.1
[0.1.0]: https://github.com/antnardo/trombinoscope/releases/tag/v0.1.0
