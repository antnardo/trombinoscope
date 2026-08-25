"""Tests du pipeline complet, avec un détecteur bouchon.

Toute la chaîne — lecture, appariement, cadrage, couleur, écriture, PDF — est
exercée sans charger le moindre modèle ni toucher au réseau.
"""

from pathlib import Path

import cv2
import pytest
from pypdf import PdfReader

from trombinoscope.models import ColorConfig, Detection, FramingConfig, GridConfig, Person
from trombinoscope.pipeline import BuildOptions, TrombinoscopeBuilder, build_trombinoscope

from .conftest import StubDetector, default_face_box, make_photo


@pytest.fixture
def builder(stub_detector: StubDetector) -> TrombinoscopeBuilder:
    return TrombinoscopeBuilder(
        BuildOptions(title="Essai", grid=GridConfig(columns=3)), detector=stub_detector
    )


class TestBuild:
    def test_produces_a_pdf(self, builder, photo_dir, roster_csv, tmp_path):
        report = builder.build(photo_dir, roster_csv, tmp_path / "out.pdf")
        assert report.pdf.exists()
        assert "Essai" in PdfReader(report.pdf).pages[0].extract_text()

    def test_report_is_clean_on_a_matching_set(self, builder, photo_dir, roster_csv, tmp_path):
        report = builder.build(photo_dir, roster_csv, tmp_path / "out.pdf")
        assert report.ok
        assert report.unmatched_people == [] and report.unmatched_photos == []

    def test_writes_one_portrait_per_photo(self, builder, photo_dir, roster_csv, tmp_path):
        builder.build(photo_dir, roster_csv, tmp_path / "out.pdf", portrait_dir=tmp_path / "p")
        assert len(list((tmp_path / "p").glob("*.portrait.jpg"))) == 5

    def test_portraits_have_the_configured_size(
        self, photo_dir, roster_csv, tmp_path, stub_detector
    ):
        options = BuildOptions(framing=FramingConfig(width=180, aspect_ratio=1.5))
        TrombinoscopeBuilder(options, detector=stub_detector).build(
            photo_dir, roster_csv, tmp_path / "out.pdf", portrait_dir=tmp_path / "p"
        )
        portrait = cv2.imread(str(next((tmp_path / "p").glob("*.jpg"))))
        assert portrait.shape == (270, 180, 3)

    def test_accepts_a_list_of_people_instead_of_a_file(self, builder, photo_dir, tmp_path, people):
        report = builder.build(photo_dir, people, tmp_path / "out.pdf")
        assert report.pdf.exists()

    def test_detector_is_called_once_per_photo(
        self, builder, photo_dir, roster_csv, tmp_path, stub_detector
    ):
        builder.build(photo_dir, roster_csv, tmp_path / "out.pdf")
        assert stub_detector.calls == 5

    def test_helper_function_builds_too(self, photo_dir, roster_csv, tmp_path):
        report = build_trombinoscope(photo_dir, roster_csv, tmp_path / "out.pdf")
        assert report.pdf.exists()

    def test_helper_rejects_unknown_options(self, photo_dir, roster_csv, tmp_path):
        with pytest.raises(TypeError):
            build_trombinoscope(photo_dir, roster_csv, tmp_path / "o.pdf", couleur="rouge")


class TestMatching:
    def test_absent_people_shift_the_assignment(self, photo_dir, tmp_path, stub_detector):
        """Un absent décale l'appariement d'un cran, sans le casser."""
        people = [Person(n) for n in ("A", "B", "C", "D", "E", "F")]
        options = BuildOptions(absent=("C",))
        report = TrombinoscopeBuilder(options, detector=stub_detector).build(
            photo_dir, people, tmp_path / "o.pdf", portrait_dir=tmp_path / "p"
        )
        assigned = {p.last_name: p.source_photo.name for p in people if p.source_photo}
        assert assigned == {
            "A": "01.jpg",
            "B": "02.jpg",
            "D": "03.jpg",
            "E": "04.jpg",
            "F": "05.jpg",
        }
        assert report.ok

    def test_more_people_than_photos_is_reported(self, builder, photo_dir, tmp_path):
        people = [Person(f"P{i}") for i in range(8)]
        report = builder.build(photo_dir, people, tmp_path / "o.pdf")
        assert report.unmatched_people == ["P5", "P6", "P7"]
        assert not report.ok

    def test_more_photos_than_people_is_reported(self, builder, photo_dir, tmp_path):
        report = builder.build(photo_dir, [Person("A"), Person("B")], tmp_path / "o.pdf")
        assert [p.name for p in report.unmatched_photos] == ["03.jpg", "04.jpg", "05.jpg"]

    def test_people_without_a_photo_still_appear_in_the_pdf(self, builder, photo_dir, tmp_path):
        """Ils prennent la silhouette de remplacement plutôt que de disparaître."""
        people = [Person(f"P{i}") for i in range(8)]
        report = builder.build(photo_dir, people, tmp_path / "o.pdf")
        text = PdfReader(report.pdf).pages[0].extract_text()
        assert "P7" in text


