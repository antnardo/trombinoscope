"""Lecture, écriture et recherche de fichiers image.

Les entrées-sorties passent par ``imdecode`` / ``imencode`` sur des octets lus en
Python, et non par ``cv2.imread`` / ``cv2.imwrite`` : ces derniers transmettent le
chemin à ``fopen`` dans l'encodage local et échouent silencieusement sur un
chemin non-ASCII sous Windows.

La recherche filtre sur le suffixe en minuscules, ce qui donne le bon résultat
que le système de fichiers soit sensible à la casse ou non, et déduplique par
inode pour les systèmes qui ne le sont pas.
"""

import os
from collections.abc import Iterable, Sequence
from pathlib import Path

import cv2
import numpy as np

from trombinoscope.log import debug, info

#: Extensions lues nativement par OpenCV.
IMAGE_SUFFIXES: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")
#: Extensions lisibles uniquement si ``pillow-heif`` est installé.
HEIF_SUFFIXES: tuple[str, ...] = (".heic", ".heif")


class ImageReadError(RuntimeError):
    """Le fichier existe mais n'a pas pu être décodé comme une image."""


def _heif_available() -> bool:
    try:
        import pillow_heif  # noqa: F401
    except ImportError:
        return False
    return True


def supported_suffixes(*, heif: bool | None = None) -> tuple[str, ...]:
    """Extensions effectivement lisibles dans cet environnement."""
    if heif is None:
        heif = _heif_available()
    return IMAGE_SUFFIXES + (HEIF_SUFFIXES if heif else ())


def find_images(folder: Path | str, *, suffixes: Sequence[str] | None = None) -> list[Path]:
    """Liste les images d'un dossier, triées par nom de fichier.

    Le tri est fait sur ``name.casefold()`` pour que ``IMG_10.jpg`` et
    ``img_9.jpg`` s'ordonnent de façon stable quel que soit le système. Les
    doublons dus à un système de fichiers insensible à la casse (le même fichier
    listé en ``.jpg`` et ``.JPG``) sont éliminés par comparaison d'inode.

    L'ordre obtenu définit l'appariement positionnel avec la liste des personnes.
    """
    folder = Path(folder)
    if not folder.is_dir():
        raise NotADirectoryError(folder)
    allowed = {s.lower() for s in (suffixes if suffixes is not None else supported_suffixes())}

    found: list[Path] = [
        entry
        for entry in folder.iterdir()
        if entry.is_file() and entry.suffix.lower() in allowed and not entry.name.startswith(".")
    ]
    found.sort(key=lambda p: p.name.casefold())
    unique = _deduplicate(found)
    info("%d image(s) trouvée(s) dans %s", len(unique), folder)
    return unique


def _deduplicate(paths: Iterable[Path]) -> list[Path]:
    """Élimine les chemins pointant vers le même fichier, en temps linéaire."""
    seen: set[tuple[int, int]] = set()
    unique: list[Path] = []
    for path in paths:
        try:
            stat = path.stat()
            key = (stat.st_dev, stat.st_ino)
        except OSError:  # pragma: no cover - lien cassé
            unique.append(path)
            continue
        if key in seen and stat.st_ino != 0:
            debug("doublon ignoré : %s", path)
            continue
        seen.add(key)
        unique.append(path)
    return unique


def read_image(path: Path | str) -> np.ndarray:
    """Charge une image en BGR, orientation EXIF appliquée.

    Lève :class:`FileNotFoundError` si le fichier n'existe pas et
    :class:`ImageReadError` s'il n'est pas décodable.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    if path.suffix.lower() in HEIF_SUFFIXES:
        return _read_heif(path)

    raw = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    image = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if image is None:
        raise ImageReadError(f"format non reconnu : {path}")
    return image


def _read_heif(path: Path) -> np.ndarray:
    try:
        import pillow_heif
    except ImportError as exc:  # pragma: no cover - dépend de l'installation
        raise ImageReadError(
            f"{path.suffix} nécessite pillow-heif : pip install 'trombinoscope[heic]'"
        ) from exc
    from PIL import Image

    pillow_heif.register_heif_opener()
    with Image.open(path) as handle:
        rgb = np.asarray(handle.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def write_image(path: Path | str, image: np.ndarray, *, quality: int = 92) -> Path:
    """Écrit une image BGR, en créant le dossier parent au besoin."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower() or ".jpg"
    params: list[int] = []
    if suffix in (".jpg", ".jpeg"):
        params = [cv2.IMWRITE_JPEG_QUALITY, quality]
    ok, buffer = cv2.imencode(suffix, image, params)
    if not ok:
        raise OSError(f"encodage impossible vers {suffix}")
    path.write_bytes(buffer.tobytes())
    return path


def draw_detections(image: np.ndarray, detections: Sequence, *, thickness: int = 2) -> np.ndarray:
    """Copie annotée de l'image, avec l'index et le score de chaque détection.

    Sert au diagnostic quand plusieurs visages sont trouvés : l'index affiché est
    celui à passer en correction manuelle (``--pick NOM=INDEX``).
    """
    annotated = image.copy()
    scale = max(image.shape[:2]) / 800
    for index, detection in enumerate(detections):
        box = detection.box
        cv2.rectangle(
            annotated, (box.x0, box.y0), (box.x1, box.y1), (0, 0, 255), thickness=thickness
        )
        cv2.putText(
            annotated,
            f"{index} {detection.confidence:.0%}",
            (box.x0, max(box.y0 - 6, 14)),
            cv2.FONT_HERSHEY_SIMPLEX,
            max(scale, 0.4),
            (0, 0, 255),
            thickness,
        )
    return annotated


def open_with_system_viewer(path: Path | str) -> bool:
    """Ouvre un fichier avec l'application par défaut. Renvoie ``False`` si impossible.

    Les arguments sont passés en liste à ``subprocess`` plutôt qu'assemblés en
    ligne de commande, pour que les espaces et apostrophes des chemins ne posent
    pas de problème.
    """
    import platform
    import subprocess

    path = Path(path)
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", str(path)], check=True)
        elif system == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif system == "Linux":
            subprocess.run(["xdg-open", str(path)], check=True)
        else:
            info("plateforme %s non reconnue, ouverture manuelle nécessaire", system)
            return False
    except (OSError, subprocess.CalledProcessError) as exc:
        info("ouverture automatique impossible (%s)", exc)
        return False
    return True
