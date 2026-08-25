"""Détection de visage.

Le détecteur est une dépendance injectable (:class:`FaceDetector`) : le reste du
pipeline ne connaît que le protocole, pas le modèle. Deux implémentations sont
fournies.

:class:`YuNetDetector` (défaut) enveloppe ``cv2.FaceDetectorYN``. Le modèle ONNX
livré avec le paquet pèse 227 Ko et renvoie, en plus de la boîte englobante, cinq
points caractéristiques — de quoi redresser la ligne des yeux sans modèle
supplémentaire.

:class:`HaarCascadeDetector` est un repli sans aucun modèle à distribuer, le
classifieur en cascade étant fourni avec ``opencv-python``. Il n'existe que sur
OpenCV 4.x : voir :func:`haar_available`.
"""

from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Protocol, runtime_checkable

import cv2
import numpy as np

from trombinoscope.log import debug, info
from trombinoscope.models import Box, Detection, Landmarks

#: Score minimal en dessous duquel une détection n'est jamais retenue.
DEFAULT_CONFIDENCE = 0.6
#: Les photos sont réduites à ce côté maximal avant détection, puis les boîtes
#: sont remises à l'échelle. Au-delà, la résolution n'apporte rien au détecteur
#: et le ralentit — d'un facteur ~15 sur une photo de smartphone en 12 Mpx.
DEFAULT_MAX_SIDE = 1024


@runtime_checkable
class FaceDetector(Protocol):
    """Tout objet capable de retourner les visages d'une image BGR."""

    def detect(self, image: np.ndarray) -> list[Detection]:
        """Visages trouvés, triés par confiance décroissante."""
        ...


def model_path(name: str = "face_detection_yunet_2023mar.onnx") -> Path:
    """Chemin d'un modèle empaqueté dans ``trombinoscope/assets/models``."""
    from importlib.resources import files

    resource = files("trombinoscope").joinpath("assets", "models", name)
    path = Path(str(resource))
    if not path.exists():
        raise FileNotFoundError(f"modèle absent du paquet : {name}")
    return path


class YuNetDetector:
    """Détecteur YuNet (OpenCV Zoo, licence MIT).

    Le modèle est chargé paresseusement, à la première détection, et mis en cache
    par chemin : instancier plusieurs détecteurs ne relit pas le fichier ONNX, et
    ``import trombinoscope`` ne charge rien.
    """

    def __init__(
        self,
        *,
        confidence: float = DEFAULT_CONFIDENCE,
        nms_threshold: float = 0.3,
        top_k: int = 50,
        max_side: int = DEFAULT_MAX_SIDE,
        model: Path | str | None = None,
    ) -> None:
        if not 0 < confidence <= 1:
            raise ValueError("confidence doit être dans ]0, 1]")
        self._confidence = confidence
        self._nms_threshold = nms_threshold
        self._top_k = top_k
        self._max_side = max_side
        self._model = Path(model) if model is not None else model_path()

    @property
    def confidence(self) -> float:
        return self._confidence

    def detect(self, image: np.ndarray) -> list[Detection]:
        working, scale = _downscale(image, self._max_side)
        height, width = working.shape[:2]

        detector = _yunet(str(self._model), self._nms_threshold, self._top_k)
        detector.setScoreThreshold(self._confidence)
        detector.setInputSize((width, height))
        _, faces = detector.detect(working)
        if faces is None:
            debug("aucun visage détecté")
            return []

        detections = [self._to_detection(row, scale) for row in faces]
        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections

    @staticmethod
    def _to_detection(row: np.ndarray, scale: float) -> Detection:
        x, y, w, h = (float(v) / scale for v in row[:4])
        points = [(float(row[i]) / scale, float(row[i + 1]) / scale) for i in range(4, 14, 2)]
        return Detection(
            box=Box.from_xywh(x, y, w, h),
            confidence=float(row[14]),
            landmarks=Landmarks(*points),
        )


def haar_available() -> bool:
    """``True`` si cette version d'OpenCV fournit les cascades de Haar.

    ``cv2.CascadeClassifier`` et les fichiers XML de ``cv2.data.haarcascades``
    n'existent plus depuis OpenCV 5.0 : le repli est réservé à OpenCV 4.x.
    """
    if not hasattr(cv2, "CascadeClassifier"):
        return False
    return _cascade_file().exists()


