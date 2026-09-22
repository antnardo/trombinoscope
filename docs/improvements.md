# Améliorations étudiées

Ce document recense les pistes examinées, avec pour chacune l'intérêt réel, le
coût, et la décision. Il sert autant à justifier ce qui **n'a pas** été fait qu'à
préparer les versions suivantes.

## 1. Suppression du fond par segmentation

> **Implémenté en 0.5.0**, sur la base de cette étude : MediaPipe
> SelfieSegmenter embarqué, garde-fou à cinq indicateurs, repli sur la photo
> d'origine. Mode d'emploi dans [DOC.md](DOC.md), section 7. Ce qui suit reste le
> raisonnement qui a conduit à ce choix, y compris les modèles écartés et les
> raisons de leur écart.

C'était la piste la plus prometteuse — et celle qui améliore le plus le rendu
d'une planche imprimée.

### 1.1 Pourquoi c'est le levier le plus fort

L'harmonisation colorimétrique corrige la teinte et l'exposition, mais elle ne
peut rien contre le fait qu'une photo ait été prise devant un mur blanc et la
suivante devant une bibliothèque. Sur une planche, un fond hétérogène saute aux
yeux bien avant un écart de balance des blancs de quelques centaines de kelvins.

Remplacer chaque fond par un aplat uniforme ferait donc, à lui seul, davantage
pour la cohérence visuelle que tout le module `color.py`. C'est d'ailleurs ce que
fait `HivisionIDPhotos` pour les photos d'identité.

### 1.2 Les briques disponibles, et le piège des licences

> **Correction (septembre 2026).** Une première version de ce tableau donnait les
> poids de MODNet pour CC BY-NC-SA 4.0. **C'est faux.** Le README de MODNet écrit
> « The code, **models**, and demos in this repository […] are released under the
> Apache License 2.0 » — le mot *models* y figure explicitement. La CC BY-NC-SA
> existe bien, mais elle porte sur le **jeu de test PPM-100**, publié dans un
> dépôt séparé, et qui n'entre dans aucune distribution. L'erreur venait
> précisément du réflexe que cette section prétend dénoncer : conclure sans lire
> la source. Toutes les licences ci-dessous ont été relues à la source.

| Modèle | Licence code | Licence **poids** (vérifiée) | Taille | `cv2.dnn` ? | Redistribuable ici ? |
| --- | --- | --- | --- | --- | --- |
| `cv2.grabCut` | Apache-2.0 | aucun poids | 0 | — | oui |
| **MediaPipe SelfieSegmenter** | Apache-2.0 | **Apache-2.0** (model card Google) | **244 Ko** | ✅ `readNetFromTFLite` | **oui** |
| U²-Net `u2netp` | Apache-2.0 | Apache-2.0 (par inclusion) | 4,4 Mo | ✅ ONNX | oui |
| MODNet | Apache-2.0 | **Apache-2.0** (« code, models, and demos ») | 25,9 Mo | ✅ fp32 seul | oui, mais lourd |
| PP-HumanSeg (OpenCV Zoo) | Apache-2.0 | Apache-2.0 | 1,6 / 6,2 Mo | ✅ | oui, mais **qualité rédhibitoire** |
| BiRefNet | MIT | MIT | ≥ 109 Mo | non testé | oui, mais hors budget |
| BEN2 | MIT | MIT | 223 Mo | non testé | oui, mais hors budget |
| SAM / SAM 2 / MobileSAM | Apache-2.0 | Apache-2.0 | ≥ 39 Mo | ✗ | hors sujet : exige une amorce |
| `silueta` | — | ⚠️ **aucune licence** | 42 Mo | — | **non** — tous droits réservés |
| BRIA RMBG-1.4 / 2.0 | — | 🔴 non commerciale / CC BY-NC 4.0 | 44 / 234 Mo | — | **non** |
| RobustVideoMatting | 🔴 GPL-3.0 | GPL-3.0 | 15 Mo | — | **non** (copyleft) |

