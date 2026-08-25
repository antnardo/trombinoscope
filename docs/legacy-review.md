# Revue du module de 2020

Ce document rassemble l'analyse du module `trombinoscope` d'origine — celui écrit
en 2020 pour produire les trombinoscopes d'une classe préparatoire, jamais
publié. Il est séparé du code exprès : les modules de `src/` décrivent ce qu'ils
font, pas ce qu'ils ont remplacé.

Il sert deux buts : documenter *pourquoi* la réécriture a pris les décisions
qu'elle a prises, et garder trace de défauts qui pourraient revenir si on n'y
prend pas garde. Chaque point corrigé est verrouillé par un test, indiqué en fin
de section.

Le [CHANGELOG](../CHANGELOG.md) en donne la version courte.

## 1. Défauts qui corrompaient le résultat

### 1.1 La correction colorimétrique était inopérante

```python
def adjust_contrast(image, alpha, beta):
    return cv2.convertScaleAbs(image, alpha, beta)
```

La signature réelle est `convertScaleAbs(src[, dst[, alpha[, beta]]])`. L'appel
positionnel plaçait donc `alpha` en position `dst` et `beta` en position `alpha`.
Le gain calculé n'était jamais appliqué, et le décalage de noir prenait sa place
comme facteur multiplicatif.

```python
>>> img = np.full((2, 2, 3), 100, np.uint8)
>>> cv2.convertScaleAbs(img, 2.0, 0.0)[0, 0]
array([0, 0, 0], dtype=uint8)
>>> cv2.convertScaleAbs(img, alpha=2.0, beta=0.0)[0, 0]
array([200, 200, 200], dtype=uint8)
```

En usage réel, `beta` valait `-minimum_gray * alpha`, soit un nombre négatif de
l'ordre de −30 à −80 ; `convertScaleAbs` en prenait la valeur absolue après
multiplication, et les images ressortaient saturées au blanc. C'est pour cela que
le pilote portait `CORRIGE_COULEUR = False  # ne marche pas pour l'instant`.

Le piège est classique dans l'API Python d'OpenCV : `dst` est un paramètre de
sortie optionnel glissé en deuxième position, contrairement à l'habitude Python.

*Verrou :* `TestAutoLevels::test_apply_actually_applies_the_gain`.
*Suite :* [color.md](color.md) pour ce qui remplace cette fonction.

### 1.2 Une détection ratée décalait tous les élèves suivants

```python
for f in files:
    e = eleves[i]
    R = detect_faces(f, seuil=seuil)
    if len(R) == 0:
        warning("aucun visage trouvé...")
        continue          # <- i n'est pas incrémenté
    ...
    i += 1
```

L'appariement photo ↔ élève était positionnel et les deux curseurs avançaient
dans la même boucle. Quand aucun visage n'était trouvé, le `continue` sautait
l'incrément : la photo suivante était attribuée au même élève, et **tout le reste
de la classe se retrouvait décalé d'un cran**. Le seul indice était un
avertissement noyé dans le flot de sortie.

La réécriture résout l'appariement *avant* toute détection
(`models.positional_match`), si bien qu'un échec ultérieur ne peut plus rien
décaler.

*Verrous :* `TestDetectionFailures::test_no_face_keeps_the_photo_and_the_alignment`,
`TestPositionalMatch::test_alignment_survives_a_shorter_photo_list`.

### 1.3 Les annotations sous les mauvaises photos

Dans `pdf.py`, le placement des photos et celui des annotations pivotées
reconstituaient l'indice de l'élève de deux façons différentes :

```python
# boucle de placement
for e_index, jcol in enumerate(positions_colonne, start=e_index_0 + i*self.cols):
    ...

# boucle des annotations, plus bas
for i in range(page_rows):
    for j in range(self.cols):
        e_index = e_index_0 + i*self.cols + j
        jcol = positions_colonnes[page][i][j]
```

Les deux coïncident tant que chaque ligne est pleine. Dès que la dernière ligne
est centrée, `positions_colonne` est plus courte que `self.cols` et contient des
indices non contigus : les options et les groupes se retrouvaient sous les
mauvaises photos, et `positions_colonnes[page][i][j]` levait une `IndexError`
pour `j` au-delà du nombre d'élèves de la ligne.

La réécriture sépare la pagination (`GridPaginator`, arithmétique pure et
testable sans ReportLab) du dessin (`TrombiRenderer`), qui ne fait plus que
traduire des cellules en coordonnées.

