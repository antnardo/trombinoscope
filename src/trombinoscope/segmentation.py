"""Détourage du fond par segmentation.

Sur une planche imprimée, un fond hétérogène saute aux yeux bien avant un écart
de balance des blancs : remplacer chaque fond par un aplat fait donc davantage
pour la cohérence visuelle que tout ``color.py``. C'est la raison d'être de ce
module.

**Pourquoi MediaPipe SelfieSegmenter.** Le modèle pèse 244 Ko — la roue passe de
257 Ko à 500 Ko, un facteur 2 — et tourne sous ``cv2.dnn.readNetFromTFLite``,
donc *sans aucune dépendance nouvelle* : ni ``onnxruntime``, ni ``mediapipe``, ni
TensorFlow. Ses poids sont sous Apache-2.0 d'après la model card de Google, ce
qui autorise la redistribution ici (voir ``CREDITS.md``). Les alternatives
coûtaient toutes beaucoup plus cher pour un gain marginal sur ce type d'image :
``u2netp`` multiplie la roue par 18, MODNet par 100. Mesuré sur des portraits,
MediaPipe fait jeu égal avec eux, parce qu'il est entraîné exactement sur ce cas
— une personne, cadrage buste, face caméra.

Le candidat le plus naturel, PP-HumanSeg, est *écarté* : il est dans OpenCV Zoo à
côté de YuNet et sa licence est irréprochable, mais il travaille en 192×192 et
efface jusqu'aux deux tiers du visage. Voir ``docs/improvements.md``, section 1.

**Pourquoi les garde-fous.** Un détourage raté est bien plus laid qu'un fond
hétérogène, et la raison tient à l'objet : un trombinoscope est nominatif. Un
fond bizarre passe pour une photo authentique ; une oreille rognée passe pour un
défaut du document, et la personne concernée est celle qui le remarquera. D'où la
règle appliquée ici — **en cas de doute, ne pas détourer**, et rendre la photo
intacte. Le modèle ne fournissant aucun indice de confiance,
:func:`assess_mask` en construit un à partir de cinq indicateurs géométriques.

Le compositing se fait **en lumière linéaire**, comme les estimateurs de
``color.py`` : sur un bord à alpha intermédiaire, mélanger les valeurs sRGB
directement assombrit le liseré, ce qui accentue précisément le défaut connu de
ce modèle sur les cheveux fins.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol, runtime_checkable

import cv2
import numpy as np

from trombinoscope.color import linear_to_srgb, srgb_to_linear
from trombinoscope.detection import model_path
from trombinoscope.log import debug, info
from trombinoscope.models import Box, SegmentationConfig

__all__ = [
    "BackgroundReplacer",
    "MaskQuality",
    "Segmenter",
    "SelfieSegmenter",
    "assess_mask",
    "replace_background",
    "segmenter_model_path",
]

#: Nom du modèle empaqueté.
MODEL_NAME = "selfie_segmenter.tflite"
#: Taille d'entrée imposée par le réseau.
INPUT_SIZE = (256, 256)


@runtime_checkable
class Segmenter(Protocol):
    """Tout objet capable de séparer le sujet du fond sur une image BGR."""

    def mask(self, image: np.ndarray) -> np.ndarray:
        """Masque flottant ``[0, 1]``, même hauteur et largeur que l'image.

        ``1`` désigne le sujet, ``0`` le fond. Les valeurs intermédiaires sont
        des bords partiellement couverts, pas une incertitude.
        """
        ...


def segmenter_model_path() -> Path:
    """Chemin du modèle de segmentation empaqueté."""
    return model_path(MODEL_NAME)


class SelfieSegmenter:
    """MediaPipe SelfieSegmenter, exécuté par ``cv2.dnn`` (poids Apache-2.0).

    Le modèle est chargé paresseusement et mis en cache par chemin, comme
    :class:`~trombinoscope.detection.YuNetDetector` : ``import trombinoscope`` ne
    charge rien, et instancier plusieurs segmenteurs ne relit pas le fichier.
    """

    def __init__(self, *, model: Path | str | None = None) -> None:
        self._model = Path(model) if model is not None else segmenter_model_path()

    def mask(self, image: np.ndarray) -> np.ndarray:
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("une image BGR à trois canaux est attendue")
        height, width = image.shape[:2]

        net = _load(str(self._model))
        blob = cv2.dnn.blobFromImage(image, 1 / 255.0, INPUT_SIZE, swapRB=True)
        net.setInput(blob)
        raw = np.squeeze(net.forward())
        if raw.ndim != 2:  # pragma: no cover - dépend de la version d'OpenCV
            raise RuntimeError(f"sortie inattendue du segmenteur : {raw.shape}")

        mask = cv2.resize(raw, (width, height), interpolation=cv2.INTER_LINEAR)
        return np.clip(mask, 0.0, 1.0).astype(np.float32)


@dataclass(frozen=True, slots=True)
class MaskQuality:
    """Verdict sur un masque, et les mesures qui l'ont produit.

    Aucun de ces indicateurs ne vient du modèle : ils sont tous géométriques, ce
    qui est justement ce qui les rend fiables — ils ne partagent pas les erreurs
    du réseau qu'ils surveillent.
    """

    #: Fraction de la boîte du visage couverte par le masque. ``None`` quand
    #: aucun visage n'a été détecté : l'indicateur le plus fort est alors
    #: indisponible, et les autres décident seuls.
    face_coverage: float | None
    #: Fraction de l'image classée sujet.
    foreground: float
    #: Composantes connexes significatives du masque.
    components: int
    #: Fraction de pixels à alpha intermédiaire — un masque sain reste bas.
    ambiguous: float
    #: Le masque touche-t-il le bord supérieur (sujet coupé) ?
    touches_top: bool
    #: ``None`` si le masque est retenu, sinon la raison du rejet.
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.reason is None

    def describe(self) -> str:
        coverage = "n/a" if self.face_coverage is None else f"{self.face_coverage:.0%}"
        return (
            f"visage {coverage}, sujet {self.foreground:.0%}, "
            f"{self.components} composante(s), ambigus {self.ambiguous:.1%}"
        )


def assess_mask(
    mask: np.ndarray, face_box: Box | None, config: SegmentationConfig | None = None
) -> MaskQuality:
    """Juge un masque sans rien demander au modèle qui l'a produit.

    L'ordre des tests est celui de leur pouvoir discriminant : la couverture du
    visage tranche presque tous les cas à elle seule, et c'est aussi la seule qui
    puisse manquer.
    """
    config = config or SegmentationConfig()
    binary = mask >= 0.5
    height, width = mask.shape[:2]

    coverage = _face_coverage(binary, face_box)
    foreground = float(binary.mean())
    components = _components(binary, config.min_component_fraction)
    ambiguous = float(((mask > 0.05) & (mask < 0.95)).mean())
    touches_top = bool(binary[0].any())

    low, high = config.foreground_range
    reason: str | None = None
    if coverage is not None and coverage < config.min_face_coverage:
        reason = f"visage couvert à {coverage:.0%} seulement"
    elif not low <= foreground <= high:
        reason = f"sujet sur {foreground:.0%} de l'image"
    elif components > config.max_components:
        reason = f"{components} fragments détachés"
    elif ambiguous > config.max_ambiguous:
        reason = f"{ambiguous:.0%} de pixels ambigus"
    elif touches_top and config.reject_touching_top:
        reason = "sujet coupé en haut du cadre"

    quality = MaskQuality(
        face_coverage=coverage,
        foreground=foreground,
        components=components,
        ambiguous=ambiguous,
        touches_top=touches_top,
        reason=reason,
    )
    debug("masque %dx%d — %s", width, height, quality.describe())
    return quality


def replace_background(
    image: np.ndarray,
    mask: np.ndarray,
    color: tuple[int, int, int] = (255, 255, 255),
    *,
    alpha_gain: float = 4.0,
    erode_px: int = 1,
) -> np.ndarray:
    """Compose l'image sur un aplat, en lumière linéaire.

    Deux traitements précèdent le mélange, dans cet ordre. ``alpha_gain`` raidit
    la rampe alpha autour de 0,5 : c'est ce qui supprime le halo, en réduisant la
    largeur de la zone où le fond d'origine transparaît encore. ``erode_px``
    rétrécit ensuite le masque du pixel ou deux de fond que le réseau inclut
    presque toujours dans le contour.

    L'ordre compte : éroder d'abord déplacerait la rampe sans la raidir, et
    laisserait donc le halo intact — mesuré à l'œil, éroder seul jusqu'à 3 px
    entame les cheveux sans effacer le liseré.
    """
    if image.shape[:2] != mask.shape[:2]:
        raise ValueError("le masque et l'image doivent avoir la même taille")

    alpha = mask.astype(np.float32)
    if alpha_gain != 1.0:
        alpha = np.clip((alpha - 0.5) * alpha_gain + 0.5, 0.0, 1.0)
    if erode_px > 0:
        size = 2 * erode_px + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        alpha = cv2.erode(alpha, kernel).astype(np.float32)

    # srgb_to_linear attend des flottants dans [0, 1] et écrête au passage :
    # lui donner du uint8 brut rendrait toute l'image blanche.
    alpha = alpha[:, :, np.newaxis]
    subject = srgb_to_linear(image.astype(np.float32) / 255.0)
    background = srgb_to_linear(np.full(image.shape, color, dtype=np.float32) / 255.0)
    blended = subject * alpha + background * (1.0 - alpha)
    return np.clip(linear_to_srgb(blended) * 255.0, 0, 255).round().astype(np.uint8)


class BackgroundReplacer:
    """Assemble segmentation, garde-fou et compositing en une seule opération.

    Sépare volontairement le calcul du masque de son application : le pipeline
    mesure la couleur sur la photo au fond intact — un aplat blanc fausserait
    l'estimation de l'illuminant — et ne compose qu'après correction.
    """

    def __init__(
        self, config: SegmentationConfig | None = None, *, segmenter: Segmenter | None = None
    ) -> None:
        self._config = config or SegmentationConfig()
        self._segmenter = segmenter or SelfieSegmenter()

    @property
    def config(self) -> SegmentationConfig:
        return self._config

    def compute(self, image: np.ndarray, face_box: Box | None) -> tuple[np.ndarray, MaskQuality]:
        """Calcule le masque et le juge, sans rien modifier."""
        mask = self._segmenter.mask(image)
        return mask, assess_mask(mask, face_box, self._config)

    def apply(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        return replace_background(
            image,
            mask,
            self._config.background,
            alpha_gain=self._config.alpha_gain,
            erode_px=self._config.erode_px,
        )


def _face_coverage(binary: np.ndarray, face_box: Box | None) -> float | None:
    """Fraction de la boîte du visage tombant dans le masque."""
    if face_box is None:
        return None
    height, width = binary.shape[:2]
    box = face_box.clipped(width, height)
    region = binary[box.y0 : box.y1, box.x0 : box.x1]
    if region.size == 0:  # pragma: no cover - boîte hors image
        return None
    return float(region.mean())


def _components(binary: np.ndarray, min_fraction: float) -> int:
    """Nombre de composantes connexes dépassant ``min_fraction`` de l'image."""
    count, labels = cv2.connectedComponents(binary.astype(np.uint8))
    if count <= 1:
        return 0
    threshold = binary.size * min_fraction
    sizes = np.bincount(np.asarray(labels, dtype=np.int32).ravel())[1:]
    return int((sizes >= threshold).sum())


@lru_cache(maxsize=4)
def _load(model: str):
    info("chargement du modèle de segmentation %s", Path(model).name)
    return cv2.dnn.readNetFromTFLite(model)