Le piège reste réel — **le code peut être permissif alors que les poids ne le sont
pas** — mais l'exemple canonique n'est pas celui qu'on croit. Les vrais cas sont
BRIA RMBG (« non-commercial use », accord commercial obligatoire au-delà) et
InsightFace. Et le pire cas n'est pas une licence restrictive, c'est **l'absence
de licence** : `silueta`, largement utilisé via `rembg`, a été partagé par un
lien Google Drive dans un ticket GitHub avec pour seule formule *« feel free to
test it »*. Ce n'est pas une licence ; juridiquement, c'est tous droits réservés.

Trois familles, dont une seule est vraiment fermée :

1. **Permissive** (Apache-2.0, MIT, BSD) — redistribuable dans une roue MIT.
2. **Copyleft / partage à l'identique** (GPL, CC BY-SA) — exigerait de relicencier
   le paquet. Pour mémoire, CC BY-SA 4.0 est compatible **à sens unique** vers
   GPLv3 depuis la déclaration de Creative Commons d'octobre 2015.
3. **Non commerciale** — **aucun changement de licence du paquet n'y change quoi
   que ce soit.** La clause contraint l'utilisateur final, pas le distributeur.
   Passer le paquet en GPL ne ferait qu'ajouter une contradiction, la GPL
   interdisant toute restriction supplémentaire : le paquet deviendrait
   indistribuable, pas plus permissif. C'est la confusion la plus fréquente sur
   le sujet.

Deux nuances de méthode, parce qu'elles reviennent souvent :

- **La licence d'un jeu de données n'est pas celle des poids.** PPM-100, DIS5K ou
  SA-1B contaminent la *provenance*, pas le fichier de poids, dont la licence est
  fixée par celui qui le publie. Que la clause « remonte » jusqu'aux poids
  entraînés est un point de droit **non tranché** — à signaler comme un risque,
  pas comme une interdiction.
- **Aucune licence libre n'est un blanc-seing sur le contenu.** Les portraits
  restent des données personnelles ; le RGPD ne dépend pas de la licence du modèle.

### 1.3 Ce que montre la mesure

Les quatre candidats exécutables ont été testés sous `cv2.dnn` sur les portraits
de `tests/data/portraits/`, en prenant pour juge la **fraction de la boîte du
visage YuNet qui tombe dans le masque** :

| Modèle | Couverture visage | Temps | Taille | Rendu |
| --- | --- | --- | --- | --- |
| MediaPipe | 94,3 – 100 % | 8–18 ms | 244 Ko | net, léger halo sur cheveux fins |
| MODNet | 94,1 – 100 % | 95–136 ms | 25,9 Mo | meilleur cheveu, alpha vraiment doux |
| `u2netp` | 94,2 – 99,9 % | 112 ms | 4,4 Mo | très proche de MODNet |
| PP-HumanSeg | **33,9 – 92,1 %** | 10 ms | 6,2 Mo | **inutilisable** |

Le résultat contre-intuitif est **PP-HumanSeg**, seul modèle de segmentation de
personne du dépôt OpenCV Zoo, donc le candidat le plus naturel ici : sa licence
est irréprochable et son rendu inexploitable. Il travaille en 192×192 et sort un
`argmax` binaire — il détruit les cheveux, mord dans le front, et **efface
jusqu'aux deux tiers du visage** sur certaines photos. Il est écarté sur la
qualité seule.

L'autre surprise est que **MediaPipe fait jeu égal avec des modèles 18 à 100 fois
plus lourds**, parce qu'il est entraîné exactement sur ce cas : une personne,
cadrage buste, face caméra. C'est précisément l'entrée d'un trombinoscope.

Sur la robustesse, un portrait de référence a été dégradé de quatre manières, en
comparant le masque obtenu à celui de l'image saine (IoU) :

| Cas | MODNet | `u2netp` |
| --- | --- | --- |
| normal | 1,00 | 1,00 |
| contre-jour | 1,00 | 0,99 |
| **fond de la couleur du vêtement** | **1,00** | **0,91** |
| sous-exposition | 1,00 | 0,99 |