*Verrous :* toute la classe `TestGridPaginator`, en particulier
`test_no_two_cells_share_a_position` et `test_all_shapes_place_everyone`.

### 1.4 `UnboundLocalError` sur les groupes sans options

```python
if len(options) > 0:
    text = ", ".join(options)
    x = lx + (jcol+.5)*colwidth - self.largeurphoto/2 - .5*mm   # <- seul endroit
    self.c.drawString(y, -x, text)
if self.affiche_groupes:
    self.c.drawRightString(y, -x, text)                          # <- x peut ne pas exister
```

`x` n'était calculé que dans la branche des options. Avec
`affiche_options=False` et `affiche_lv=False`, la première itération levait une
`UnboundLocalError` ; aux suivantes, `x` gardait sa valeur de l'élève précédent,
ce qui était pire — pas d'erreur, mais un décalage silencieux. `text` souffrait
du même problème.

## 2. Défauts qui provoquaient des exceptions

### 2.1 Division par zéro sur une image uniforme

```python
alpha = 255 / (maximum_gray - minimum_gray)
```

Un fond blanc surexposé ou un portrait très sombre donnait
`maximum_gray == minimum_gray`. La boucle de recherche des points de coupe
pouvait par ailleurs faire passer l'indice sous zéro, où l'indexation négative de
Python reboucle silencieusement en fin de liste.

*Verrou :* `TestAutoLevels::test_flat_image_is_left_alone`.

### 2.2 Recadrage débordant de la photo source

`images_util.resize` découpait des tranches de tableau et les recollait dans un
fond blanc, en gérant les dépassements avec quatre `min`/`max` imbriqués :

```python
cropped[
    cyi: cyi+min(cyf, h_orig)-max(0, cy),
    cxi: cxi+min(cxf, w_orig)-max(0, cx)
] = image[max(0, cy): min(cyf, h_orig), max(0, cx): min(cxf, w_orig)]
```

Dès que le cadre sortait entièrement de la photo, les deux formes ne
correspondaient plus et l'affectation levait une `ValueError`. Le commentaire
« rapport non conservé en cas de cutoff » était par ailleurs faux : le rapport
était bien conservé, puisque `cropped` avait exactement les dimensions voulues.

La réécriture construit une seule transformation affine et laisse
`cv2.warpAffine` remplir les bords. Bénéfice secondaire : la rotation qui
redresse la ligne des yeux se compose avec la même matrice, au lieu de demander
un second passage.

*Verrou :* `TestOutOfBounds`, quatre positions de visage paramétrées.

## 3. Portabilité

### 3.1 Le module ne s'importait plus sous Python ≥ 3.12

`face_detect.py` et `pdf.py` importaient `pkg_resources`, retiré de la
bibliothèque standard avec `setuptools` en Python 3.12. Un simple
`import trombinoscope` levait `ModuleNotFoundError`. Remplacé par
`importlib.resources`.

### 3.2 `readNetFromCaffe` a disparu d'OpenCV 5

La détection reposait sur `cv2.dnn.readNetFromCaffe` et le SSD ResNet-10. Cette
fonction n'existe plus dans OpenCV 5 : l'approche n'était plus viable
indépendamment de tout choix de conception. C'est ce qui a décidé du passage à
`cv2.FaceDetectorYN`.

Au passage, `cv2.CascadeClassifier` et les fichiers de `cv2.data.haarcascades`
ont eux aussi disparu d'OpenCV 5 — d'où le garde-fou `detection.haar_available()`.

### 3.3 Chemins non-ASCII sous Windows

`cv2.imread` et `cv2.imwrite` passent le chemin à `fopen` dans l'encodage local
et échouent silencieusement — `imread` renvoie `None` — sur un chemin contenant
des accents. Un dossier `Élèves/` suffisait. La lecture et l'écriture passent
maintenant par `imdecode` / `imencode` sur des octets lus en Python.

*Verrou :* `TestReadWrite::test_non_ascii_path_works`.

### 3.4 Ligne de commande construite par concaténation

```python
os.system(cmd + " " + str(file))
```

Un espace ou une apostrophe dans le chemin cassait la commande. Remplacé par
`subprocess.run` avec une liste d'arguments.

## 4. Conception

### 4.1 `logging.py` masquait la bibliothèque standard

Le module s'appelait `trombinoscope/logging.py`. Tout import absolu de `logging`
depuis l'intérieur du paquet récupérait ce module-là. Renommé `log.py`, et bâti
*sur* la stdlib plutôt qu'à côté.

