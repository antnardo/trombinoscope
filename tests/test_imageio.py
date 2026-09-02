"""Tests de la lecture, de l'écriture et de la recherche de fichiers image."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from trombinoscope.imageio import (
    ImageReadError,
    draw_detections,
    find_images,
    read_image,
    supported_suffixes,
    write_image,
)
from trombinoscope.models import Box, Detection

from .conftest import make_photo


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    target = tmp_path / "photos"
    target.mkdir()
    return target


def put(folder: Path, name: str) -> Path:
    path = folder / name
    cv2.imwrite(str(path), make_photo(60, 80))
    return path


class TestFindImages:
    def test_sorted_by_filename(self, folder):
        for name in ("c.jpg", "a.jpg", "b.jpg"):
            put(folder, name)
        assert [p.name for p in find_images(folder)] == ["a.jpg", "b.jpg", "c.jpg"]

    def test_sorting_ignores_case(self, folder):
        for name in ("B.jpg", "a.jpg", "C.jpg"):
            put(folder, name)
        assert [p.name for p in find_images(folder)] == ["a.jpg", "B.jpg", "C.jpg"]

    def test_uppercase_extensions_are_found(self, folder):
        put(folder, "a.JPG")
        put(folder, "b.JPEG")
        assert len(find_images(folder)) == 2

    def test_non_images_are_ignored(self, folder):
        put(folder, "a.jpg")
        (folder / "notes.txt").write_text("bonjour")
        (folder / "liste.csv").write_text("nom")
        assert [p.name for p in find_images(folder)] == ["a.jpg"]

    def test_hidden_files_are_ignored(self, folder):
        put(folder, "a.jpg")
        put(folder, ".DS_Store.jpg")
        assert [p.name for p in find_images(folder)] == ["a.jpg"]

    def test_subdirectories_are_ignored(self, folder):
        put(folder, "a.jpg")
        (folder / "cropped").mkdir()
        put(folder / "cropped", "b.jpg")
        assert len(find_images(folder)) == 1

    def test_case_insensitive_filesystem_does_not_duplicate(self, folder):
        """Sur macOS, `a.jpg` et `a.JPG` désignent le même fichier."""
        path = put(folder, "a.jpg")
        found = find_images(folder)
        assert len(found) == 1 and found[0].stat().st_ino == path.stat().st_ino

    def test_explicit_suffixes_restrict_the_search(self, folder):
        put(folder, "a.jpg")
        put(folder, "b.png")
        assert [p.name for p in find_images(folder, suffixes=[".png"])] == ["b.png"]

    def test_empty_folder_gives_an_empty_list(self, folder):
        assert find_images(folder) == []

    def test_missing_folder_raises(self, tmp_path):
        with pytest.raises(NotADirectoryError):
            find_images(tmp_path / "nulle-part")

    def test_a_file_is_not_a_folder(self, folder):
        path = put(folder, "a.jpg")
        with pytest.raises(NotADirectoryError):
            find_images(path)

    def test_supported_suffixes_include_jpeg(self):
        assert ".jpg" in supported_suffixes() and ".jpeg" in supported_suffixes()

    def test_heif_suffixes_are_conditional(self):
        assert (".heic" in supported_suffixes(heif=True)) is True
        assert (".heic" in supported_suffixes(heif=False)) is False


class TestReadWrite:
    def test_round_trip_preserves_the_shape(self, tmp_path):
        image = make_photo(120, 160)
        path = write_image(tmp_path / "a.png", image)
        assert read_image(path).shape == image.shape

    def test_png_round_trip_is_lossless(self, tmp_path):
        image = make_photo(60, 80)
        assert np.array_equal(read_image(write_image(tmp_path / "a.png", image)), image)

    def test_creates_missing_parent_directories(self, tmp_path):
        path = write_image(tmp_path / "x" / "y" / "a.jpg", make_photo(40, 50))
        assert path.exists()

    def test_non_ascii_path_works(self, tmp_path):
        """Un chemin accentué doit fonctionner sur les trois systèmes."""
        path = write_image(tmp_path / "élève-numéro-1 (café).jpg", make_photo(40, 50))
        assert read_image(path) is not None

    def test_missing_file_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_image(tmp_path / "absent.jpg")

    def test_garbage_file_raises_image_read_error(self, tmp_path):
        path = tmp_path / "a.jpg"
        path.write_bytes(b"ceci n'est pas une image")
        with pytest.raises(ImageReadError):
            read_image(path)

    def test_jpeg_quality_affects_file_size(self, tmp_path):
        image = make_photo(300, 400)
        low = write_image(tmp_path / "low.jpg", image, quality=30).stat().st_size
        high = write_image(tmp_path / "high.jpg", image, quality=98).stat().st_size
        assert low < high


class TestDrawDetections:
    def test_returns_a_copy(self):
        image = make_photo(100, 120)
        annotated = draw_detections(image, [Detection(box=Box(10, 10, 50, 60), confidence=0.9)])
        assert not np.array_equal(annotated, image)
        assert annotated.shape == image.shape

    def test_original_is_untouched(self):
        image = make_photo(100, 120)
        before = image.copy()
        draw_detections(image, [Detection(box=Box(10, 10, 50, 60), confidence=0.9)])
        assert np.array_equal(image, before)

    def test_no_detection_leaves_the_image_alone(self):
        image = make_photo(100, 120)
        assert np.array_equal(draw_detections(image, []), image)


class TestHeifWarning:
    """Un dossier de HEIC sans pillow-heif doit dire pourquoi il paraît vide."""

    def test_avertit_quand_les_heic_sont_illisibles(self, folder, monkeypatch, caplog):
        import trombinoscope.imageio as module

        (folder / "IMG_1.HEIC").write_bytes(b"x")
        (folder / "IMG_2.heic").write_bytes(b"x")
        put(folder, "a.jpg")
        monkeypatch.setattr(module, "supported_suffixes", lambda **_: module.IMAGE_SUFFIXES)

        with caplog.at_level("WARNING", logger="trombinoscope"):
            trouvees = find_images(folder)

        assert [p.name for p in trouvees] == ["a.jpg"]
        assert "trombinoscope[heic]" in caplog.text
        assert "2 fichier(s)" in caplog.text

    def test_pas_d_avertissement_sans_heic(self, folder, monkeypatch, caplog):
        import trombinoscope.imageio as module

        put(folder, "a.jpg")
        monkeypatch.setattr(module, "supported_suffixes", lambda **_: module.IMAGE_SUFFIXES)
        with caplog.at_level("WARNING", logger="trombinoscope"):
            find_images(folder)
        assert "heic" not in caplog.text.lower()
