"""Homogénéisation colorimétrique des portraits.

Voir ``docs/color.md`` pour l'étude complète, mesures à l'appui.

Résumé de l'implémentation :

1. **Estimation d'illuminant** par une norme de Minkowski (`Shades of Gray`,
   Finlayson & Trezzi 2004), calculée **en lumière linéaire** — une correction
   diagonale appliquée à des valeurs encodées en sRGB n'a pas de sens physique et
   sous-corrige systématiquement les dominantes fortes.
2. **Correction de von Kries** : un gain par canal, borné, pour éviter qu'une
   photo au fond bleu saturé ne se voie appliquer un gain rouge délirant.
3. **Normalisation d'exposition** par correction gamma sur la luminance médiane
   du **visage**, et non de l'image entière : un mur blanc ou un fond sombre ne
   doit pas décider de l'exposition d'un portrait.
4. **Harmonisation du lot** : l'illuminant de référence et la luminance cible sont
   les médianes du lot. C'est l'étape qui rend un trombinoscope visuellement
   cohérent, et celle qu'aucune bibliothèque de correction couleur ne fournit —
   toutes travaillent image par image.

Précaution : on estime toujours l'*illuminant* (une propriété de l'éclairage) et
jamais une teinte de peau cible. Ramener tous les visages vers une carnation de
référence modifierait la couleur de peau des personnes photographiées ; ce
paquet ne le fait pas et ne propose pas d'option pour le faire.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import cv2
import numpy as np

from trombinoscope.log import debug
from trombinoscope.models import Box, ColorConfig

__all__ = [
    "AutoLevels",
    "BatchColorHarmonizer",
    "GrayWorldEstimator",
    "IlluminantEstimator",
    "LuminanceMatcher",
    "ShadesOfGrayEstimator",
    "WhiteBalancer",
    "WhitePatchEstimator",
    "build_estimator",
    "face_mask",
    "linear_to_srgb",
    "median_luminance",
    "srgb_to_linear",
]

_EPS = 1e-6


# --------------------------------------------------------------------------- #
# Espaces colorimétriques
# --------------------------------------------------------------------------- #


def srgb_to_linear(image: np.ndarray) -> np.ndarray:
    """Décode sRGB → lumière linéaire. Entrée et sortie en float dans ``[0, 1]``."""
    x = np.clip(image.astype(np.float32), 0.0, 1.0)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


def linear_to_srgb(image: np.ndarray) -> np.ndarray:
    """Encode lumière linéaire → sRGB. Entrée et sortie en float dans ``[0, 1]``."""
    x = np.clip(image.astype(np.float32), 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * x ** (1 / 2.4) - 0.055).astype(np.float32)


def _to_float(image: np.ndarray) -> np.ndarray:
    if image.dtype == np.uint8:
        return image.astype(np.float32) / 255.0
    return image.astype(np.float32)


def _to_uint8(image: np.ndarray) -> np.ndarray:
    return np.clip(image * 255.0 + 0.5, 0, 255).astype(np.uint8)


def face_mask(
    shape: tuple[int, ...], box: Box | None, *, shrink: float = 0.75
) -> np.ndarray | None:
    """Masque booléen elliptique inscrit dans la boîte du visage.

    L'ellipse est resserrée (``shrink``) pour exclure cheveux, oreilles et bord de
    fond que la boîte englobante inclut toujours. Renvoie ``None`` si aucune boîte
    n'est fournie, ce qui fait retomber les estimateurs sur l'image entière.
    """
    if box is None:
        return None
    height, width = shape[:2]
    inner = box.scaled(shrink).clipped(width, height)
    mask = np.zeros((height, width), dtype=np.uint8)
    center = (round((inner.x0 + inner.x1) / 2), round((inner.y0 + inner.y1) / 2))
    axes = (max(inner.width // 2, 1), max(inner.height // 2, 1))
    cv2.ellipse(mask, center, axes, 0, 0, 360, color=1, thickness=-1)
    return mask.astype(bool)


def _samples(linear: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
    """Pixels retenus pour l'estimation, en ``(N, 3)``.

    Les pixels saturés sont écartés : un pixel écrêté ne porte plus l'information
    de l'illuminant, il tire seulement l'estimation vers le blanc.
    """
    pixels = linear[mask] if mask is not None else linear.reshape(-1, 3)
    if pixels.size == 0:
        return linear.reshape(-1, 3)
    unclipped = pixels[(pixels < 0.98).all(axis=1)]
    return unclipped if unclipped.shape[0] >= 32 else pixels


# --------------------------------------------------------------------------- #
# Estimation d'illuminant
# --------------------------------------------------------------------------- #


@runtime_checkable
class IlluminantEstimator(Protocol):
    """Estime la couleur de la source lumineuse d'une image en lumière linéaire."""

    def estimate(self, linear: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
        """Vecteur BGR de norme 1 décrivant l'illuminant."""
        ...


def _normalize(vector: np.ndarray) -> np.ndarray:
    vector = np.maximum(vector.astype(np.float32), _EPS)
    return vector / float(np.linalg.norm(vector))


@dataclass(frozen=True, slots=True)
class ShadesOfGrayEstimator:
    """Norme de Minkowski d'ordre ``p`` (Finlayson & Trezzi, 2004).

    ``p = 1`` redonne exactement Gray World, ``p → ∞`` redonne White Patch.
    ``p = 6`` est la valeur empirique de l'article original, et reste le meilleur
    compromis sans apprentissage sur des portraits à fond uni.
    """

    p: float = 6.0

    def estimate(self, linear: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
        pixels = _samples(linear, mask)
        if not np.isfinite(self.p) or self.p > 64:
            return _normalize(pixels.max(axis=0))
        moment = np.mean(np.power(pixels.astype(np.float64), self.p), axis=0)
        return _normalize(np.power(moment, 1.0 / self.p))


@dataclass(frozen=True, slots=True)
class GrayWorldEstimator:
    """Hypothèse du monde gris : la moyenne de la scène est neutre.

    Robuste et sans paramètre, mais mise en défaut dès qu'une couleur domine la
    surface de l'image — un fond de rideau rouge suffit à la faire dériver.
    """

    def estimate(self, linear: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
        return _normalize(_samples(linear, mask).mean(axis=0))


@dataclass(frozen=True, slots=True)
class WhitePatchEstimator:
    """Retinex « white patch » adouci : percentile par canal au lieu du maximum.

    Prendre le maximum brut, comme le fait la formulation historique de Land,
    revient à caler la balance sur un unique reflet spéculaire ou un pixel mort du
    capteur.
    """

    percentile: float = 97.0

    def estimate(self, linear: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
        pixels = _samples(linear, mask)
        return _normalize(np.percentile(pixels, self.percentile, axis=0))


def build_estimator(name: str, config: ColorConfig | None = None) -> IlluminantEstimator | None:
    """Fabrique un estimateur par nom. ``"none"`` renvoie ``None``."""
    config = config or ColorConfig()
    match name:
        case "none":
            return None
        case "grayworld":
            return GrayWorldEstimator()
        case "shades-of-gray":
            return ShadesOfGrayEstimator(p=config.minkowski_p)
        case "white-patch":
            return WhitePatchEstimator(percentile=config.white_patch_percentile)
        case _:
            raise ValueError(
                f"méthode de balance des blancs inconnue : {name!r} "
                "(none, grayworld, shades-of-gray, white-patch)"
            )


# --------------------------------------------------------------------------- #
# Correction
# --------------------------------------------------------------------------- #


class WhiteBalancer:
    """Applique une correction diagonale de von Kries en lumière linéaire.

    Le gain de chaque canal est le rapport entre l'illuminant *cible* et
    l'illuminant *estimé*. Sans cible explicite, la cible est le gris neutre, ce
    qui revient à la balance des blancs classique ; en passant l'illuminant médian
    du lot, on aligne au contraire toutes les photos les unes sur les autres, ce
    qui préserve l'ambiance de la séance tout en supprimant les écarts.
    """

    def __init__(
        self, estimator: IlluminantEstimator, *, max_gain: float = 2.0, strength: float = 1.0
    ) -> None:
        if max_gain < 1.0:
            raise ValueError("max_gain doit être >= 1")
        if not 0.0 <= strength <= 1.0:
            raise ValueError("strength doit être dans [0, 1]")
        self._estimator = estimator
        self._max_gain = max_gain
        self._strength = strength

    def estimate(self, image: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
        """Illuminant de l'image, en lumière linéaire, normalisé."""
        return self._estimator.estimate(srgb_to_linear(_to_float(image)), mask)

    def gains(self, illuminant: np.ndarray, target: np.ndarray | None = None) -> np.ndarray:
        """Gains par canal, bornés à ``[1/max_gain, max_gain]``.

        Les gains sont renormalisés autour de leur moyenne géométrique pour que la
        correction ne change pas la luminosité globale : seule la *teinte* bouge,
        l'exposition est traitée séparément par :class:`LuminanceMatcher`.

        ``strength`` interpole ensuite géométriquement vers l'identité : élever un
        gain à la puissance ``s`` conserve la neutralité de la moyenne géométrique,
        ce qu'une interpolation linéaire ne ferait pas.
        """
        illuminant = np.maximum(np.asarray(illuminant, dtype=np.float32), _EPS)
        if target is None:
            target = np.full(3, 1 / np.sqrt(3), dtype=np.float32)
        target = np.maximum(np.asarray(target, dtype=np.float32), _EPS)

        raw = target / illuminant
        raw /= float(np.exp(np.mean(np.log(raw))))
        if self._strength != 1.0:
            raw = np.power(raw, self._strength)
        return np.clip(raw, 1.0 / self._max_gain, self._max_gain).astype(np.float32)

    def apply(self, image: np.ndarray, gains: np.ndarray) -> np.ndarray:
        """Applique des gains déjà calculés. Entrée/sortie en BGR uint8."""
        linear = srgb_to_linear(_to_float(image))
        corrected = linear * np.asarray(gains, dtype=np.float32).reshape(1, 1, 3)
        return _to_uint8(linear_to_srgb(corrected))

    def balance(
        self,
        image: np.ndarray,
        mask: np.ndarray | None = None,
        target: np.ndarray | None = None,
    ) -> np.ndarray:
        """Estime puis corrige, en une passe."""
        gains = self.gains(self.estimate(image, mask), target)
        debug("gains B=%.3f G=%.3f R=%.3f", *gains)
        return self.apply(image, gains)


class AutoLevels:
    """Étalement d'histogramme sur la luminance, avec écrêtage symétrique.

    Le calcul se fait sur un masque optionnel — la zone du visage plutôt que le
    fond —, le gain est borné, et une image de plage dynamique nulle renvoie
    l'identité plutôt qu'une division par zéro.

    Désactivé par défaut : sur un lot hétérogène, l'étalement *dégrade* la
    cohérence, parce qu'il cale la plage sur le seul visage et brûle donc les
    fonds. Voir ``docs/color.md``, section 5.
    """

    def __init__(self, clip_percent: float = 0.5, *, max_gain: float = 3.0) -> None:
        if not 0 <= clip_percent < 50:
            raise ValueError("clip_percent doit être dans [0, 50[")
        self._clip_percent = clip_percent
        self._max_gain = max_gain

    def levels(self, image: np.ndarray, mask: np.ndarray | None = None) -> tuple[float, float]:
        """Couple ``(alpha, beta)`` tel que ``sortie = alpha * entrée + beta``."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        values = gray[mask] if mask is not None else gray.reshape(-1)
        if values.size == 0:
            return 1.0, 0.0

        low = float(np.percentile(values, self._clip_percent))
        high = float(np.percentile(values, 100.0 - self._clip_percent))
        if high - low < 1.0:
            debug("plage dynamique nulle (%.1f..%.1f), aucun étalement", low, high)
            return 1.0, 0.0

        alpha = min(255.0 / (high - low), self._max_gain)
        return alpha, -low * alpha

    def apply(self, image: np.ndarray, alpha: float, beta: float) -> np.ndarray:
        # Arguments nommés obligatoirement : la signature d'OpenCV est
        # convertScaleAbs(src, dst, alpha, beta), et un appel positionnel enverrait
        # le gain dans le paramètre de sortie `dst`.
        return cv2.convertScaleAbs(image, alpha=alpha, beta=beta)

    def transform(self, image: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
        alpha, beta = self.levels(image, mask)
        return self.apply(image, alpha, beta)


def median_luminance(image: np.ndarray, mask: np.ndarray | None = None) -> float:
    """Luminance perceptuelle médiane, dans ``[0, 255]``.

    Mesurée sur le canal ``L`` de CIE L*a*b* : la luminance sRGB pondérée serait
    biaisée par la teinte, et un simple ``BGR2GRAY`` n'est pas perceptuellement
    uniforme.
    """
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    channel = lab[:, :, 0]
    values = channel[mask] if mask is not None else channel
    if values.size == 0:
        return float(np.median(channel))
    return float(np.median(values))


class LuminanceMatcher:
    """Aligne la luminance médiane d'une image sur une cible, par correction gamma.

    Une correction gamma est préférée à un gain linéaire parce qu'elle est monotone
    et ne peut pas écrêter : remonter une photo sous-exposée de deux diaphragmes
    par ``image * 4`` brûlerait toutes les hautes lumières, alors que le gamma les
    comprime.
    """

    def __init__(self, *, min_gamma: float = 0.4, max_gamma: float = 2.5) -> None:
        self._min_gamma = min_gamma
        self._max_gamma = max_gamma

    def gamma_for(self, current: float, target: float) -> float:
        """Exposant tel que ``(current/255) ** gamma == target/255``."""
        current = float(np.clip(current, 1.0, 254.0)) / 255.0
        target = float(np.clip(target, 1.0, 254.0)) / 255.0
        gamma = np.log(target) / np.log(current)
        return float(np.clip(gamma, self._min_gamma, self._max_gamma))

    def apply(self, image: np.ndarray, gamma: float) -> np.ndarray:
        if abs(gamma - 1.0) < 1e-3:
            return image
        table = np.clip(((np.arange(256) / 255.0) ** gamma) * 255.0, 0, 255).astype(np.uint8)
        return cv2.LUT(image, table)

    def transform(
        self, image: np.ndarray, target: float, mask: np.ndarray | None = None
    ) -> np.ndarray:
        return self.apply(image, self.gamma_for(median_luminance(image, mask), target))


# --------------------------------------------------------------------------- #
# Harmonisation du lot
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ColorSample:
    """Mesures faites sur une photo pendant la passe d'analyse."""

    illuminant: np.ndarray
    luminance: float


class BatchColorHarmonizer:
    """Homogénéise un lot de portraits en deux passes.

    Passe 1 (:meth:`measure`) : sur chaque photo, estimation de l'illuminant et de
    la luminance médiane, restreintes à la zone du visage quand elle est connue.

    Passe 2 (:meth:`transform`) : chaque photo est ramenée vers l'illuminant
    **médian** et la luminance **médiane** du lot. La médiane, et non la moyenne,
    parce qu'une seule photo prise à contre-jour suffirait à décaler une moyenne.

    Utiliser le lot comme référence plutôt que le gris neutre a deux vertus : le
    résultat reste fidèle à l'ambiance réelle de la séance, et les écarts entre
    portraits — le seul défaut réellement visible sur une planche imprimée —
    disparaissent. Une correction photo par photo ne peut pas y parvenir,
    puisqu'elle ignore les autres photos.
    """

    def __init__(self, config: ColorConfig | None = None) -> None:
        self._config = config or ColorConfig()
        self._estimator = build_estimator(self._config.white_balance, self._config)
        self._balancer = (
            WhiteBalancer(
                self._estimator,
                max_gain=self._config.max_gain,
                strength=self._config.strength,
            )
            if self._estimator is not None
            else None
        )
        self._levels = (
            AutoLevels(self._config.auto_levels_clip)
            if self._config.auto_levels_clip is not None
            else None
        )
        self._luminance = LuminanceMatcher()
        self._samples: list[ColorSample] = []

    @property
    def config(self) -> ColorConfig:
        return self._config

    @property
    def samples(self) -> Sequence[ColorSample]:
        return tuple(self._samples)

    # -- passe 1 ------------------------------------------------------------ #

    def measure(self, image: np.ndarray, box: Box | None = None) -> ColorSample:
        """Mesure une photo et mémorise le résultat pour le calcul de la référence."""
        mask = face_mask(image.shape, box) if self._config.estimate_on_face else None
        illuminant = (
            self._balancer.estimate(image, mask)
            if self._balancer is not None
            else np.full(3, 1 / np.sqrt(3), dtype=np.float32)
        )
        sample = ColorSample(illuminant=illuminant, luminance=median_luminance(image, mask))
        self._samples.append(sample)
        return sample

    def measure_all(self, images: Iterable[tuple[np.ndarray, Box | None]]) -> None:
        for image, box in images:
            self.measure(image, box)

    # -- référence ---------------------------------------------------------- #

    @property
    def reference_illuminant(self) -> np.ndarray | None:
        """Illuminant médian du lot, ou ``None`` si rien n'a été mesuré."""
        if not self._samples:
            return None
        stacked = np.stack([s.illuminant for s in self._samples])
        return _normalize(np.median(stacked, axis=0))

    @property
    def reference_luminance(self) -> float | None:
        """Luminance médiane du lot, ou ``None`` si rien n'a été mesuré."""
        if not self._samples:
            return None
        return float(np.median([s.luminance for s in self._samples]))

    # -- passe 2 ------------------------------------------------------------ #

    def transform(self, image: np.ndarray, box: Box | None = None) -> np.ndarray:
        """Applique la correction complète à une photo, d'après la référence du lot."""
        mask = face_mask(image.shape, box) if self._config.estimate_on_face else None
        result = image

        if self._balancer is not None:
            target = self.reference_illuminant if self._config.harmonize_batch else None
            gains = self._balancer.gains(self._balancer.estimate(result, mask), target)
            result = self._balancer.apply(result, gains)

        if self._levels is not None:
            result = self._levels.transform(result, mask)

        if self._config.harmonize_batch:
            reference = self.reference_luminance
            if reference is not None:
                result = self._luminance.transform(
                    result, self._target(result, reference, mask), mask
                )

        return result

    def _target(self, image: np.ndarray, reference: float, mask: np.ndarray | None) -> float:
        """Luminance visée, bridée par ``max_luminance_shift``.

        Une photo nettement plus sombre ou plus claire que le lot est une valeur
        aberrante, pas un écart à rattraper coûte que coûte : la tirer jusqu'à la
        médiane lui fait perdre son contraste, puisque le gamma qui la déplace
        comprime la plage d'un côté. On la rapproche donc du lot sans l'y forcer.
        """
        cap = self._config.max_luminance_shift
        if cap is None:
            return reference
        current = median_luminance(image, mask)
        target = float(np.clip(reference, current - cap, current + cap))
        if target != reference:
            debug("luminance visée bridée : %.0f au lieu de %.0f", target, reference)
        return target

    def reset(self) -> None:
        self._samples.clear()
