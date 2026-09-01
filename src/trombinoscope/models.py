"""Structures de données partagées entre les modules.

Ce module ne dépend d'aucun autre module du paquet : c'est la base de la
hiérarchie d'imports ``models`` ← ``{color, detection, framing, roster}`` ←
``pipeline`` ← ``cli``.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

# --------------------------------------------------------------------------- #
# Géométrie
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Box:
    """Boîte englobante en pixels, origine en haut à gauche, bornes exclusives à droite/bas."""

    x0: int
    y0: int
    x1: int
    y1: int

    def __post_init__(self) -> None:
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError(f"boîte dégénérée : {self}")

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    @property
    def area(self) -> int:
        return self.width * self.height

    def scaled(self, factor: float) -> "Box":
        """Homothétie autour du centre, arrondie au pixel."""
        cx, cy = self.center
        half_w = self.width * factor / 2
        half_h = self.height * factor / 2
        return Box(round(cx - half_w), round(cy - half_h), round(cx + half_w), round(cy + half_h))

    def clipped(self, width: int, height: int) -> "Box":
        """Intersection avec le rectangle image ``(0, 0, width, height)``."""
        return Box(
            max(0, min(self.x0, width - 1)),
            max(0, min(self.y0, height - 1)),
            min(width, max(self.x1, 1)),
            min(height, max(self.y1, 1)),
        )

    @classmethod
    def from_xywh(cls, x: float, y: float, w: float, h: float) -> "Box":
        return cls(round(x), round(y), round(x + w), round(y + h))


@dataclass(frozen=True, slots=True)
class Landmarks:
    """Cinq points caractéristiques renvoyés par YuNet, en pixels image.

    Les côtés *droite* / *gauche* sont ceux de l'image, pas ceux du sujet.
    """

    right_eye: tuple[float, float]
    left_eye: tuple[float, float]
    nose: tuple[float, float]
    right_mouth: tuple[float, float]
    left_mouth: tuple[float, float]

    @property
    def eye_angle_deg(self) -> float:
        """Inclinaison de la ligne des yeux, en degrés, positive dans le sens horaire."""
        import math

        dx = self.left_eye[0] - self.right_eye[0]
        dy = self.left_eye[1] - self.right_eye[1]
        return math.degrees(math.atan2(dy, dx))

    @property
    def eye_center(self) -> tuple[float, float]:
        return (
            (self.right_eye[0] + self.left_eye[0]) / 2,
            (self.right_eye[1] + self.left_eye[1]) / 2,
        )


@dataclass(frozen=True, slots=True)
class Detection:
    """Un visage détecté, avec son score de confiance."""

    box: Box
    confidence: float
    landmarks: Landmarks | None = None


# --------------------------------------------------------------------------- #
# Personnes
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class Person:
    """Une personne du trombinoscope.

    Volontairement générique : plutôt que des champs métier figés, deux listes
    libres d'étiquettes, que l'appelant remplit comme il veut.

    ``tags`` s'écrit dans la gouttière gauche de la photo, ``groups`` dans la
    gouttière droite, et ``badge`` déclenche l'étoile en coin.
    """

    last_name: str
    first_name: str = ""
    tags: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()
    badge: bool = False

    #: Photo source, renseignée par l'appariement dossier ↔ liste.
    source_photo: Path | None = None
    #: Portrait recadré écrit sur disque, utilisé par la mise en page PDF.
    portrait: Path | None = None
    #: Détections retenues pour cette personne (diagnostic).
    detections: tuple[Detection, ...] = ()

    @property
    def display_name(self) -> str:
        return f"{self.last_name} {self.first_name}".strip()

    def with_portrait(self, path: Path) -> "Person":
        return replace(self, portrait=path)


# --------------------------------------------------------------------------- #
# Configurations
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class FramingConfig:
    """Paramètres de recadrage du portrait autour du visage détecté.

    ``face_ratio`` est la fraction de la largeur du cadre qu'occupe la boîte du
    visage : c'est ce qui rend les portraits comparables entre eux, quelle que
    soit la distance de prise de vue.
    """

    #: hauteur / largeur du portrait final
    aspect_ratio: float = 4 / 3
    #: largeur du visage / largeur du cadre
    face_ratio: float = 0.55
    #: position verticale du centre du visage dans le cadre, 0 = haut, 1 = bas
    face_y: float = 0.5
    #: largeur du portrait produit, en pixels
    width: int = 300
    #: redresse l'image pour horizontaliser la ligne des yeux (nécessite les landmarks)
    align_eyes: bool = False
    #: couleur de remplissage BGR quand le cadre déborde de la photo source
    fill: tuple[int, int, int] = (255, 255, 255)

    def __post_init__(self) -> None:
        if not 0 < self.face_ratio <= 1:
            raise ValueError("face_ratio doit être dans ]0, 1]")
        if not 0 <= self.face_y <= 1:
            raise ValueError("face_y doit être dans [0, 1]")
        if self.width <= 0:
            raise ValueError("width doit être strictement positif")
        if self.aspect_ratio <= 0:
            raise ValueError("aspect_ratio doit être strictement positif")

    @property
    def height(self) -> int:
        return round(self.width * self.aspect_ratio)


@dataclass(frozen=True, slots=True)
class ColorConfig:
    """Paramètres d'homogénéisation colorimétrique.

    Voir ``docs/color.md`` pour le détail des méthodes et leurs limites.
    """

    #: "none", "grayworld", "shades-of-gray", "white-patch"
    white_balance: str = "shades-of-gray"
    #: exposant de la norme de Minkowski pour "shades-of-gray" (1 = gray world, ∞ = max-RGB)
    minkowski_p: float = 6.0
    #: percentile utilisé par "white-patch", en % (100 = max brut, sensible aux spéculaires)
    white_patch_percentile: float = 97.0
    #: Étale l'histogramme de luminance en écrêtant ce pourcentage de pixels à
    #: chaque extrémité. ``None`` — le défaut — le désactive : mesuré sur un lot
    #: hétérogène, l'étalement *dégrade* la cohérence au lieu de l'améliorer
    #: (dispersion chromatique 0,0196 sans, 0,0256 avec), parce qu'il cale la plage
    #: sur le seul visage et brûle donc les fonds. La normalisation gamma de
    #: :class:`~trombinoscope.color.LuminanceMatcher` fait le même travail
    #: d'exposition sans écrêter. Voir ``docs/color.md``.
    auto_levels_clip: float | None = None
    #: aligne l'illuminant **et** la luminance de chaque portrait sur la médiane du
    #: lot, au lieu de corriger chaque photo isolément vers le gris neutre
    harmonize_batch: bool = True
    #: n'estime l'illuminant que sur la zone du visage plutôt que sur toute l'image
    estimate_on_face: bool = True
    #: bride le gain appliqué à chaque canal, pour éviter les corrections aberrantes
    max_gain: float = 2.0
    #: Intensité de la correction de teinte, entre 0 (aucune) et 1 (complète).
    #: Les valeurs intermédiaires interpolent géométriquement vers l'identité.
    #: Utile sur les lots contenant des photos quasi monochromes, dont l'illuminant
    #: est mal estimé et que la correction pleine puissance colore à tort.
    strength: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError("strength doit être dans [0, 1]")
        if self.max_gain < 1.0:
            raise ValueError("max_gain doit être >= 1")


@dataclass(frozen=True, slots=True)
class GridConfig:
    """Mise en page de la grille PDF.

    Les longueurs sont en millimètres, sauf ``line_skip`` et ``font_size`` (en
    points PostScript) et ``title_top`` / ``title_skip`` (en hauteurs de ligne).
    """

    columns: int = 5
    #: fraction de la largeur de colonne laissée vide autour de chaque photo
    column_padding: float = 0.2
    #: espace vertical entre deux lignes, en points PostScript
    line_skip: float = 8.0
    margin_left: float = 8.0
    margin_right: float = 8.0
    margin_top: float = 5.0
    margin_bottom: float = 5.0
    #: Taille du bloc nom/prénom sous chaque photo, en points PostScript.
    #: 10 pt est la taille que ce bloc avait de fait en 0.1.0, où l'option était
    #: sans effet ; la garder en défaut évite de déplacer les rendus existants.
    font_size: float = 10.0
    #: Interligne de ce bloc, en points. ``None`` prend ``font_size * 1.25``.
    #: À augmenter pour aérer, à réduire pour serrer deux lignes très proches.
    name_leading: float | None = None
    #: Réduit la police des **seuls** noms trop larges pour leur colonne, afin
    #: qu'ils tiennent sur une ligne. Les autres gardent ``font_size``, si bien
    #: que la planche reste homogène là où elle peut l'être.
    shrink_long_names: bool = True
    #: Plancher de cette réduction, en fraction de ``font_size``. En dessous, on
    #: cesse de réduire et le nom repasse à la ligne : un nom illisible serait
    #: pire qu'un nom sur deux lignes.
    name_shrink_floor: float = 0.6
    #: Blanc entre le bas du titre et la première rangée, en **hauteurs de ligne**
    #: — c'est-à-dire en multiples de ``font_size``, et non en millimètres comme
    #: les marges. Ainsi l'espacement suit la taille du texte quand on la change.
    title_skip: float = 1.0
    #: Blanc au-dessus du titre, en hauteurs de ligne.
    title_top: float = 0.0
    landscape: bool = False
    #: centre la dernière ligne quand elle est incomplète
    center_last_row: bool = True
    show_tags: bool = True
    show_groups: bool = True
    show_badges: bool = True
    show_logo: bool = True
    #: Coin où placer le logo : ``"top-right"``, ``"bottom-right"``, ``"top-left"``
    #: ou ``"bottom-left"``.
    logo_position: str = "top-right"
    #: Largeur du logo, en millimètres.
    logo_width: float = 30.0
    #: Marge entre le logo et le bord de la zone de contenu, en millimètres.
    logo_margin: float = 5.0
    #: Décalage fin du logo après positionnement dans son coin, en millimètres :
    #: ``x`` vers la droite, ``y`` vers le haut. Sert à le faire mordre sur la
    #: marge, ce que les marges ordinaires ne permettent pas.
    logo_offset: tuple[float, float] = (0.0, 0.0)
    #: Décalage de l'étoile vers l'intérieur de la photo, en millimètres. À ``0``
    #: elle est centrée sur le coin et déborde donc de moitié.
    badge_inset: float = 0.0
    #: Rayon de l'étoile, en millimètres. La pastille blanche qui la porte fait
    #: une fois et demie ce rayon.
    badge_radius: float = 1.0
    annotation_font: str = "Courier"
    #: taille des annotations pivotées, en points
    annotation_font_size: float = 4.8
    #: Répartition des annotations pivotées autour de la photo.
    #: ``"gutters"`` place ``tags`` à gauche et ``groups`` à droite.
    #: ``"left"`` met les deux séries dans la gouttière gauche, ``tags`` partant du
    #: bas et ``groups`` calé sur le haut — plus compact, mais les deux se
    #: chevauchent si elles sont longues.
    annotation_layout: str = "gutters"
    #: Coin de la photo où se place l'étoile : ``"top-right"``, ``"bottom-right"``,
    #: ``"top-left"`` ou ``"bottom-left"``.
    badge_corner: str = "top-right"

    def __post_init__(self) -> None:
        if self.columns < 1:
            raise ValueError("columns doit être >= 1")
        if not 0 <= self.column_padding < 1:
            raise ValueError("column_padding doit être dans [0, 1[")
        if self.badge_radius <= 0:
            raise ValueError("badge_radius doit être strictement positif")
        if self.font_size <= 0:
            raise ValueError("font_size doit être strictement positif")
        if self.name_leading is not None and self.name_leading <= 0:
            raise ValueError("name_leading doit être strictement positif")
        if not 0 < self.name_shrink_floor <= 1:
            raise ValueError("name_shrink_floor doit être dans ]0, 1]")
        if self.annotation_layout not in ("gutters", "left"):
            raise ValueError("annotation_layout doit valoir 'gutters' ou 'left'")
        corners = ("top-right", "bottom-right", "top-left", "bottom-left")
        if self.badge_corner not in corners:
            raise ValueError(f"badge_corner doit être l'un de {corners}")
        if self.logo_position not in corners:
            raise ValueError(f"logo_position doit être l'un de {corners}")


@dataclass(slots=True)
class BuildReport:
    """Ce qui s'est passé pendant un ``build``, pour que l'appelant puisse décider."""

    people: list[Person] = field(default_factory=list)
    photos: list[Path] = field(default_factory=list)
    unmatched_people: list[str] = field(default_factory=list)
    unmatched_photos: list[Path] = field(default_factory=list)
    no_face: list[Path] = field(default_factory=list)
    multiple_faces: list[Path] = field(default_factory=list)
    pdf: Path | None = None

    @property
    def ok(self) -> bool:
        return not (self.unmatched_people or self.unmatched_photos or self.no_face)

    def summary(self) -> str:
        parts = [f"{len(self.people)} personne(s)", f"{len(self.photos)} photo(s)"]
        if self.no_face:
            parts.append(f"{len(self.no_face)} sans visage détecté")
        if self.multiple_faces:
            parts.append(f"{len(self.multiple_faces)} avec plusieurs visages")
        if self.unmatched_people:
            parts.append(f"{len(self.unmatched_people)} personne(s) sans photo")
        if self.unmatched_photos:
            parts.append(f"{len(self.unmatched_photos)} photo(s) sans personne")
        return ", ".join(parts)


def positional_match(
    people: Sequence[Person], photos: Sequence[Path], absent: Sequence[str] = ()
) -> tuple[list[tuple[Person, Path]], list[str], list[Path]]:
    """Apparie personnes et photos par position, en sautant les absents.

    C'est le cœur de l'ergonomie de l'outil : les photos triées par nom de fichier
    sont supposées suivre l'ordre de la liste. L'appariement est calculé en une
    fois, indépendamment de la détection, pour qu'aucun traitement ultérieur ne
    puisse le décaler.

    Renvoie les paires, les noms sans photo, et les photos sans personne.
    """
    absent_set = {name.casefold() for name in absent}
    expecting = [p for p in people if p.last_name.casefold() not in absent_set]

    pairs = list(zip(expecting, photos, strict=False))
    leftover_people = [p.last_name for p in expecting[len(pairs) :]]
    leftover_photos = list(photos[len(pairs) :])
    return pairs, leftover_people, leftover_photos
