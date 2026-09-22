"""Tests du pipeline complet, avec un détecteur bouchon.

Toute la chaîne — lecture, appariement, cadrage, couleur, écriture, PDF — est
exercée sans charger le moindre modèle ni toucher au réseau.
"""

from pathlib import Path

import cv2
import numpy as np
import pytest
from pypdf import PdfReader

from trombinoscope.models import (
    NO_COLOR,
    ColorConfig,
    Detection,
    FramingConfig,
    GridConfig,
    Person,
    SegmentationConfig,
)
from trombinoscope.pipeline import BuildOptions, TrombinoscopeBuilder, build_trombinoscope

from .conftest import StubDetector, StubSegmenter, default_face_box, make_photo


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


# --------------------------------------------------------------------------- #
# Détourage du fond
# --------------------------------------------------------------------------- #


def subject_mask(height: int = 800, width: int = 600) -> np.ndarray:
    """Masque couvrant tout le visage mais **plus étroit que le cadre du portrait**.

    C'est la condition pour que du fond reste visible dans le portrait produit :
    un masque plus large que le recadrage ne laisserait rien à remplacer, et le
    test passerait sans rien démontrer.
    """
    face = default_face_box(width, height)
    mask = np.zeros((height, width), dtype=np.float32)
    mask[face.y0 - 10 :, face.x0 - 5 : face.x1 + 5] = 1.0
    return mask


def corner_color(portrait: Path) -> tuple[int, int, int]:
    return tuple(int(v) for v in cv2.imread(str(portrait))[2, 2])


class TestSegmentation:
    def test_le_detourage_est_inactif_par_defaut(self, photo_dir, roster_csv, tmp_path):
        stub = StubSegmenter()
        builder = TrombinoscopeBuilder(
            BuildOptions(grid=GridConfig(columns=3)),
            detector=StubDetector(),
            segmenter=stub,
        )
        builder.build(photo_dir, roster_csv, tmp_path / "out.pdf")
        assert stub.calls == 0

    def test_le_fond_est_remplace_quand_il_est_demande(self, photo_dir, roster_csv, tmp_path):
        builder = TrombinoscopeBuilder(
            BuildOptions(
                grid=GridConfig(columns=3),
                segmentation=SegmentationConfig(enabled=True, background=(255, 255, 255)),
                color=NO_COLOR,
            ),
            detector=StubDetector(),
            segmenter=StubSegmenter(subject_mask()),
        )
        report = builder.build(photo_dir, roster_csv, tmp_path / "out.pdf")
        assert not report.background_kept
        assert corner_color(report.people[0].portrait) == (255, 255, 255)

    def test_sans_detourage_le_fond_d_origine_subsiste(self, photo_dir, roster_csv, tmp_path):
        builder = TrombinoscopeBuilder(
            BuildOptions(grid=GridConfig(columns=3), color=NO_COLOR), detector=StubDetector()
        )
        report = builder.build(photo_dir, roster_csv, tmp_path / "out.pdf")
        assert corner_color(report.people[0].portrait) != (255, 255, 255)

    def test_un_masque_refuse_conserve_la_photo_et_le_signale(
        self, photo_dir, roster_csv, tmp_path
    ):
        """Le repli attendu : le traitement continue, la photo reste intacte."""
        aberrant = np.ones((800, 600), dtype=np.float32)
        builder = TrombinoscopeBuilder(
            BuildOptions(
                grid=GridConfig(columns=3),
                segmentation=SegmentationConfig(enabled=True),
                color=NO_COLOR,
            ),
            detector=StubDetector(),
            segmenter=StubSegmenter(aberrant),
        )
        report = builder.build(photo_dir, roster_csv, tmp_path / "out.pdf")
        assert len(report.background_kept) == len(report.photos)
        assert corner_color(report.people[0].portrait) != (255, 255, 255)
        assert "fond(s) conservé(s)" in report.summary()

    def test_un_fond_conserve_ne_rend_pas_le_rapport_mauvais(self, photo_dir, roster_csv, tmp_path):
        """Conserver un fond est le repli prévu, pas un échec du build."""
        builder = TrombinoscopeBuilder(
            BuildOptions(grid=GridConfig(columns=3), segmentation=SegmentationConfig(enabled=True)),
            detector=StubDetector(),
            segmenter=StubSegmenter(np.ones((800, 600), dtype=np.float32)),
        )
        report = builder.build(photo_dir, roster_csv, tmp_path / "out.pdf")
        assert report.background_kept
        assert report.ok

    def test_la_couleur_est_mesuree_avant_le_detourage(self, photo_dir, roster_csv, tmp_path):
        """Invariant d'ordre : composer avant la mesure ferait lire au batch un fond
        neutre, et la correction couleur ne corrigerait plus rien."""
        illuminants = []
        for segmentation in (SegmentationConfig(), SegmentationConfig(enabled=True)):
            builder = TrombinoscopeBuilder(
                BuildOptions(grid=GridConfig(columns=3), segmentation=segmentation),
                detector=StubDetector(),
                segmenter=StubSegmenter(subject_mask()),
            )
            builder.build(photo_dir, roster_csv, tmp_path / f"{segmentation.enabled}.pdf")
            illuminants.append(builder._harmonizer.reference_illuminant)
        assert illuminants[0] == pytest.approx(illuminants[1])