### 4.2 `warning()` bloquait sur `input()`

```python
def warning(*arg, header=True, nostop=False, **kwargs):
    print("[WARNING]", ...)
    if not nostop:
        input('Appuyez sur une touche pour continuer...')
```

Utilisable depuis un script lancé à la main, impossible depuis une bibliothèque
importée, un service ou une intégration continue. La pause existe toujours mais
devient un choix explicite de l'appelant (`set_interactive`), désactivé par
défaut, et l'option `--interactive` la rétablit.

### 4.3 Le modèle était chargé à l'import

```python
NET = cv2.dnn.readNetFromCaffe(PROTOTXT, MODEL)   # au niveau module
```

Un simple `import trombinoscope` payait le chargement du réseau, et échouait si
le fichier manquait — même pour n'utiliser que la mise en page PDF. Le
chargement est désormais paresseux et mis en cache par chemin (`_yunet`).

### 4.4 Sensibilité à la casse devinée en écrivant un fichier

```python
def is_fs_case_sensitive(dir):
    if not hasattr(is_fs_case_sensitive, 'case_sensitive'):
        with tempfile.NamedTemporaryFile(prefix='CASE', dir=dir) as tmp_file:
            ...
```

La fonction créait un fichier temporaire dans le dossier de photos de
l'utilisateur, et mémorisait le résultat dans un attribut de fonction partagé par
*tous* les dossiers — donc faux dès qu'on traitait deux volumes différents dans
le même processus. Remplacé par un filtrage sur le suffixe en minuscules, qui
donne le bon résultat des deux côtés sans rien écrire.

### 4.5 Déduplication en O(n²)

`eliminate_duplicates` comparait chaque fichier à tous les précédents avec
`os.path.samefile`, soit un appel système par paire. Remplacé par un ensemble de
couples `(st_dev, st_ino)`.

### 4.6 Curseur vertical implicite dans `PDFMaker`

`PDFMaker` portait un curseur vertical mis à jour à quatre endroits différents et
partagé par toutes les méthodes de dessin. C'est ce qui rendait la position des
annotations pivotées difficile à prévoir dès qu'une page n'était pas pleine. La
grille est maintenant dessinée directement sur le canevas, chaque appel recevant
ses coordonnées.

### 4.7 Modèle de données spécifique à la prépa française

```python
class Eleve:
    def __init__(self, nom, prenom, cube, LV1, LV2, option, groupe, groupecolle, ...):
```

Huit champs positionnels, dont six ne veulent rien dire hors d'une CPGE
française. Remplacé par `Person(last_name, first_name, tags, groups, badge)`,
deux listes libres d'étiquettes couvrant le cas d'origine sans imposer son
vocabulaire. La table de correspondance est dans [DOC.md](DOC.md), section 10, et
`examples/trombi_mp_sqlite.py` montre la conversion sur la vraie base.

### 4.8 Fonctionnalités présentes mais jamais branchées

- `FaceAligner` et `shape_to_np` : le redressement sur la ligne des yeux était
  écrit, mais le prédicteur 68 points de dlib était commenté et `dlib` n'était
  même pas importé. Le code n'a donc jamais tourné.
- `dldata/shape_predictor_68_face_landmarks.dat` (95 Mo) et
  `dldata/HR18-300W.pth` (37 Mo) : aucun code n'y faisait référence. Sur 142 Mo
  de modèles dans l'arborescence, 132 Mo n'étaient jamais chargés.
- `trombinoscope/pdf_maker.py` : un fichier d'une ligne réexportant un module
  local non publié.
- Les tests de `test/` référençaient `trombinoscope.make` et
  `trombinoscope.face_reco`, qui n'existaient plus.

## 5. Un bug introduit pendant la réécriture

Pour l'honnêteté du compte rendu : le redressement de la ligne des yeux a
d'abord été écrit avec `-eye_angle_deg`. La matrice d'OpenCV vaut
`[[α, β, …], [−β, α, …]]` avec `α = s·cos θ` et `β = s·sin θ` ; l'écart vertical
entre les deux yeux après transformation vaut `−β·Δx + α·Δy`, qui s'annule pour
`tan θ = Δy/Δx`. L'angle à passer est donc l'inclinaison elle-même. Prendre son
opposé **doublait** l'inclinaison au lieu de la supprimer.

C'est le test paramétré `test_aligned_portrait_has_level_eyes` qui l'a attrapé —
une première version du test se contentait de vérifier que deux images
différaient, et ne voyait rien.
