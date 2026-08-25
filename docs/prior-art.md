# État de l'art et étude d'originalité

> Recherche documentaire effectuée le 24 août 2026. Les licences et versions
> indiquées ont été vérifiées sur les dépôts et sur l'API JSON de PyPI au moment
> de la rédaction.

## A) État de l'art / projets existants

### A.1 Générateurs de trombinoscope bout-en-bout

C'est la catégorie la plus directement concurrente. Elle est peuplée, mais
presque exclusivement par des scripts personnels non packagés et par des
applications web d'annuaire.

| Projet | Langage | Licence | Entrées | Sortie | Détection de visage |
| --- | --- | --- | --- | --- | --- |
| [WhosWho](https://framagit.org/Yvan-Masson/WhosWho) | Python 3 + GTK3 | GPL-3.0 | Dossier photos + CSV (optionnel) | PDF A4/A3, 150 et 300 DPI | Oui (OpenCV via Willow) |
| [skramm/trombino](https://github.com/skramm/trombino) | Bash | WTFPL | CSV groupe/nom/prénom + photos ordonnées | PDF (LaTeX `tabularx`) et/ou HTML | Non |
| [trombi](https://www.nongnu.org/trombi/site/en/index.html) | non précisé | non vérifiée | Liste de photos | Fichier LaTeX → DVI/PDF | Non |
| [Dagrut/trombi-maker](https://github.com/Dagrut/trombi-maker) | Node.js | non spécifiée | CSV + dossier photos | `trombinoscope.odt` + `.pdf` via LibreOffice | Non |
| [stevenliatti/trombinoscope](https://github.com/stevenliatti/trombinoscope) | Scala + LaTeX | GPL-3.0 | CSV (nom, pupitre) + photos numérotées | PDF par pupitre | Non |
| [fabrice1618/trombinoscope](https://github.com/fabrice1618/trombinoscope) | PHP + MySQL | non spécifiée | Formulaire web | Page HTML | Non |
| [PnEcrins/Trombi](https://github.com/PnEcrins/Trombi) | Python (Flask) + Vue.js | GPL-3.0 | Annuaire LDAP | Application web | Non |

**WhosWho est le concurrent direct le plus sérieux.** C'est un logiciel Python
(GTK3, ImageMagick, OpenCV via Willow, Pillow, chardet) distribué en Flatpak sur
Flathub, créé en mai 2020, avec 289 commits et 22 releases, dont une version 2.0
en mai 2024. Il fait du recadrage automatique centré sur le visage, accepte un
CSV de noms, propose sept mises en page en A4 et A3, exporte en PDF à 150 ou
300 DPI, gère une image par défaut pour les photos manquantes et permet un tri
par nom ou par prénom. Sa présentation est détaillée sur
[LinuxFr](https://linuxfr.org/news/whoswho-le-trombinoscope-facile). Son README
ne mentionne **aucune correction colorimétrique**, et c'est une **application
graphique de bureau**, pas une bibliothèque ni une CLI installable par `pip`.

Le [topic GitHub `trombinoscope`](https://github.com/topics/trombinoscope) ne
recense que huit dépôts publics, majoritairement en PHP (applications web
d'annuaire d'entreprise), ce qui confirme que la niche « bibliothèque Python
scriptable » n'est pas occupée.

À signaler également : un
[gist de génération de planche photo depuis un CSV Blackboard](https://gist.github.com/Stwerp/e30f78a5c250c404ca0e381f82479efb),
en Python 2, qui télécharge les photos d'identité et compile un PDF via
`pdflatex`, sans détection de visage.

**Disponibilité du nom sur PyPI :** l'API JSON de PyPI renvoie 404 pour
`trombinoscope` et pour `yearbook`. Aucun paquet PyPI existant ne porte ces
noms.

### A.2 Recadrage automatique de portraits par détection de visage

| Projet | Licence | Version / date | Ce qu'il fait |
| --- | --- | --- | --- |
| [autocrop](https://github.com/leblancfg/autocrop) | MIT (v2) | 672 étoiles, CI sur Python 3.10–3.14 | Recadre en lot autour du plus grand visage détecté |
| [face-crop-plus](https://pypi.org/project/face-crop-plus/) | MIT | 1.1.0, juin 2023 | Détection + alignement par points de repère, super-résolution, parsing d'attributs, masques |
| [smartcrop](https://pypi.org/project/smartcrop/) | MIT | 0.5.0, mars 2026 | Recadrage par saillance, port de `smartcrop.js`, pas spécifique aux visages |
| [HivisionIDPhotos](https://github.com/Zeyi-Lin/HivisionIDPhotos) | Apache-2.0 | 21,4k étoiles | Photo d'identité : détection, matting du fond, tailles normalisées, planches d'impression |

**`autocrop` est la brique la plus proche de l'étape 2+3 du pipeline.** Sa
version 2 utilise le détecteur neuronal **YuNet** d'OpenCV (le même que celui
retenu ici), expose `--facePercent` — c'est-à-dire exactement la « proportion du
visage dans le cadre » —, ainsi que `-w/--width`, `-H/--height`, `--no-resize`,
un dossier `--reject` pour les images sans visage, une API Python `Cropper` et
un mode `stdin`/`stdout`. Il ne fait ni PDF, ni correction colorimétrique, ni
appariement avec une liste de personnes.

Une nuance de licence à noter : la
[page PyPI d'autocrop](https://pypi.org/project/autocrop/) décrit encore la
version 1.3.0 (janvier 2022, détecteur en cascade de Haar) sous licence
BSD 2-Clause, alors que le dépôt GitHub de la v2 annonce MIT. Il faut vérifier
la licence de la version effectivement installée avant toute redistribution.

`HivisionIDPhotos` produit des planches d'impression (6 pouces, 5 pouces, A4,
3R, 4R) en PNG/JPEG à 300 DPI, mais pas de PDF natif et sans notion de liste
nominative.

Les noms `facecrop` et `python-imagecrop` parfois cités **ne correspondent à
aucun projet établi et maintenu** que la recherche ait pu identifier.

### A.3 Briques de détection de visage utilisables

| Brique | Licence | Remarques |
| --- | --- | --- |
| [YuNet / opencv_zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) | MIT | Auteurs Wu, Peng et Yu. Variantes `2023mar` (entrée fixe, OpenCV 4.x), `2026may` (dimensions symboliques, OpenCV 5.x), `2023mar_int8bq` (quantifié) |
| OpenCV DNN + res10 SSD Caffe | BSD / Apache-2.0 | Approche historique, supplantée par YuNet |
| dlib | Boost Software License | Robuste, compilation C++ lourde |
| [face_recognition](https://github.com/ageitgey/face_recognition) | MIT | Enrobage de dlib, orienté reconnaissance |
| MediaPipe | Apache-2.0 | Rapide, mais dépendance lourde |
| InsightFace | Code MIT, **poids pré-entraînés non commerciaux** | Piège de licence pour un paquet redistribué |
| [RetinaFace (serengil)](https://github.com/serengil/retinaface) | MIT | Précision de pointe, le plus lent |
| [deepface](https://github.com/serengil/deepface) | MIT | Méta-bibliothèque multi-backends ; les licences des modèles sous-jacents sont héritées |

Pour un paquet PyPI destiné à rester léger et redistribuable, YuNet en ONNX
(227 Ko, inférence CPU, licence MIT) est le choix par défaut rationnel : il évite
d'imposer PyTorch et évite les restrictions non commerciales d'InsightFace.

### A.4 Balance des blancs et correction colorimétrique

| Brique | Licence | Version / date | Algorithmes |
| --- | --- | --- | --- |
| [colorcorrect](https://github.com/shunsukeaihara/colorcorrect) | MIT | 0.9.1, mai 2020 | Gray world, max white, stretch, retinex, retinex adjust, SDWGW, SDLWGW, LWGW, ACE |
| [OpenCV `xphoto`](https://docs.opencv.org/3.4/de/daa/group__xphoto.html) | Apache-2.0 | suit OpenCV | `SimpleWB`, `GrayworldWB`, `LearningBasedWB` |
| [scikit-image `exposure`](https://scikit-image.org/docs/stable/api/skimage.exposure.html) | BSD-3-Clause | actif | CLAHE, `match_histograms`, rééchelonnement d'intensité |

`colorcorrect` n'a plus de release depuis mai 2020 et est considéré comme
dormant. Le paquet `imagecorrect` parfois cité **n'existe pas sur PyPI**.

Point important pour la partie B : **toutes ces briques opèrent image par
image.** `match_histograms` de scikit-image permet techniquement un alignement
sur une référence, mais il faut choisir soi-même l'image de référence et gérer
la boucle ; c'est une primitive, pas une politique d'homogénéisation de lot.
Voir la [démonstration de PyImageSearch](https://pyimagesearch.com/2021/02/08/histogram-matching-with-opencv-scikit-image-and-python/)
pour le mode d'emploi de base.

### A.5 Planches contact et générateurs de grilles

| Outil | Licence | Sortie | Limites |
| --- | --- | --- | --- |
| [ImageMagick `montage`](https://imagemagick.org/script/montage.php) | ImageMagick License (type Apache-2.0) | Image | `-tile`, `-geometry`, `-label '%f'`, `-auto-orient`. Pas de PDF paginé, pas de dernière ligne centrée, pas de texte pivoté en marge, pas d'appariement CSV |
| [contactsheet](https://pypi.org/project/contactsheet/) | MIT | Image unique | 0.1.0, juillet 2018, non maintenu ; taille de sortie calée sur la première image |
| [Phatch](https://pypi.org/project/Phatch/) | GPL | Images | Dernière release PyPI `0.1.bzr496`, wxPython, projet moribond |
| gThumb, XnView MP / XnConvert | GPL / propriétaire | Image, HTML | Fonctions de planche contact en interface graphique uniquement |
| [vcsi](https://github.com/amietn/vcsi) | MIT | Image | Planches contact **vidéo**, hors sujet |

Le [tutoriel de Pat David](https://patdavid.net/2013/04/using-imagemagick-to-create-contact/)
donne la recette canonique de planche contact avec `montage`, y compris
l'étiquetage par nom de fichier. C'est l'état de l'art « recette shell » de la
catégorie.

### A.6 Génération de PDF en grille

| Brique | Licence | Remarques |
| --- | --- | --- |
| [ReportLab](https://pypi.org/project/reportlab/) | BSD | 5.0.1, Python 3.9 à 3.14, dépend de Pillow. Contrôle typographique et positionnement absolu, y compris rotations |
| WeasyPrint | BSD-3-Clause | Alternative crédible : CSS Grid + `@page` produisent une grille paginée sans code de mise en page impératif |
| LaTeX | LPPL | Voie retenue par `trombino`, `trombi` et `stevenliatti/trombinoscope`, via `tabularx` maison |
| [pyearcal](https://pypi.org/project/pyearcal) | non vérifiée | Exemple de paquet PyPI qui produit une grille paginée avec ReportLab (calendriers annuels) |

**Aucun paquet CTAN nommé `trombinoscope` n'existe** : la recherche CTAN ne
renvoie aucun résultat. Le paquet `photoalbum` parfois évoqué **n'existe pas non
plus** sur CTAN. Les projets LaTeX cités plus haut écrivent leur propre gabarit
`tabular` / `tabularx`. `tabularray` existe bien mais reste un paquet de tableaux
généraliste, sans rien de spécifique aux portraits.

### A.7 Logiciels métier et services SaaS

Ces solutions résolvent le même problème métier mais ne sont pas des
alternatives pour un usage scriptable : ni API, ni CLI, ni intégration continue,
ni reproductibilité, et généralement des données déjà présentes dans le système.

- **PRONOTE et EDT (Index Éducation)** : gèrent l'import et l'export des photos
  d'élèves et de personnels, et proposent un
  [trombinoscope consultable et imprimable en PDF](https://doc.index-education.com/fr/pronote/pronote/PRONOTE/T/Trombinoscope.htm).
  L'import exige que les photos soient déjà nommées selon une convention
  reconnue par le logiciel — c'est précisément le travail d'appariement que ce
  paquet automatise en amont. Propriétaire.
- **SACoche (Sésamath)** : gestion des
  [photos d'élèves](https://sacoche.sesamath.net/index.php?page=documentation__support_administrateur__photos_eleves).
  Libre, mais orienté suivi de compétences, pas mise en page imprimable.
- **GEPI** : projet historique de gestion scolaire libre, aujourd'hui largement
  supplanté.
- **Lumys Scolaire** : service destiné aux photographes scolaires, dont l'argument
  est justement
  [l'intégration des photos dans Pronote et la génération de trombinoscopes](https://lumys-scolaire.photo/integrer-les-photos-aux-outils-de-gestion-scolaire-et-generer-des-trombinoscopes/).
  SaaS commercial.
- **SaaS yearbook nord-américains** : [TreeRing](https://blog.treering.com/yearbook-design-software/)
  et [Picaboo Yearbooks](https://www.picabooyearbooks.com/yearbook-software)
  sont des éditeurs WYSIWYG couplés à une imprimerie.
- **Annuaires paroissiaux** : [Instant Church Directory](https://www.instantchurchdirectory.com/),
  [Church Pictorial](https://churchpictorial.com/) et
  [Universal Church Directories](https://ucdir.com/printed-directory/) produisent
  des PDF prêts à imprimer. Tous propriétaires ou SaaS. La recherche n'a identifié
  **aucune alternative libre établie** dans cette catégorie.

### A.8 Catégories sans résultat

Par souci d'honnêteté, voici ce que la recherche n'a **pas** trouvé :

- Aucun paquet PyPI nommé `trombinoscope` ni `yearbook`.
- Aucun paquet CTAN `trombinoscope` ni `photoalbum`.
- Aucun projet établi nommé `facecrop`, `python-imagecrop` ou `imagecorrect`.
- Le terme **« face sheet »** ne renvoie, en anglais, qu'à des fiches
  administratives médicales et à des gabarits de coloriage scolaire. Aucun
  logiciel pertinent.
- Aucune bibliothèque, dans aucun langage, offrant une **homogénéisation
  colorimétrique à l'échelle d'un lot** comme fonction de premier niveau.
- Aucun outil de planche contact offrant **pagination automatique + dernière
  ligne centrée + annotations pivotées à 90° en marge**.

## B) Étude d'originalité

### B.1 Ce que le paquet ne réinvente pas

Toutes les briques techniques du pipeline existent, sont matures et sont sous
licence permissive. Le paquet s'appuie dessus et il serait absurde de faire
autrement.

| Étape | Brique existante réutilisée |
| --- | --- |
| Détection de visage | YuNet ONNX via `cv2.FaceDetectorYN` (MIT) |
| Recadrage centré visage | Algorithmiquement identique à ce que fait `autocrop` |
| Balance des blancs | Mêmes familles d'algorithmes que `cv2.xphoto`, `colorcorrect`, `skimage.exposure` |
| Rendu PDF | ReportLab |
| Concept de trombinoscope CSV + photos | `trombino`, `trombi-maker`, WhosWho, `stevenliatti/trombinoscope` |

Aucun des cinq blocs pris isolément ne constitue une contribution.

### B.2 Ce qui est réellement original

Trois points résistent à l'examen, et un seul est vraiment fort.

**1. L'homogénéisation colorimétrique à l'échelle du lot — le point le plus
défendable.** Toutes les bibliothèques de correction couleur recensées opèrent
image par image : `GrayworldWB` normalise une photo par rapport à elle-même,
`match_histograms` exige qu'on lui désigne une référence. Aucune ne répond à la
question réelle du trombinoscope : *étant donné trente photos prises dans des
conditions d'éclairage hétérogènes, produire trente portraits qui se ressemblent
sur une même page*. C'est un problème de cohérence inter-images, pas de qualité
intra-image, et la littérature outillée l'ignore. Ni WhosWho, ni `autocrop`, ni
`montage` ne l'abordent. Le détail de l'approche est dans [color.md](color.md).

**2. La mise en page grille paginée avec dernière ligne centrée et annotations
pivotées.** `montage` aligne la dernière ligne à gauche et ne sait pas écrire
verticalement dans les marges. Les gabarits LaTeX des projets concurrents non
plus. Ce n'est pas une prouesse technique — c'est du positionnement ReportLab —
mais c'est du travail de finition que personne n'a fait et que chaque
utilisateur refait à la main.

**3. Le pipeline en une commande, sans dépendance système.** Les concurrents
exigent tous une chaîne externe : LaTeX pour `trombino`, LibreOffice headless
pour `trombi-maker`, ImageMagick pour WhosWho. Un paquet `pip install`-able qui
ne dépend que de roues Python (`opencv-python`, `reportlab`, `Pillow`, `numpy`)
est déployable en CI et en conteneur sans friction. C'est un différenciateur
d'ingénierie, pas d'algorithmique.

### B.3 Ce qui n'est PAS original, et pourquoi c'est acceptable

**L'appariement positionnel photos ↔ liste n'est pas une innovation.**
`trombino` fait exactement cela — il documente explicitement que les photos
doivent être fournies « dans l'ordre de la liste » — et WhosWho également.
C'est une convention de terrain (« photographier les élèves dans l'ordre de
l'appel »), pas une invention. Sa valeur est ergonomique : elle évite le
renommage manuel qu'exige, par exemple, l'import de photos dans PRONOTE.

**Le cadrage à proportion de visage constante n'est pas original :**
`autocrop --facePercent` fait déjà précisément cela, avec le même détecteur
YuNet. La combinaison avec un ratio d'aspect 4/3 imposé est marginale.

**Il faut dire les choses clairement : WhosWho fait environ 80 % du travail.**
Python, OpenCV, recadrage automatique sur le visage, CSV de noms, sept mises en
page A4/A3, PDF à 300 DPI, image de remplacement pour les photos manquantes, et
un projet vivant sous GPL-3.0 avec 22 releases. Quiconque cherche un
trombinoscope et accepte une interface graphique devrait probablement utiliser
WhosWho. Les écarts réels sont : l'absence d'homogénéisation colorimétrique
inter-photos, l'absence d'API et de CLI scriptables, la dépendance à ImageMagick
et à GTK3, et un ciblage Linux/Flatpak.

Ce paquet est donc, honnêtement, **une réimplémentation orientée bibliothèque
d'un problème déjà résolu en application de bureau, plus une étape de traitement
colorimétrique que personne n'a outillée**. C'est une contribution réelle mais
modeste. La survendre comme « le premier générateur de trombinoscope automatisé »
serait faux.

### B.4 Tableau de décision : quelle alternative préférer

| Situation de l'utilisateur | Outil recommandé |
| --- | --- |
| Il veut un trombinoscope, en interface graphique, sur Linux, sans écrire de code | [WhosWho](https://framagit.org/Yvan-Masson/WhosWho) |
| Il est déjà dans un établissement équipé de PRONOTE et les photos y sont importées | [Trombinoscope PRONOTE](https://doc.index-education.com/fr/pronote/pronote/PRONOTE/T/Trombinoscope.htm) |
| Il veut **seulement** recadrer un dossier de portraits sur le visage | [autocrop](https://github.com/leblancfg/autocrop) |
| Il veut des photos d'identité aux normes, fond détouré et uniforme | [HivisionIDPhotos](https://github.com/Zeyi-Lin/HivisionIDPhotos) |
| Il veut une planche image rapide, sans noms, en une ligne de shell | [`montage` d'ImageMagick](https://imagemagick.org/script/montage.php) |
| Il maîtrise LaTeX et veut un contrôle typographique total | [skramm/trombino](https://github.com/skramm/trombino) ou un gabarit `tabularx` maison |
| Il préfère décrire la mise en page en CSS plutôt qu'en code impératif | WeasyPrint avec CSS Grid et `@page` |
| Il prépare un jeu de données pour de l'apprentissage automatique (alignement, masques) | [face-crop-plus](https://pypi.org/project/face-crop-plus/) |
| Il veut un yearbook imprimé, relié, avec pages personnalisées | [TreeRing](https://blog.treering.com/yearbook-design-software/) ou [Picaboo](https://www.picabooyearbooks.com/yearbook-software) |
| Il veut un annuaire web consultable, pas un imprimé | [PnEcrins/Trombi](https://github.com/PnEcrins/Trombi) |
| **Il a un dossier de JPEG bruts hétérogènes, une liste CSV, et veut un PDF reproductible depuis un script ou une CI** | **`trombinoscope`** |

La dernière ligne est la seule case du tableau qui reste vide sans ce paquet.
C'est une case étroite, mais elle est réelle.

---

**Note de vérification :** toutes les URL de ce document ont été résolues
individuellement. Les mentions « non spécifiée » ou « non vérifiée » signalent
une information réellement absente du dépôt, et non une omission de recherche.