Contre-intuitif là encore : le contre-jour et la sous-exposition ne gênent
presque pas. Le vrai piège est le **fond de la couleur du vêtement** — un élève en
pull bordeaux devant un mur bordeaux — où `u2netp` mange 6 % du buste.

### 1.4 Ce qui a été retenu

1. **Un protocole `Segmenter`**, injectable au même titre que `FaceDetector`.
2. **MediaPipe SelfieSegmenter embarqué** : 244 Ko, Apache-2.0,
   `cv2.dnn.readNetFromTFLite` — **aucune dépendance nouvelle**, ni
   `onnxruntime`, ni `mediapipe`, ni TensorFlow. La roue passerait de 257 Ko à
   environ 500 Ko, soit un facteur 2 ; `u2netp` la multiplierait par 18 et MODNet
   par 100.
3. **MODNet en téléchargement optionnel** pour qui veut le meilleur alpha. Ici le
   téléchargement à la demande n'est pas un contournement juridique — MODNet est
   Apache-2.0 — mais la réponse au seul problème de **taille**.

Le fond de remplacement est paramétrable. Reste une piste ouverte : l'**estimer
sur le lot**, dans l'esprit de `BatchColorHarmonizer`, plutôt que d'imposer un
blanc arbitraire.

Un point n'était pas prévu par l'étude et s'est imposé à l'usage : **le halo se
corrige en raidissant la rampe alpha, pas en érodant le masque**. Vérifié à l'œil
sur un portrait à fond noir, éroder jusqu'à 3 px entame les cheveux sans effacer
le liseré, alors qu'un gain de 4 le supprime en gardant la mèche. D'où
`--alpha-gain`, absent des recommandations initiales.

### 1.5 Le garde-fou, qui n'était pas optionnel

Un détourage raté est **bien plus laid** qu'un fond hétérogène, et la raison tient
à l'objet : un trombinoscope est nominatif. Un fond hétérogène passe pour une
photo authentique ; une oreille rognée passe pour un défaut du document — et la
personne concernée est identifiable, c'est elle qui le remarquera. D'où la règle :
**en cas de doute, ne pas détourer.**

Le modèle ne fournit aucun indice de confiance ; il faut le construire. Quatre
indicateurs suffisent, en quelques lignes de numpy :

1. **Couverture du visage** — le meilleur signal, et YuNet est déjà là. En dessous
   de **95 %**, refuser. Ce test seul disqualifie PP-HumanSeg et valide les trois
   autres.
2. **Surface d'avant-plan** — hors de `[10 %, 85 %]`, le masque est aberrant.
3. **Composantes connexes** — au-delà d'une seule composante de plus de 0,5 % de
   l'image, il reste des fragments de fond.
4. **Pixels ambigus** (alpha entre 0,05 et 0,95) — un masque sain reste à 2–5 % ;
   PP-HumanSeg monte à 12–24 %.

Cinquième garde-fou utile : si le masque **touche le bord supérieur**, le sujet
est coupé et le remplacement produira une tête tranchée.

Piège d'implémentation : la détection de visage peut échouer, et l'indicateur
nº 1 devient alors indisponible. Le code retombe sur les indicateurs 2 à 4 plutôt
que de refuser ou d'accepter aveuglément.

Le seuil de couverture a dû être **abaissé de 0,95 à 0,90** au moment de
l'implémentation, contrairement à ce que l'étude concluait. La raison est
géométrique et aurait dû être vue plus tôt : la boîte du visage est un rectangle,
la tête non, donc ses coins tombent nécessairement à côté du visage et un masque
parfait ne couvre jamais toute la boîte. Mesuré, un bon détourage donne 93 à
100 % ; à 0,95, deux portraits corrects sur huit étaient rejetés.

Enfin, deux traitements qui améliorent beaucoup le rendu pour un coût nul :
**éroder le masque d'un ou deux pixels** avant compositing, ce qui supprime le
liseré de fond d'origine, et composer sur un fond **clair** plutôt que sombre, où
le halo résiduel devient invisible.

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
