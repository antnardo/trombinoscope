"""Recadrage des portraits autour du visage détecté.

Le visage occupe une fraction constante du cadre, ce qui rend les portraits
comparables entre eux quelle que soit la distance de prise de vue. C'est la
propriété qui rend une planche regardable.

Le recadrage est une unique transformation affine confiée à ``cv2.warpAffine``,
qui remplit lui-même les bords quand le cadre déborde de la photo source. La
rotation qui redresse la ligne des yeux se compose avec la même matrice, sans
second passage ni modèle supplémentaire.
"""

import cv2
import numpy as np

from trombinoscope.log import debug
from trombinoscope.models import Box, Detection, FramingConfig


class PortraitFramer:
    """Produit un portrait de taille fixe centré sur une détection.

    Responsabilité unique : la géométrie. Aucune correction colorimétrique ici.
    """

    def __init__(self, config: FramingConfig | None = None) -> None:
        self._config = config or FramingConfig()

    @property
    def config(self) -> FramingConfig:
        return self._config

    def frame(self, image: np.ndarray, detection: Detection | None) -> np.ndarray:
        """Portrait recadré. Sans détection, l'image est mise à l'échelle sans recadrage.

        Le repli sans détection préserve la totalité de la photo dans le bon format
        plutôt que de la couper au hasard : mieux vaut un portrait mal cadré mais
        entier, qu'un cadrage arbitraire qui décapiterait le sujet.
        """
        if detection is None:
            return self._fit_whole(image)
        return self.frame_box(
            image,
            detection.box,
            angle=self._angle_of(detection),
        )

    def frame_box(self, image: np.ndarray, box: Box, *, angle: float = 0.0) -> np.ndarray:
        """Recadre autour d'une boîte explicite, avec une rotation optionnelle."""
        config = self._config
        out_w, out_h = config.width, config.height

        scale = (config.face_ratio * out_w) / max(box.width, 1)
        source_center = box.center

        # Le visage garde sa hauteur relative : la marge verticale restante est
        # répartie selon face_y (0 = visage collé en haut, 1 = collé en bas).
        face_h = box.height * scale
        target_x = out_w / 2
        target_y = config.face_y * (out_h - face_h) + face_h / 2

        matrix = cv2.getRotationMatrix2D(source_center, angle, scale)
        matrix[0, 2] += target_x - source_center[0]
        matrix[1, 2] += target_y - source_center[1]

        debug(
            "cadrage : échelle %.3f, rotation %.1f°, cible (%.0f, %.0f)",
            scale,
            angle,
            target_x,
            target_y,
        )
        return cv2.warpAffine(
            image,
            matrix,
            (out_w, out_h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=config.fill,
        )

    def _angle_of(self, detection: Detection) -> float:
        if not self._config.align_eyes or detection.landmarks is None:
            return 0.0
        # La matrice d'OpenCV vaut [[α, β, …], [−β, α, …]] avec α = s·cos θ et
        # β = s·sin θ. L'écart vertical entre les deux yeux après transformation
        # vaut −β·Δx + α·Δy, qui s'annule pour tan θ = Δy/Δx : l'angle à passer est
        # l'inclinaison elle-même, et non son opposé.
        return detection.landmarks.eye_angle_deg

    def _fit_whole(self, image: np.ndarray) -> np.ndarray:
        """Met la photo entière au format demandé, en ajoutant des bandes de fond."""
        config = self._config
        out_w, out_h = config.width, config.height
        height, width = image.shape[:2]
        scale = min(out_w / width, out_h / height)

        matrix = np.array(
            [
                [scale, 0.0, (out_w - width * scale) / 2],
                [0.0, scale, (out_h - height * scale) / 2],
            ],
            dtype=np.float32,
        )
        return cv2.warpAffine(
            image,
            matrix,
            (out_w, out_h),
            flags=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=config.fill,
        )

    def framed_box(self, image: np.ndarray, detection: Detection | None) -> Box | None:
        """Position du visage *dans le portrait produit*, pour masquer la correction couleur.

        Sans ce masque, l'estimation d'illuminant porterait aussi sur les bandes de
        remplissage, qui tireraient le résultat vers le neutre.
        """
        if detection is None:
            return None
        config = self._config
        scale = (config.face_ratio * config.width) / max(detection.box.width, 1)
        face_w = detection.box.width * scale
        face_h = detection.box.height * scale
        x0 = (config.width - face_w) / 2
        y0 = config.face_y * (config.height - face_h)
        return Box(round(x0), round(y0), round(x0 + face_w), round(y0 + face_h)).clipped(
            config.width, config.height
        )
