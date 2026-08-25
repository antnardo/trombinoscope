"""Fixtures partagées.

Principe : l'essentiel de la suite tourne sur des images **synthétiques** et un
détecteur **bouchon**. Aucune photographie, aucun réseau, aucun modèle à charger,
donc une CI rapide et déterministe qui couvre malgré tout le pipeline entier.

Les rares tests qui exercent le vrai détecteur sont marqués ``integration`` et se
sautent d'eux-mêmes si ``scripts/fetch_samples.py`` n'a pas été lancé.
"""

import csv
from pathlib import Path

import cv2
import numpy as np
import pytest

from trombinoscope.models import Box, Detection, Landmarks, Person

SAMPLE_DIR = Path(__file__).parent / "data" / "portraits"


# --------------------------------------------------------------------------- #
# Images synthétiques
# --------------------------------------------------------------------------- #


def make_photo(
    width: int = 600,
    height: int = 800,
    *,
    face: Box | None = None,
    background: tuple[int, int, int] = (200, 190, 180),
    skin: tuple[int, int, int] = (150, 180, 210),
) -> np.ndarray:
    """Image BGR avec un « visage » repérable : un ovale de teinte chair sur un fond.

    Ce n'est pas destiné à être détecté par un vrai détecteur — c'est le rôle du
    bouchon — mais à porter une géométrie et une colorimétrie connues, ce qui rend
    les assertions exactes plutôt qu'approximatives.
    """
    face = face or default_face_box(width, height)
    image = np.full((height, width, 3), background, dtype=np.uint8)
    # Un dégradé léger, pour que l'étalement d'histogramme ait de quoi travailler.
    ramp = np.linspace(-20, 20, width, dtype=np.float32)[None, :, None]
    image = np.clip(image.astype(np.float32) + ramp, 0, 255).astype(np.uint8)

    cv2.ellipse(
        image,
        (int(face.center[0]), int(face.center[1])),
        (face.width // 2, face.height // 2),
        0,
        0,
        360,
        skin,
        thickness=-1,
    )
    return image


def default_face_box(width: int = 600, height: int = 800) -> Box:
    """Boîte de visage utilisée par défaut par :func:`make_photo` et le bouchon."""
    face_w = width // 4
    face_h = int(face_w * 1.3)
    x0 = (width - face_w) // 2
    y0 = height // 5
    return Box(x0, y0, x0 + face_w, y0 + face_h)


def apply_cast(image: np.ndarray, gains: tuple[float, float, float]) -> np.ndarray:
    """Applique une dominante colorée connue, en BGR."""
    scaled = image.astype(np.float32) * np.array(gains, dtype=np.float32).reshape(1, 1, 3)
    return np.clip(scaled, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------- #
# Détecteur bouchon
# --------------------------------------------------------------------------- #


class StubDetector:
    """Renvoie des détections fixées d'avance, sans charger le moindre modèle."""

    def __init__(self, detections: list[Detection] | None = None) -> None:
        self.detections = detections
        self.calls = 0

    def detect(self, image: np.ndarray) -> list[Detection]:
        self.calls += 1
        if self.detections is not None:
            return list(self.detections)
        height, width = image.shape[:2]
        box = default_face_box(width, height)
        return [Detection(box=box, confidence=0.99, landmarks=landmarks_for(box))]


def landmarks_for(box: Box, *, tilt: float = 0.0) -> Landmarks:
    """Points caractéristiques cohérents avec une boîte, éventuellement inclinés."""
    cx, cy = box.center
    eye_dx = box.width * 0.22
    eye_dy = box.height * 0.12
    offset = box.width * tilt
    return Landmarks(
        right_eye=(cx - eye_dx, cy - eye_dy - offset),
        left_eye=(cx + eye_dx, cy - eye_dy + offset),
        nose=(cx, cy),
        right_mouth=(cx - eye_dx * 0.7, cy + box.height * 0.2),
        left_mouth=(cx + eye_dx * 0.7, cy + box.height * 0.2),
    )


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def face_box() -> Box:
    return default_face_box()


@pytest.fixture
def photo(face_box: Box) -> np.ndarray:
    return make_photo(face=face_box)


@pytest.fixture
def detection(face_box: Box) -> Detection:
    return Detection(box=face_box, confidence=0.95, landmarks=landmarks_for(face_box))


@pytest.fixture
def stub_detector() -> StubDetector:
    return StubDetector()


@pytest.fixture
def people() -> list[Person]:
    return [
        Person("HOPPER", "Grace", tags=("Maths",), groups=("Gr1",), badge=True),
        Person("JOHNSON", "Katherine", tags=("Info",), groups=("Gr2",)),
        Person("PERLMAN", "Radia", tags=("Réseaux",), groups=("Gr1",)),
        Person("KNUTH", "Donald", tags=("TeX",), groups=("Gr3",), badge=True),
        Person("KAY", "Alan"),
    ]


@pytest.fixture
def photo_dir(tmp_path: Path) -> Path:
    """Dossier de cinq photos synthétiques, nommées dans l'ordre attendu."""
    folder = tmp_path / "photos"
    folder.mkdir()
    # Dominantes différentes : de quoi donner du travail à l'harmonisation.
    casts = [(1.0, 1.0, 1.0), (1.25, 0.95, 0.85), (0.8, 1.0, 1.2), (1.1, 1.1, 0.9), (0.9, 0.9, 1.0)]
    for index, cast in enumerate(casts, start=1):
        cv2.imwrite(str(folder / f"{index:02d}.jpg"), apply_cast(make_photo(), cast))
    return folder


@pytest.fixture
def roster_csv(tmp_path: Path, people: list[Person]) -> Path:
    path = tmp_path / "roster.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["nom", "prenom", "tags", "groupes", "badge"])
        for person in people:
            writer.writerow(
                [
                    person.last_name,
                    person.first_name,
                    ";".join(person.tags),
                    ";".join(person.groups),
                    "1" if person.badge else "",
                ]
            )
    return path


@pytest.fixture
def sample_photos() -> list[Path]:
    """Portraits réels téléchargés par ``scripts/fetch_samples.py``, ou skip."""
    photos = sorted(SAMPLE_DIR.glob("*.jpg"))
    if not photos:
        pytest.skip("portraits absents : lancer `python scripts/fetch_samples.py`")
    return photos