class TestDetectionFailures:
    def test_no_face_keeps_the_photo_and_the_alignment(self, photo_dir, tmp_path):
        """Une photo sans visage ne doit décaler aucune des suivantes."""
        detector = StubDetector(detections=[])
        people = [Person(f"P{i}") for i in range(5)]
        report = TrombinoscopeBuilder(BuildOptions(), detector=detector).build(
            photo_dir, people, tmp_path / "o.pdf", portrait_dir=tmp_path / "p"
        )
        assert len(report.no_face) == 5
        assert [p.source_photo.name for p in people] == [f"0{i}.jpg" for i in range(1, 6)]

    def test_multiple_faces_are_reported(self, photo_dir, tmp_path):
        box = default_face_box()
        detector = StubDetector(
            detections=[
                Detection(box=box, confidence=0.95),
                Detection(box=box.scaled(0.5), confidence=0.8),
            ]
        )
        report = TrombinoscopeBuilder(BuildOptions(), detector=detector).build(
            photo_dir, [Person(f"P{i}") for i in range(5)], tmp_path / "o.pdf"
        )
        assert len(report.multiple_faces) == 5

    def test_face_choice_selects_another_detection(self, photo_dir, tmp_path):
        big, small = default_face_box(), default_face_box().scaled(0.4)
        detector = StubDetector(
            detections=[Detection(box=big, confidence=0.95), Detection(box=small, confidence=0.8)]
        )
        options = BuildOptions(face_choice={"P0": 1}, framing=FramingConfig(width=120))
        people = [Person(f"P{i}") for i in range(5)]
        TrombinoscopeBuilder(options, detector=detector).build(
            photo_dir, people, tmp_path / "o.pdf", portrait_dir=tmp_path / "p"
        )
        chosen = cv2.imread(str(tmp_path / "p" / "01.portrait.jpg"))
        other = cv2.imread(str(tmp_path / "p" / "02.portrait.jpg"))
        assert chosen.shape == other.shape
        assert not (chosen == other).all()

    def test_negative_choice_keeps_the_whole_photo(self, photo_dir, tmp_path):
        detector = StubDetector()
        options = BuildOptions(face_choice={"P0": -1})
        people = [Person(f"P{i}") for i in range(5)]
        TrombinoscopeBuilder(options, detector=detector).build(
            photo_dir, people, tmp_path / "o.pdf", portrait_dir=tmp_path / "p"
        )
        assert (tmp_path / "p" / "01.portrait.jpg").exists()

    def test_unreadable_file_is_skipped(self, tmp_path, stub_detector):
        folder = tmp_path / "photos"
        folder.mkdir()
        cv2.imwrite(str(folder / "01.jpg"), make_photo())
        (folder / "02.jpg").write_bytes(b"pas une image")

        report = TrombinoscopeBuilder(BuildOptions(), detector=stub_detector).build(
            folder, [Person("A"), Person("B")], tmp_path / "o.pdf"
        )
        assert len(report.no_face) == 1
        assert report.pdf.exists()

    def test_debug_images_are_written_when_asked(self, photo_dir, tmp_path):
        box = default_face_box()
        detector = StubDetector(
            detections=[
                Detection(box=box, confidence=0.9),
                Detection(box=box.scaled(0.5), confidence=0.7),
            ]
        )
        options = BuildOptions(debug_dir=tmp_path / "dbg")
        TrombinoscopeBuilder(options, detector=detector).build(
            photo_dir, [Person(f"P{i}") for i in range(5)], tmp_path / "o.pdf"
        )
        assert len(list((tmp_path / "dbg").glob("*.detections.jpg"))) == 5

    def test_no_debug_images_by_default(self, builder, photo_dir, roster_csv, tmp_path):
        builder.build(photo_dir, roster_csv, tmp_path / "o.pdf")
        assert not (tmp_path / "dbg").exists()


class TestColorIntegration:
    def test_harmonization_reduces_the_spread_of_written_portraits(
        self, photo_dir, tmp_path, stub_detector
    ):
        """Vérifie sur les fichiers réellement écrits, pas sur des tableaux en mémoire."""
        import numpy as np

        from trombinoscope.color import median_luminance

        people = [Person(f"P{i}") for i in range(5)]
        TrombinoscopeBuilder(BuildOptions(), detector=stub_detector).build(
            photo_dir, people, tmp_path / "o.pdf", portrait_dir=tmp_path / "on"
        )
        after = [
            median_luminance(cv2.imread(str(p))) for p in sorted((tmp_path / "on").glob("*.jpg"))
        ]

        raw = [median_luminance(cv2.imread(str(p))) for p in sorted(photo_dir.glob("*.jpg"))]
        assert np.std(after) < np.std(raw)

    def test_color_can_be_turned_off(self, photo_dir, tmp_path, stub_detector):
        options = BuildOptions(
            color=ColorConfig(white_balance="none", auto_levels_clip=None, harmonize_batch=False)
        )
        report = TrombinoscopeBuilder(options, detector=stub_detector).build(
            photo_dir, [Person(f"P{i}") for i in range(5)], tmp_path / "o.pdf"
        )
        assert report.pdf.exists()


class TestErrors:
    def test_missing_photo_directory(self, builder, roster_csv, tmp_path):
        with pytest.raises(NotADirectoryError):
            builder.build(tmp_path / "nulle-part", roster_csv, tmp_path / "o.pdf")

    def test_missing_roster(self, builder, photo_dir, tmp_path):
        with pytest.raises(FileNotFoundError):
            builder.build(photo_dir, Path("nulle-part.csv"), tmp_path / "o.pdf")
