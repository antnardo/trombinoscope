"""Orchestration : dossier de photos + liste de personnes → PDF.

Le traitement se fait en deux passes, ce qui est imposé par l'harmonisation
colorimétrique : la référence du lot n'est connue qu'une fois toutes les photos
mesurées. La passe 1 détecte et recadre, la passe 2 corrige et écrit.

L'appariement personnes ↔ photos est entièrement résolu **avant** la première
détection. Un échec de détection ne peut donc pas décaler les personnes
suivantes : il produit un portrait non recadré et une entrée dans le rapport.

Le détourage impose sa propre contrainte d'ordre, moins évidente : le masque est
calculé en passe 1 sur la photo d'origine — c'est là que le réseau est le plus
juste, et c'est la seule échelle où les seuils du garde-fou ont un sens — mais il
n'est **appliqué qu'en passe 2, après la correction couleur**. Composer d'abord
remplirait le fond d'un aplat neutre, que l'estimateur d'illuminant lirait comme
une scène déjà équilibrée : la correction couleur ne ferait plus rien.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from trombinoscope.color import BatchColorHarmonizer
from trombinoscope.detection import FaceDetector, build_detector, pick_detection
from trombinoscope.framing import PortraitFramer
from trombinoscope.imageio import (
    ImageReadError,
    draw_detections,
    find_images,
    read_image,
    write_image,
)
from trombinoscope.log import info, warning
from trombinoscope.models import (
    Box,
    BuildReport,
    ColorConfig,
    FramingConfig,
    GridConfig,
    Person,
    SegmentationConfig,
    positional_match,
)
from trombinoscope.pdf.grid import TrombiRenderer
from trombinoscope.roster import load_roster
from trombinoscope.segmentation import BackgroundReplacer, Segmenter

__all__ = [
    "BuildOptions",
    "TrombinoscopeBuilder",
    "build_trombinoscope",
]


@dataclass(slots=True)
class BuildOptions:
    """Tout ce qui pilote un ``build``, en un seul objet."""

    title: str = "Trombinoscope"
    subtitle: str = ""
    #: Noms attendus dans la liste mais sans photo. Comparaison insensible à la casse.
    absent: tuple[str, ...] = ()
    #: ``{nom: index}`` — index du visage à retenir quand la photo en contient
    #: plusieurs, ``-1`` pour n'en retenir aucun et garder la photo entière.
    face_choice: dict[str, int] = field(default_factory=dict)
    framing: FramingConfig = field(default_factory=FramingConfig)
    color: ColorConfig = field(default_factory=ColorConfig)
    grid: GridConfig = field(default_factory=GridConfig)
    segmentation: SegmentationConfig = field(default_factory=SegmentationConfig)
    detector_backend: str = "yunet"
    confidence: float = 0.6
    logo: Path | None = None
    #: Dossier où écrire les images annotées de diagnostic. ``None`` pour ne rien écrire.
    debug_dir: Path | None = None


@dataclass(slots=True)
class _Pending:
    """État intermédiaire d'une personne entre les deux passes."""

    person: Person
    photo: Path
    portrait: np.ndarray
    face_box: Box | None
    #: Masque de détourage déjà recadré, ou ``None`` si le fond est conservé.
    mask: np.ndarray | None = None


