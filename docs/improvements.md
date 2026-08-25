# Améliorations étudiées

Ce document recense les pistes examinées, avec pour chacune l'intérêt réel, le
coût, et la décision. Il sert autant à justifier ce qui **n'a pas** été fait qu'à
préparer les versions suivantes.

## 1. Suppression du fond par segmentation

C'est la piste la plus prometteuse — et probablement celle qui améliorerait le
plus le rendu d'une planche imprimée.

### 1.1 Pourquoi c'est le levier le plus fort

L'harmonisation colorimétrique corrige la teinte et l'exposition, mais elle ne
peut rien contre le fait qu'une photo ait été prise devant un mur blanc et la
suivante devant une bibliothèque. Sur une planche, un fond hétérogène saute aux
yeux bien avant un écart de balance des blancs de quelques centaines de kelvins.

Remplacer chaque fond par un aplat uniforme ferait donc, à lui seul, davantage
pour la cohérence visuelle que tout le module `color.py`. C'est d'ailleurs ce que
fait `HivisionIDPhotos` pour les photos d'identité.

### 1.2 Les briques disponibles, et le piège des licences

| Approche | Licence du code | Licence des **poids** | Taille | Verdict |
| --- | --- | --- | --- | --- |
| `cv2.grabCut` | Apache-2.0 (OpenCV) | aucun poids | 0 | Utilisable immédiatement, qualité moyenne |
| MediaPipe Selfie Segmentation | Apache-2.0 | Apache-2.0 | ~250 Ko | Bon compromis, mais dépendance MediaPipe lourde |
| `rembg` (U²-Net) | MIT | **variable selon le modèle** | 5–176 Mo | À vérifier modèle par modèle |
| MODNet | Apache-2.0 | **CC BY-NC-SA 4.0** | ~25 Mo | **Écarté** : usage non commercial seulement |
| RobustVideoMatting | GPL-3.0 | GPL-3.0 | ~15 Mo | Incompatible avec une distribution MIT |
| BiSeNet *face parsing* | MIT | selon l'entraînement | ~50 Mo | Donne aussi cheveux/peau/vêtements séparément |
| SAM / SAM 2 | Apache-2.0 | Apache-2.0 | 38 Mo – 2,4 Go | Surdimensionné pour un portrait |

Le piège est réel et fréquent : **le code peut être permissif alors que les poids
ne le sont pas**. MODNet en est l'exemple type — son dépôt est Apache-2.0, mais
les poids pré-entraînés sont sous CC BY-NC-SA 4.0, ce qui interdit tout usage
commercial et impose le partage à l'identique. Distribuer ces poids dans une roue
PyPI sous licence MIT serait une faute. InsightFace pose exactement le même
problème. Toute intégration devra vérifier la licence des poids, pas seulement
celle du dépôt.

### 1.3 Ce qui serait raisonnable

Une conception en deux niveaux, cohérente avec l'architecture actuelle :

1. **Un protocole `Segmenter`**, injectable au même titre que `FaceDetector`,
   pour que l'utilisateur puisse brancher n'importe quel modèle sans que le
   paquet ait à le distribuer ;
2. **Une implémentation par défaut sans poids à distribuer** — `cv2.grabCut`
   amorcé par la boîte du visage, agrandie selon `FramingConfig`. C'est
   médiocre sur des cheveux détaillés, mais gratuit en taille de roue et sans
   aucune question de licence ;
3. **Un extra optionnel** `pip install trombinoscope[matting]` tirant MediaPipe
   ou `rembg`, avec la licence de chaque modèle documentée.

Le fond de remplacement devrait être paramétrable (blanc, gris neutre, dégradé
studio) et, idéalement, **estimé sur le lot** — dans l'esprit de ce que fait déjà
`BatchColorHarmonizer` : plutôt qu'un blanc arbitraire, la couleur de fond la plus
fréquente de la séance.

Point de vigilance : un détourage raté est **bien plus laid** qu'un fond
hétérogène. Une oreille rognée ou un halo autour des cheveux se voit
immédiatement. Il faudra un indicateur de confiance et un repli sur « fond
d'origine conservé » quand le masque est douteux, sur le modèle du repli
« aucun visage détecté → photo entière » déjà en place.

## 2. Balance des blancs par apprentissage

`cv2.xphoto.createLearningBasedWB` (méthode de Barron) surpasse Shades of Gray
sur les jeux de référence. Elle vit dans `opencv-contrib-python`, qui pèse
nettement plus lourd que `opencv-python-headless` et duplique le module `cv2`.

