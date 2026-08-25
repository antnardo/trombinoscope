# Couleurs et balance des blancs

Ce document explique ce que fait le module `color.py`, pourquoi, et ce que ça vaut
en mesures.

Il commence par le diagnostic de la version de 2020, parce que c'est lui qui
justifie les choix de la version actuelle. La revue complète de ce module
d'origine est dans [legacy-review.md](legacy-review.md).

## 1. Le diagnostic : trois bugs superposés

La première version tentait déjà une correction. Le code tenait en deux fonctions.

```python
def automatic_brightness_and_contrast(image, clip_hist_percent=0.01):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    # ... accumulation, recherche des points de coupe ...
    alpha = 255 / (maximum_gray - minimum_gray)
    beta = -minimum_gray * alpha
    return alpha, beta

def adjust_contrast(image, alpha, beta):
    return cv2.convertScaleAbs(image, alpha, beta)
```

### 1.1 Le bug fatal : des arguments positionnels

La signature réelle d'OpenCV est `convertScaleAbs(src[, dst[, alpha[, beta]]])`.
L'appel `convertScaleAbs(image, alpha, beta)` place donc **`alpha` en position
`dst`** et **`beta` en position `alpha`**. Le gain calculé n'était jamais
appliqué, et le décalage de noir prenait sa place comme facteur multiplicatif.

Vérification directe :

```python
>>> img = np.full((2, 2, 3), 100, np.uint8)
>>> cv2.convertScaleAbs(img, 2.0, 0.0)[0, 0]        # appel positionnel
array([0, 0, 0], dtype=uint8)
>>> cv2.convertScaleAbs(img, alpha=2.0, beta=0.0)[0, 0]   # appel nommé
array([200, 200, 200], dtype=uint8)
```

En usage réel, `beta` valait `-minimum_gray * alpha`, donc un nombre négatif de
l'ordre de −30 à −80. `convertScaleAbs` prenait sa valeur absolue après
multiplication : toutes les images ressortaient saturées au blanc. La fonction
n'était pas approximative, elle était **inopérante**.

C'est un piège classique de l'API Python d'OpenCV : `dst` est un paramètre de
sortie optionnel glissé en deuxième position, contrairement à l'habitude Python.
Le correctif tient en un mot-clé, et un test de non-régression le verrouille
(`TestAutoLevels::test_apply_actually_applies_the_gain`).

### 1.2 La division par zéro

Sur une image uniforme — un fond blanc surexposé, un portrait à contre-jour très
sombre — `maximum_gray == minimum_gray`, et `255 / 0` levait une exception. La
boucle `while accumulator[maximum_gray] >= ...` pouvait par ailleurs faire passer
l'indice sous zéro, où l'indexation négative de Python reboucle silencieusement
en fin de liste.

### 1.3 L'erreur de conception : mesurer le fond plutôt que le sujet

Même corrigée, cette fonction ne faisait pas ce qu'on attendait d'elle. Elle
étalait l'histogramme de **toute l'image**. Sur un portrait, la majorité des
pixels appartiennent au fond. Un mur blanc, un tableau noir, un rideau : c'est le
décor qui décidait de l'exposition du visage.

Et surtout, un étalement d'histogramme corrige le **contraste**, pas la **balance
des blancs**. Une photo prise sous une lampe à incandescence a une dominante
orange que l'étalement d'un canal de luminance ne touche pas.

## 2. Le vrai problème : la cohérence, pas la qualité

Un trombinoscope se regarde **en planche**. Trente portraits côte à côte sur une
page A4. Dans ces conditions, ce que l'œil voit n'est pas qu'une photo soit
légèrement chaude — c'est que celle-ci soit plus chaude que sa voisine.

C'est une différence de nature. Les bibliothèques de correction couleur
existantes — `cv2.xphoto`, `colorcorrect`, `skimage.exposure` — travaillent
**image par image** : elles optimisent chaque photo indépendamment. Aucune ne
répond à la question « rendre ces trente photos semblables entre elles », qui est
un problème de cohérence inter-images.

C'est le seul endroit où ce paquet apporte quelque chose que les briques
existantes ne fournissent pas. Voir [prior-art.md](prior-art.md), section B.2.

## 3. Ce que fait l'implémentation actuelle

Quatre étapes, dans `trombinoscope/color.py`.

### 3.1 Estimation de l'illuminant en lumière linéaire

L'estimation utilise la famille **Shades of Gray** (Finlayson & Trezzi, 2004),
une norme de Minkowski d'ordre `p` :

```text
e_c = ( moyenne( I_c^p ) )^(1/p)     pour chaque canal c
```