class HaarCascadeDetector:
    """Repli en cascade de Haar, sans modèle à distribuer (OpenCV 4.x uniquement).

    Nettement moins précis que YuNet — pas de profils, sensible à l'inclinaison, et
    aucun point caractéristique — mais il ne demande aucun fichier supplémentaire.
    Le score renvoyé est dérivé du nombre de voisins retenus, ramené dans
    ``[0, 1]`` : ce n'est pas une probabilité, seulement un ordre de préférence.
    """

    def __init__(self, *, scale_factor: float = 1.1, min_neighbors: int = 5) -> None:
        if not haar_available():
            raise RuntimeError(
                "les cascades de Haar ont été retirées d'OpenCV 5 : utilisez le "
                "backend 'yunet', ou installez 'opencv-python<5'"
            )
        self._scale_factor = scale_factor
        self._min_neighbors = min_neighbors

    def detect(self, image: np.ndarray) -> list[Detection]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        cascade = _haar_cascade()
        boxes, _, weights = cascade.detectMultiScale3(
            gray,
            scaleFactor=self._scale_factor,
            minNeighbors=self._min_neighbors,
            outputRejectLevels=True,
        )
        if len(boxes) == 0:
            return []
        highest = max(float(w) for w in weights) or 1.0
        detections = [
            Detection(box=Box.from_xywh(*box), confidence=min(float(weight) / highest, 1.0))
            for box, weight in zip(boxes, weights, strict=True)
        ]
        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections


def _downscale(image: np.ndarray, max_side: int) -> tuple[np.ndarray, float]:
    """Réduit l'image si nécessaire. Renvoie l'image et le facteur appliqué."""
    height, width = image.shape[:2]
    longest = max(height, width)
    if max_side <= 0 or longest <= max_side:
        return image, 1.0
    scale = max_side / longest
    resized = cv2.resize(
        image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA
    )
    debug("image réduite d'un facteur %.3f pour la détection", scale)
    return resized, scale


@lru_cache(maxsize=4)
def _yunet(model: str, nms_threshold: float, top_k: int):
    info("chargement du modèle de détection %s", Path(model).name)
    return cv2.FaceDetectorYN.create(
        model=model,
        config="",
        input_size=(320, 320),
        score_threshold=0.5,
        nms_threshold=nms_threshold,
        top_k=top_k,
    )


def _cascade_file() -> Path:
    return Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"


@lru_cache(maxsize=1)
def _haar_cascade():
    path = _cascade_file()
    cascade = cv2.CascadeClassifier(str(path))
    if cascade.empty():  # pragma: no cover - installation opencv cassée
        raise FileNotFoundError(f"cascade introuvable : {path}")
    return cascade


def build_detector(backend: str = "yunet", **kwargs) -> FaceDetector:
    """Fabrique un détecteur par nom : ``"yunet"`` ou ``"haar"``."""
    backends = {"yunet": YuNetDetector, "haar": HaarCascadeDetector}
    try:
        factory = backends[backend]
    except KeyError:
        raise ValueError(
            f"backend inconnu : {backend!r} (disponibles : {', '.join(sorted(backends))})"
        ) from None
    if factory is HaarCascadeDetector:
        kwargs.pop("confidence", None)
        kwargs.pop("model", None)
        kwargs.pop("max_side", None)
    return factory(**kwargs)


def pick_detection(
    detections: Sequence[Detection], index: int = 0, *, strategy: str = "confidence"
) -> Detection | None:
    """Choisit une détection parmi plusieurs.

    ``strategy`` vaut ``"confidence"`` (la liste est déjà triée) ou ``"largest"``,
    utile quand la photo contient un visage d'arrière-plan mieux net que le sujet.
    Un ``index`` négatif signifie « aucune détection ne convient », ce qui laisse la
    photo non recadrée plutôt que mal recadrée.
    """
    if index < 0 or not detections:
        return None
    ordered = (
        sorted(detections, key=lambda d: d.box.area, reverse=True)
        if strategy == "largest"
        else list(detections)
    )
    if index >= len(ordered):
        return None
    return ordered[index]