class TrombinoscopeBuilder:
    """Assemble le trombinoscope. Responsabilité unique : enchaîner les étapes.

    Chaque étape est déléguée à une classe dédiée — détection, cadrage, couleur,
    rendu — qui reste utilisable seule. Détecteur et segmenteur sont injectables,
    ce qui permet de brancher un autre modèle ou un bouchon de test.
    """

    def __init__(
        self,
        options: BuildOptions | None = None,
        *,
        detector: FaceDetector | None = None,
        segmenter: Segmenter | None = None,
    ):
        self._options = options or BuildOptions()
        self._detector = detector or build_detector(
            self._options.detector_backend, confidence=self._options.confidence
        )
        self._framer = PortraitFramer(self._options.framing)
        self._harmonizer = BatchColorHarmonizer(self._options.color)
        segmentation = self._options.segmentation
        self._replacer = (
            BackgroundReplacer(segmentation, segmenter=segmenter) if segmentation.enabled else None
        )
        # Le masque subit exactement la géométrie du portrait — recadrage *et*
        # rotation de redressement — donc le même recadreur, au remplissage près :
        # ce qui déborde de la photo est du fond, pas du sujet.
        self._mask_framer = PortraitFramer(replace(self._options.framing, fill=(0, 0, 0)))

    @property
    def options(self) -> BuildOptions:
        return self._options

    # -- API principale ----------------------------------------------------- #

    def build(
        self,
        photo_dir: Path | str,
        roster: Path | str | Sequence[Person],
        output: Path | str,
        *,
        portrait_dir: Path | str | None = None,
    ) -> BuildReport:
        """Produit le PDF et renvoie un rapport de ce qui s'est passé."""
        photo_dir = Path(photo_dir)
        output = Path(output)
        people = list(roster) if not isinstance(roster, str | Path) else load_roster(roster)
        photos = find_images(photo_dir)
        portrait_dir = Path(portrait_dir) if portrait_dir else photo_dir / "portraits"

        pairs, unmatched_people, unmatched_photos = positional_match(
            people, photos, self._options.absent
        )
        report = BuildReport(
            people=people,
            photos=photos,
            unmatched_people=unmatched_people,
            unmatched_photos=unmatched_photos,
        )
        if unmatched_people:
            warning(
                "%d personne(s) sans photo : %s", len(unmatched_people), ", ".join(unmatched_people)
            )
        if unmatched_photos:
            warning(
                "%d photo(s) en trop : %s",
                len(unmatched_photos),
                ", ".join(p.name for p in unmatched_photos),
            )

        pending = self._first_pass(pairs, report)
        self._second_pass(pending, portrait_dir)

        report.pdf = TrombiRenderer(self._options.grid, logo=self._options.logo).render(
            people,
            output,
            title=self._options.title,
            subtitle=self._options.subtitle,
        )
        info("terminé — %s", report.summary())
        return report

    # -- passes ------------------------------------------------------------- #

    def _first_pass(self, pairs, report: BuildReport) -> list[_Pending]:
        """Détecte, recadre en mémoire, et mesure la couleur de chaque portrait."""
        pending: list[_Pending] = []
        for person, photo in pairs:
            try:
                image = read_image(photo)
            except (OSError, ImageReadError) as exc:
                warning("%s illisible (%s), ignorée", photo.name, exc)
                report.no_face.append(photo)
                continue

            detections = self._detector.detect(image)
            person.source_photo = photo
            person.detections = tuple(detections)

            if len(detections) > 1:
                report.multiple_faces.append(photo)
                warning(
                    "%d visages sur %s (%s) — index retenu : %d",
                    len(detections),
                    photo.name,
                    person.last_name,
                    self._options.face_choice.get(person.last_name, 0),
                )
                self._write_debug(photo, image, detections)
            elif not detections:
                report.no_face.append(photo)
                warning(
                    "aucun visage sur %s (%s) — photo conservée sans recadrage",
                    photo.name,
                    person.last_name,
                )

            chosen = pick_detection(detections, self._options.face_choice.get(person.last_name, 0))
            portrait = self._framer.frame(image, chosen)
            face_box = self._framer.framed_box(image, chosen)
            # Mesure faite sur le portrait au fond intact : voir la docstring du
            # module. Le masque, lui, est calculé sur la photo d'origine.
            self._harmonizer.measure(portrait, face_box)
            pending.append(
                _Pending(
                    person=person,
                    photo=photo,
                    portrait=portrait,
                    face_box=face_box,
                    mask=self._mask_for(image, chosen, photo, report),
                )
            )
        return pending

    def _mask_for(self, image: np.ndarray, chosen, photo: Path, report: BuildReport):
        """Masque de détourage recadré, ou ``None`` s'il faut garder le fond.

        Le garde-fou décide sur la photo d'origine, à la résolution où ses seuils
        ont été calibrés, et avant tout recadrage qui fausserait la surface
        d'avant-plan comme la détection d'un sujet coupé.
        """
        if self._replacer is None:
            return None
        full, quality = self._replacer.compute(image, chosen.box if chosen else None)
        if not quality.ok:
            report.background_kept.append(photo)
            warning(
                "fond conservé sur %s : %s (%s)", photo.name, quality.reason, quality.describe()
            )
            return None
        as_image = np.repeat((full * 255).astype(np.uint8)[:, :, np.newaxis], 3, axis=2)
        return self._mask_framer.frame(as_image, chosen)[:, :, 0].astype(np.float32) / 255.0

    def _second_pass(self, pending: Sequence[_Pending], portrait_dir: Path) -> None:
        """Applique la correction calée sur le lot, puis écrit les portraits."""
        portrait_dir.mkdir(parents=True, exist_ok=True)
        reference = self._harmonizer.reference_illuminant
        if reference is not None:
            info("illuminant de référence du lot : B=%.3f G=%.3f R=%.3f", *reference)

        for item in pending:
            corrected = self._harmonizer.transform(item.portrait, item.face_box)
            if item.mask is not None and self._replacer is not None:
                corrected = self._replacer.apply(corrected, item.mask)
            target = portrait_dir / f"{item.photo.stem}.portrait.jpg"
            write_image(target, corrected)
            item.person.portrait = target

    def _write_debug(self, photo: Path, image: np.ndarray, detections: Sequence) -> None:
        if self._options.debug_dir is None:
            return
        annotated = draw_detections(image, detections)
        write_image(Path(self._options.debug_dir) / f"{photo.stem}.detections.jpg", annotated)


def build_trombinoscope(
    photo_dir: Path | str,
    roster: Path | str | Sequence[Person],
    output: Path | str,
    **kwargs,
) -> BuildReport:
    """Raccourci : construit les options depuis des mots-clés et lance le build.

    Les clés inconnues de :class:`BuildOptions` lèvent une ``TypeError`` explicite
    plutôt que d'être ignorées sans rien dire.
    """
    portrait_dir = kwargs.pop("portrait_dir", None)
    options = BuildOptions(**kwargs)
    return TrombinoscopeBuilder(options).build(photo_dir, roster, output, portrait_dir=portrait_dir)