`p = 1` redonne exactement Gray World, `p → ∞` redonne White Patch (max-RGB),
`p = 6` est la valeur empirique de l'article et le défaut retenu ici.

Le point important est **où** ce calcul est fait. Les valeurs d'un JPEG sont
encodées en sRGB, c'est-à-dire avec une fonction de transfert non linéaire
d'exposant ≈ 2,2. Un gain multiplicatif appliqué à des valeurs encodées ne
correspond à aucune opération physique : la lumière, elle, s'additionne
linéairement. La plupart des implémentations naïves — y compris la majorité des
recettes qu'on trouve en ligne — ignorent cette étape et sous-corrigent
systématiquement les dominantes fortes.

Ici, chaque image est décodée en lumière linéaire (`srgb_to_linear`), corrigée,
puis ré-encodée (`linear_to_srgb`).

Deux précautions de plus :

- les **pixels écrêtés** (canal ≥ 0,98) sont écartés de l'estimation : un pixel
  saturé ne porte plus l'information de l'illuminant, il tire seulement le
  résultat vers le blanc ;
- l'estimation est restreinte à un **masque elliptique inscrit dans la boîte du
  visage**, resserré à 75 % pour exclure cheveux et bord de fond.

### 3.2 Correction diagonale de von Kries, bornée

```text
gain_c = illuminant_cible_c / illuminant_estimé_c
```

Les gains sont ensuite renormalisés autour de leur **moyenne géométrique**, de
sorte que la correction déplace la teinte sans toucher à la luminosité globale :
exposition et couleur restent deux réglages séparés. Puis ils sont bornés à
`[1/max_gain, max_gain]` (2,0 par défaut), ce qui empêche qu'une photo au fond
fortement coloré ne reçoive un gain aberrant.

Le paramètre `strength` interpole géométriquement vers l'identité
(`gain ** strength`), ce qui préserve la neutralité de la moyenne géométrique —
une interpolation linéaire ne le ferait pas.

### 3.3 Normalisation d'exposition par gamma

La luminance médiane est mesurée sur le canal `L*` de CIE L\*a\*b\*, sur le masque
du visage, puis ramenée à la cible par une **correction gamma** :

```text
gamma = log(cible / 255) / log(actuel / 255)
```

Le gamma est préféré à un gain linéaire parce qu'il est monotone et ne peut pas
écrêter : remonter une photo sous-exposée de deux diaphragmes par une
multiplication brûlerait tous les hauts tons, alors que le gamma les comprime.

### 3.4 Harmonisation à l'échelle du lot

C'est l'étape qui manquait entièrement. Le traitement se fait en **deux passes** :

1. **mesure** de l'illuminant et de la luminance de chaque portrait ;
2. **correction** de chaque portrait vers l'illuminant **médian** et la luminance
   **médiane** du lot.

La médiane, et non la moyenne : une seule photo prise à contre-jour suffirait à
décaler une moyenne, alors qu'elle ne déplace pas une médiane. Un test le
verrouille (`test_reference_is_the_median_not_the_mean`).

Viser la médiane du lot plutôt que le gris neutre a deux vertus : le résultat
reste fidèle à l'ambiance réelle de la séance, et les écarts entre portraits —
le seul défaut réellement visible sur une planche imprimée — disparaissent.

## 4. Mesures

Le script `scripts/color_bench.py` produit ces chiffres. Deux métriques :

- **dispersion chromatique** : écart-type, sur le lot, des chromaticités
  `c / (R+G+B)` de l'illuminant estimé — plus c'est bas, plus les photos se
  ressemblent en teinte ;
- **dispersion de luminance** : écart-type de la luminance médiane du visage.

### 4.1 Cas contrôlé : une séance dont la balance des blancs dérive

Un portrait unique, six dominantes connues appliquées, puis harmonisation. La
vérité terrain est connue : les six images devraient redevenir identiques.

| | dispersion chromatique | écart max entre deux portraits |
| --- | --- | --- |
| dominantes appliquées | 0,0822 | 24,3 niveaux |
| après harmonisation | 0,0180 | 10,3 niveaux |

C'est le cas d'usage visé, et le résultat est net : **−78 % de dispersion
chromatique**, et à l'œil les six portraits redeviennent difficiles à distinguer.

### 4.2 Cas réel : un lot volontairement hétéroclite

Les huit portraits d'exemple ne sont *pas* une séance : ce sont des
photographies prises à des décennies d'écart, en studio et en conférence, dont
l'une est quasi monochrome. C'est le pire cas possible, choisi exprès.

