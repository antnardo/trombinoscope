"""Tests de la détection.

Les tests de sélection et de fabrique tournent sans modèle. Ceux qui exercent
réellement YuNet sont marqués ``integration`` et se sautent si les portraits
d'exemple n'ont pas été téléchargés.
"""

from pathlib import Path

import numpy as np
import pytest

from trombinoscope.detection import (
    HaarCascadeDetector,
    YuNetDetector,
    build_detector,
    haar_available,
    model_path,
    pick_detection,
)
from trombinoscope.imageio import read_image
from trombinoscope.models import Box, Detection


class TestModelAsset:
    def test_model_is_shipped_with_the_package(self):
        assert model_path().exists()

    def test_model_is_small_enough_to_ship(self):
        """Le modèle embarqué doit rester négligeable devant la taille de la roue."""
        assert model_path().stat().st_size < 1_000_000

    def test_unknown_model_raises(self):
        with pytest.raises(FileNotFoundError):
            model_path("inexistant.onnx")


class TestBuildDetector:
    def test_yunet_is_the_default(self):
        assert isinstance(build_detector(), YuNetDetector)

    def test_unknown_backend_lists_the_alternatives(self):
        with pytest.raises(ValueError, match="yunet"):
            build_detector("magique")

    def test_haar_backend_matches_availability(self):
        if haar_available():
            assert isinstance(build_detector("haar"), HaarCascadeDetector)
        else:
            with pytest.raises(RuntimeError, match="OpenCV 5"):
                build_detector("haar")

    @pytest.mark.parametrize("confidence", [0.0, -0.1, 1.5])
    def test_confidence_is_validated(self, confidence: float):
        with pytest.raises(ValueError, match="confidence"):
            YuNetDetector(confidence=confidence)

    def test_missing_model_file_is_reported(self, tmp_path):
        detector = YuNetDetector(model=tmp_path / "absent.onnx")
        with pytest.raises(Exception):  # noqa: B017 - OpenCV lève son propre type
            detector.detect(np.zeros((64, 64, 3), dtype=np.uint8))


class TestPickDetection:
    @pytest.fixture
    def detections(self) -> list[Detection]:
        return [
            Detection(box=Box(0, 0, 40, 50), confidence=0.95),  # petit mais sûr
            Detection(box=Box(100, 100, 300, 350), confidence=0.80),  # grand
        ]

    def test_default_takes_the_first(self, detections):
        assert pick_detection(detections) is detections[0]

    def test_index_selects_another(self, detections):
        assert pick_detection(detections, 1) is detections[1]

    def test_negative_index_means_none(self, detections):
        assert pick_detection(detections, -1) is None

    def test_out_of_range_index_gives_none(self, detections):
        assert pick_detection(detections, 5) is None

    def test_empty_list_gives_none(self):
        assert pick_detection([]) is None

    def test_largest_strategy_prefers_area_over_confidence(self, detections):
        assert pick_detection(detections, strategy="largest") is detections[1]


@pytest.mark.integration
class TestYuNetOnRealPhotos:
    @pytest.fixture
    def detector(self) -> YuNetDetector:
        # Le réseau lui-même est mis en cache par `_yunet`, cette construction est
        # donc quasi gratuite à chaque test.
        return YuNetDetector(confidence=0.6)

    def test_finds_exactly_one_face_in_each_portrait(self, detector, sample_photos: list[Path]):
        counts = {p.name: len(detector.detect(read_image(p))) for p in sample_photos}
        assert all(count == 1 for count in counts.values()), counts

    def test_detections_carry_landmarks(self, detector, sample_photos: list[Path]):
        detection = detector.detect(read_image(sample_photos[0]))[0]
        assert detection.landmarks is not None

    def test_detected_box_is_inside_the_image(self, detector, sample_photos: list[Path]):
        for path in sample_photos:
            image = read_image(path)
            height, width = image.shape[:2]
            box = detector.detect(image)[0].box
            assert 0 <= box.x0 < box.x1 <= width
            assert 0 <= box.y0 < box.y1 <= height

    def test_face_is_a_plausible_fraction_of_the_frame(self, detector, sample_photos: list[Path]):
        for path in sample_photos:
            image = read_image(path)
            box = detector.detect(image)[0].box
            fraction = box.area / (image.shape[0] * image.shape[1])
            assert 0.005 < fraction < 0.6, f"{path.name}: {fraction:.3f}"

    def test_downscaling_does_not_move_the_box(self, sample_photos: list[Path]):
        """Les coordonnées sont remises à l'échelle de la photo d'origine."""
        image = read_image(sample_photos[0])
        full = YuNetDetector(max_side=0).detect(image)[0].box
        reduced = YuNetDetector(max_side=512).detect(image)[0].box
        tolerance = max(image.shape[:2]) * 0.05
        assert abs(full.center[0] - reduced.center[0]) < tolerance
        assert abs(full.center[1] - reduced.center[1]) < tolerance

    def test_results_are_sorted_by_confidence(self, detector, sample_photos: list[Path]):
        detections = YuNetDetector(confidence=0.1).detect(read_image(sample_photos[0]))
        scores = [d.confidence for d in detections]
        assert scores == sorted(scores, reverse=True)

    def test_raising_the_threshold_never_adds_detections(self, sample_photos: list[Path]):
        image = read_image(sample_photos[0])
        assert len(YuNetDetector(confidence=0.9).detect(image)) <= len(
            YuNetDetector(confidence=0.3).detect(image)
        )

    def test_eye_angles_are_small_on_studio_portraits(self, detector, sample_photos: list[Path]):
        for path in sample_photos:
            angle = detector.detect(read_image(path))[0].landmarks.eye_angle_deg
            assert abs(angle) < 25, f"{path.name}: {angle:.1f}°"

    def test_blank_image_yields_nothing(self, detector):
        assert detector.detect(np.full((400, 300, 3), 128, dtype=np.uint8)) == []
