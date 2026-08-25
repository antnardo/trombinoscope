"""Tests de la géométrie de recadrage.

Le point à vérifier n'est pas qu'une image sort, mais que le visage sort **au même
endroit et à la même taille** quelle que soit la photo d'entrée : c'est la seule
propriété qui rende une planche de portraits regardable.
"""

import numpy as np
import pytest

from trombinoscope.framing import PortraitFramer
from trombinoscope.models import Box, Detection, FramingConfig

from .conftest import landmarks_for, make_photo


def face_bbox_in(portrait: np.ndarray, skin=(150, 180, 210), tolerance: int = 30) -> Box:
    """Retrouve la zone « chair » dans un portrait produit, pour mesurer le cadrage."""
    distance = np.abs(portrait.astype(np.int16) - np.array(skin, dtype=np.int16)).sum(axis=2)
    ys, xs = np.nonzero(distance < tolerance)
    if xs.size == 0:
        raise AssertionError("aucun pixel de visage retrouvé dans le portrait")
    return Box(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


class TestPortraitFramer:
    @pytest.fixture
    def framer(self) -> PortraitFramer:
        return PortraitFramer(FramingConfig(width=300, aspect_ratio=4 / 3, face_ratio=0.5))

    def test_output_has_the_configured_size(self, framer, photo, detection):
        assert framer.frame(photo, detection).shape == (400, 300, 3)

    @pytest.mark.parametrize("aspect", [1.0, 4 / 3, 3 / 2])
    def test_output_respects_the_aspect_ratio(self, photo, detection, aspect: float):
        framer = PortraitFramer(FramingConfig(width=240, aspect_ratio=aspect))
        height, width = framer.frame(photo, detection).shape[:2]
        assert height / width == pytest.approx(aspect, rel=0.01)

    @pytest.mark.parametrize("face_ratio", [0.35, 0.5, 0.65])
    def test_face_occupies_the_requested_fraction(self, face_ratio: float):
        config = FramingConfig(width=300, face_ratio=face_ratio)
        framer = PortraitFramer(config)
        box = Box(200, 250, 340, 430)
        image = make_photo(800, 1000, face=box)

        found = face_bbox_in(framer.frame(image, Detection(box=box, confidence=0.9)))
        assert found.width / config.width == pytest.approx(face_ratio, rel=0.12)

    def test_face_is_horizontally_centered(self, framer):
        box = Box(80, 300, 200, 460)  # nettement décentré à gauche
        image = make_photo(800, 1000, face=box)
        found = face_bbox_in(framer.frame(image, Detection(box=box, confidence=0.9)))
        assert found.center[0] == pytest.approx(150, abs=8)

    @pytest.mark.parametrize("face_y,expected", [(0.0, 0.25), (0.5, 0.5), (1.0, 0.75)])
    def test_face_y_moves_the_face_vertically(self, face_y: float, expected: float):
        """Avec face_ratio=0.5 et un visage carré, le centre va de 1/4 à 3/4 de hauteur."""
        config = FramingConfig(width=300, aspect_ratio=1.0, face_ratio=0.5, face_y=face_y)
        box = Box(300, 400, 420, 520)
        image = make_photo(900, 900, face=box)
        found = face_bbox_in(
            PortraitFramer(config).frame(image, Detection(box=box, confidence=0.9))
        )
        assert found.center[1] / config.height == pytest.approx(expected, abs=0.06)

    def test_two_different_photos_give_the_same_framing(self, framer):
        """Le cœur du problème : deux prises de vue, un seul cadrage."""
        near = Box(250, 300, 550, 690)
        far = Box(380, 430, 460, 534)
        found_near = face_bbox_in(
            framer.frame(make_photo(800, 1000, face=near), Detection(box=near, confidence=0.9))
        )
        found_far = face_bbox_in(
            framer.frame(make_photo(800, 1000, face=far), Detection(box=far, confidence=0.9))
        )
        assert found_near.width == pytest.approx(found_far.width, abs=6)
        assert found_near.center[1] == pytest.approx(found_far.center[1], abs=10)


class TestOutOfBounds:
    """Un cadre qui déborde de la photo source doit produire une image, pas une erreur."""

    @pytest.fixture
    def framer(self) -> PortraitFramer:
        return PortraitFramer(FramingConfig(width=200, face_ratio=0.4))

    @pytest.mark.parametrize(
        "box",
        [
            Box(0, 0, 60, 78),  # visage collé au coin haut gauche
            Box(340, 0, 400, 78),  # coin haut droit
            Box(0, 422, 60, 500),  # coin bas gauche
            Box(170, 210, 230, 290),  # centré, cadre plus grand que la photo
        ],
        ids=["haut-gauche", "haut-droit", "bas-gauche", "cadre-trop-grand"],
    )
    def test_frame_never_raises(self, framer, box: Box):
        image = make_photo(400, 500, face=box)
        expected = (framer.config.height, framer.config.width, 3)
        assert framer.frame(image, Detection(box=box, confidence=0.9)).shape == expected

    def test_overflow_is_filled_with_the_configured_color(self):
        config = FramingConfig(width=200, face_ratio=0.2, fill=(0, 0, 255))
        box = Box(0, 0, 40, 52)
        image = make_photo(400, 500, face=box)
        portrait = PortraitFramer(config).frame(image, Detection(box=box, confidence=0.9))
        assert tuple(int(v) for v in portrait[2, 2]) == (0, 0, 255)


class TestNoDetection:
    def test_whole_photo_is_fitted_without_detection(self):
        framer = PortraitFramer(FramingConfig(width=300, aspect_ratio=4 / 3))
        portrait = framer.frame(make_photo(600, 800), None)
        assert portrait.shape == (400, 300, 3)

    def test_fitted_photo_keeps_its_own_aspect_ratio(self):
        """Une photo panoramique est encadrée de bandes, pas déformée."""
        framer = PortraitFramer(FramingConfig(width=300, aspect_ratio=4 / 3, fill=(0, 0, 255)))
        portrait = framer.frame(make_photo(800, 200), None)
        assert tuple(int(v) for v in portrait[2, 150]) == (0, 0, 255)  # bande en haut

    def test_framed_box_is_none_without_detection(self):
        assert PortraitFramer().framed_box(make_photo(), None) is None


class TestEyeAlignment:
    def test_alignment_is_off_by_default(self, photo):
        box = Box(200, 200, 320, 356)
        marks = landmarks_for(box, tilt=0.2)
        plain = PortraitFramer(FramingConfig()).frame(
            photo, Detection(box=box, confidence=0.9, landmarks=marks)
        )
        aligned = PortraitFramer(FramingConfig(align_eyes=True)).frame(
            photo, Detection(box=box, confidence=0.9, landmarks=marks)
        )
        assert not np.array_equal(plain, aligned)

    def test_alignment_without_landmarks_is_a_no_op(self, photo):
        box = Box(200, 200, 320, 356)
        detection = Detection(box=box, confidence=0.9, landmarks=None)
        with_flag = PortraitFramer(FramingConfig(align_eyes=True)).frame(photo, detection)
        without = PortraitFramer(FramingConfig(align_eyes=False)).frame(photo, detection)
        assert np.array_equal(with_flag, without)

    @pytest.mark.parametrize("tilt", [-0.2, -0.05, 0.05, 0.15])
    def test_aligned_portrait_has_level_eyes(self, tilt: float):
        """Après redressement, les deux yeux tombent à la même hauteur.

        L'assertion porte sur la position projetée des yeux, et non sur le fait que
        deux images diffèrent : une erreur de signe sur l'angle doublerait
        l'inclinaison, ce qui produit bien une image différente.
        """
        import cv2

        box = Box(300, 350, 460, 558)
        marks = landmarks_for(box, tilt=tilt)
        config = FramingConfig(width=300, align_eyes=True)
        framer = PortraitFramer(config)

        scale = (config.face_ratio * config.width) / box.width
        matrix = cv2.getRotationMatrix2D(
            box.center, framer._angle_of(Detection(box=box, confidence=0.9, landmarks=marks)), scale
        )
        eyes = np.array([[*marks.right_eye, 1.0], [*marks.left_eye, 1.0]], dtype=np.float64).T
        projected = matrix @ eyes
        assert projected[1, 0] == pytest.approx(projected[1, 1], abs=0.5)

    def test_alignment_is_a_no_op_on_level_eyes(self):
        box = Box(300, 350, 460, 558)
        detection = Detection(box=box, confidence=0.9, landmarks=landmarks_for(box, tilt=0.0))
        image = make_photo(900, 1100, face=box)
        aligned = PortraitFramer(FramingConfig(align_eyes=True)).frame(image, detection)
        plain = PortraitFramer(FramingConfig(align_eyes=False)).frame(image, detection)
        assert np.array_equal(aligned, plain)


class TestFramedBox:
    def test_reports_where_the_face_lands(self):
        config = FramingConfig(width=300, aspect_ratio=4 / 3, face_ratio=0.5, face_y=0.5)
        framer = PortraitFramer(config)
        box = Box(200, 300, 320, 456)
        framed = framer.framed_box(
            make_photo(800, 1000, face=box), Detection(box=box, confidence=0.9)
        )
        assert framed.width == pytest.approx(150, abs=2)
        assert framed.center[0] == pytest.approx(150, abs=2)

    def test_framed_box_matches_the_real_portrait(self):
        """La boîte annoncée doit correspondre à ce que le recadrage produit."""
        config = FramingConfig(width=300, face_ratio=0.5)
        framer = PortraitFramer(config)
        box = Box(250, 320, 400, 515)
        image = make_photo(900, 1100, face=box)
        detection = Detection(box=box, confidence=0.9)

        announced = framer.framed_box(image, detection)
        measured = face_bbox_in(framer.frame(image, detection))
        assert measured.center[0] == pytest.approx(announced.center[0], abs=6)
        assert measured.center[1] == pytest.approx(announced.center[1], abs=6)