| méthode | dispersion chromatique | dispersion de luminance |
| --- | --- | --- |
| brut (aucune correction) | 0,0475 | 17,34 |
| grayworld | 0,0389 (−18 %) | 1,00 (−94 %) |
| **shades-of-gray** (défaut) | **0,0196 (−59 %)** | **0,48 (−97 %)** |
| white-patch | 0,0241 (−49 %) | 0,48 (−97 %) |
| shades-of-gray, `strength=0.75` | 0,0120 (−75 %) | 0,66 (−96 %) |
| shades-of-gray, **sans** harmonisation de lot | 0,0089 (−81 %) | 17,69 (+2 %) |

Trois enseignements, y compris ceux qui dérangent.

**Shades of Gray domine nettement Gray World**, ce qui confirme le choix par
défaut : `p = 6` résiste bien mieux aux fonds colorés que `p = 1`.

**La correction photo par photo obtient la meilleure dispersion chromatique
(0,0089) mais ne fait rien pour la luminance (17,69, soit le niveau brut).**
C'est logique : ramener chaque image vers le gris neutre est la stratégie de
convergence maximale en teinte, mais elle ignore les autres photos, donc
l'exposition reste aussi disparate qu'avant. Sur une planche imprimée, c'est
l'écart de luminosité qui saute aux yeux le premier. L'harmonisation de lot
échange un peu de convergence chromatique contre un facteur 37 sur la luminance,
et préserve au passage l'ambiance de la séance.

**Une correction à pleine puissance n'est pas forcément la meilleure.** Sur ce
lot, `strength=0.75` mesure mieux que `strength=1.0`, parce que l'estimateur
lui-même se trompe sur les images presque monochromes et qu'atténuer sa décision
atténue aussi son erreur. Le défaut reste 1,0 — huit photos ne suffisent pas à
justifier un réglage — mais **si le résultat vous paraît sur-corrigé, essayez
`--strength 0.7`**.

Enfin, il faut le dire franchement : sur ce lot-là, les planches corrigées ne
sont pas *visuellement* meilleures que les brutes. Les métriques mesurent la
convergence, pas la beauté, et harmoniser des photos qui n'ont jamais appartenu à
la même séance n'a pas grand sens. Générez les planches et jugez vous-même :

```bash
uv run python scripts/fetch_samples.py
uv run python scripts/color_bench.py --output artifacts
```

## 5. Ce que le paquet ne fait pas, et pourquoi

**Il n'ancre jamais la correction sur une teinte de peau de référence.** L'idée
revient souvent : puisqu'on sait où est le visage, pourquoi ne pas ramener toutes
les carnations vers une valeur cible ? Parce que cela reviendrait à *modifier la
couleur de peau des personnes photographiées*. La couleur de peau varie d'un
individu à l'autre ; l'illuminant, lui, est une propriété de l'éclairage, partagée
par toutes les photos d'une même séance. C'est donc l'illuminant qu'on estime, et
jamais une carnation cible. Aucune option ne permet de faire autrement.

**L'étalement d'histogramme est désactivé par défaut.** `AutoLevels` reste
disponible (`--auto-levels 0.5`) et son bug historique est corrigé, mais la mesure
montre qu'il *dégrade* la cohérence du lot : 0,0256 de dispersion chromatique avec,
contre 0,0196 sans. Il cale la plage dynamique sur le seul visage, brûle donc les
fonds et amplifie le bruit des photos sombres. La normalisation gamma fait le même
travail d'exposition sans écrêter.

**Aucune méthode par apprentissage.** `cv2.xphoto.createLearningBasedWB` est
meilleure que Shades of Gray sur les jeux de référence, mais elle vit dans
`opencv-contrib-python`, un paquet nettement plus lourd. Le gain ne justifie pas
la dépendance pour cet usage. Voir [improvements.md](improvements.md).

## 6. Références

- G. Finlayson, E. Trezzi, *Shades of Gray and Colour Constancy*, Color Imaging
  Conference, 2004 — l'article fondateur de la norme de Minkowski appliquée à la
  constance chromatique.
- E. Land, *The Retinex Theory of Color Vision*, Scientific American, 1977 —
  l'origine de l'approche « white patch ».
- J. von Kries, 1902 — la correction diagonale par gains indépendants par canal.
- [Documentation OpenCV de `convertScaleAbs`](https://docs.opencv.org/4.x/d2/de8/group__core__array.html#ga3460e9c9f37b563ab9dd550c4d8c4e7d)
  — la signature à l'origine du bug de la section 1.1.
- [Spécification sRGB (IEC 61966-2-1)](https://www.color.org/srgb.pdf) — la
  fonction de transfert utilisée par `srgb_to_linear`.