**Décision : reporté.** Le gain mesurable sur des portraits — où le sujet occupe
plus de la moitié du cadre et où l'hypothèse de neutralité tient bien — ne
justifie pas la dépendance. À reconsidérer si un extra `[contrib]` apparaît pour
d'autres raisons.

## 3. Détection des photos quasi monochromes

L'analyse de la [section 4.2 de color.md](color.md) montre que les images à
faible saturation reçoivent une correction de teinte peu fiable : leur illuminant
est mal contraint, et la correction leur ajoute une dominante au lieu d'en
retirer une.

Piste concrète : mesurer la saturation médiane du visage et moduler `strength` en
conséquence, plutôt que d'appliquer un réglage global. Une image dont la
chromaticité est à moins de quelques pourcents du neutre devrait recevoir une
correction proche de zéro.

C'est peu coûteux, entièrement testable, et cela supprimerait l'un des rares cas
où le traitement dégrade le résultat. **Bon candidat pour la 0.2.**

## 4. Appariement par le nom de fichier plutôt que par la position

L'appariement positionnel est ergonomique mais fragile : une photo ratée effacée
après coup décale tout. Une alternative, en complément et non en remplacement :

- reconnaître un identifiant dans le nom de fichier (`DUPONT_Marie.jpg`,
  `12345.jpg`) et le rapprocher d'une colonne de la liste ;
- rapprochement approché (distance de Levenshtein) avec seuil et rapport des
  ambiguïtés, plutôt qu'une correspondance exacte qui échouerait sur les accents.

Le rapport `BuildReport` est déjà structuré pour porter ce diagnostic. À prévoir
comme `--match filename` opposé au `--match position` actuel.

## 5. Reconnaissance faciale pour l'appariement

Techniquement séduisant — associer automatiquement chaque photo à la bonne
personne à partir d'une photo de référence — mais cela transformerait l'outil en
système de reconnaissance biométrique. Dans l'Union européenne, le traitement de
données biométriques aux fins d'identifier une personne physique relève de
l'article 9 du RGPD, et le règlement sur l'IA encadre spécifiquement ces usages.

**Décision : écarté.** Le paquet fait de la *détection* de visage (« y a-t-il un
visage, et où ») et jamais de la *reconnaissance* (« qui est-ce »). C'est une
frontière volontaire, et elle mérite de le rester dans un outil destiné à des
établissements scolaires.

## 6. Sortie autre que PDF

Une planche PNG, une page HTML, un export vers un tableur. `ReportLab` produit
déjà du PDF ; une sortie image demanderait un moteur de rendu distinct.

Alternative plus économique : documenter `pdftoppm` ou `pypdfium2` en
post-traitement, sans rien ajouter au paquet. **Décision : hors périmètre.**

## 7. Mise en page

Plusieurs points restent perfectibles dans `pdf/grid.py` :

- **hauteur de ligne variable** selon la longueur des noms : un nom qui passe sur
  deux lignes décale actuellement toute la ligne de la grille ;
- **gouttières d'annotation** : les étiquettes longues débordent sans avertir. Un
  mécanisme de troncature ou de réduction automatique serait utile ;
- **groupes visuels** : séparer la planche par groupe, avec un intertitre, plutôt
  qu'une grille continue ;
- **format A3** et impression recto-verso.

## 8. Performance

Le traitement garde tous les portraits recadrés en mémoire entre les deux passes
— environ 360 Ko par personne à la taille par défaut, soit 72 Mo pour 200
personnes. Acceptable pour l'usage visé, mais un lot de plusieurs milliers de
photos demanderait de passer par un cache disque.

La détection domine le temps de calcul. Elle est déjà accélérée par la réduction
à 1024 pixels de côté (facteur ~15 sur une photo de 12 Mpx) ; la paralléliser sur
plusieurs cœurs serait le gain suivant, `cv2.FaceDetectorYN` n'étant pas
réentrant, il faudrait une instance par processus.

## 9. Ce qui a été corrigé, et qui n'est donc plus une piste

Pour mémoire, ces points étaient des défauts de la première version et sont
traités dans la 0.1 :

- correction colorimétrique inopérante — voir [color.md](color.md), section 1 ;
- décalage silencieux de l'appariement dès qu'une détection échouait ;
- annotations placées sous les mauvaises photos quand la dernière ligne était
  centrée ;
- `UnboundLocalError` quand les groupes étaient affichés sans étiquettes ;
- exception sur les cadrages débordant de la photo source ;
- 142 Mo de modèles dans l'arborescence, dont 132 Mo jamais chargés par le code,
  remplacés par un unique fichier de 227 Ko ;
- blocage sur `input()` au milieu d'une bibliothèque ;
- module `logging.py` masquant celui de la bibliothèque standard.
