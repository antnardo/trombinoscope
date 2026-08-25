"""Mise en page de la grille de portraits.

La pagination est séparée du dessin. :class:`GridPaginator` ne manipule que des
entiers, ne dépend pas de ReportLab et se teste donc directement ;
:class:`TrombiRenderer` ne fait que traduire ses cellules en coordonnées.

Chaque personne est placée une fois pour toutes dans une :class:`Cell`, qui porte
sa ligne et sa colonne. Photo, nom et annotations lisent la même cellule, ce qui
garantit qu'ils restent solidaires quelle que soit la forme de la grille — y
compris sur une dernière ligne centrée, où les colonnes occupées ne sont ni
contiguës ni en nombre égal à ``columns``.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from reportlab.lib.units import mm

from trombinoscope.log import debug, info
from trombinoscope.models import GridConfig, Person
from trombinoscope.pdf.canvas import PdfCanvas, fit_width, join_annotations


@dataclass(frozen=True, slots=True)
class Cell:
    """Une personne, à une position ``(row, column)`` de la grille d'une page."""

    person: Person
    row: int
    column: int


@dataclass(slots=True)
class PageLayout:
    """Le contenu d'une page."""

    number: int
    rows: int
    cells: list[Cell] = field(default_factory=list)


def corner_parts(corner: str) -> tuple[str, str]:
    """Découpe ``"top-right"`` en ``("top", "right")``."""
    vertical, horizontal = corner.split("-")
    return vertical, horizontal


def centered_columns(count: int, columns: int) -> list[int]:
    """Indices de colonne pour ``count`` éléments centrés sur ``columns`` colonnes.

    Quand ``count`` et ``columns`` ont la même parité, l'écart est pair et un bloc
    contigu tombe exactement au centre.

    Quand ``columns`` est impair et ``count`` pair, aucun bloc contigu n'est
    centré ; on scinde alors le groupe en deux moitiés de part et d'autre de la
    colonne médiane, qui reste vide. Cinq colonnes et deux photos donnent ainsi
    ``. P . P .`` plutôt que ``. P P . .``.

    Dans le dernier cas — ``columns`` pair et ``count`` impair — aucune disposition
    symétrique n'existe : on centre au mieux, à une demi-colonne près.
    """
    if count >= columns:
        return list(range(columns))
    gap = columns - count
    left = gap // 2
    if columns % 2 == 1 and count % 2 == 0:
        half = count // 2
        return [left + i for i in range(half)] + [left + half + 1 + i for i in range(half)]
    return [left + i for i in range(count)]


class GridPaginator:
    """Répartit les personnes en pages, lignes et colonnes.

    Logique pure : aucune dépendance à ReportLab, aucun effet de bord.
    """

    def __init__(self, config: GridConfig | None = None) -> None:
        self._config = config or GridConfig()

    def paginate(self, people: Sequence[Person], rows_per_page: int) -> list[PageLayout]:
        """Découpe ``people`` en pages d'au plus ``rows_per_page`` lignes."""
        if rows_per_page < 1:
            raise ValueError(
                "aucune ligne ne tient dans la hauteur disponible : réduisez la taille "
                "des photos (columns plus grand) ou les marges"
            )
        columns = self._config.columns
        per_page = rows_per_page * columns

        pages: list[PageLayout] = []
        for page_number, start in enumerate(range(0, len(people), per_page), start=1):
            chunk = people[start : start + per_page]
            pages.append(self._lay_out(chunk, page_number, columns))
        if not pages:
            pages.append(PageLayout(number=1, rows=0))
        return pages

    def _lay_out(self, chunk: Sequence[Person], page_number: int, columns: int) -> PageLayout:
        rows = (len(chunk) + columns - 1) // columns
        page = PageLayout(number=page_number, rows=rows)
        for row in range(rows):
            slice_ = chunk[row * columns : (row + 1) * columns]
            is_last = row == rows - 1
            positions = (
                centered_columns(len(slice_), columns)
                if is_last and self._config.center_last_row
                else list(range(len(slice_)))
            )
            for person, column in zip(slice_, positions, strict=True):
                page.cells.append(Cell(person=person, row=row, column=column))
        return page


class TrombiRenderer:
    """Dessine les pages calculées par :class:`GridPaginator`."""

    def __init__(
        self,
        config: GridConfig | None = None,
        *,
        placeholder: Path | None = None,
        logo: Path | None = None,
    ) -> None:
        self._config = config or GridConfig()
        self._placeholder = placeholder or default_placeholder()
        self._logo = logo

    def render(
        self,
        people: Sequence[Person],
        path: Path | str,
        *,
        title: str = "",
        subtitle: str = "",
    ) -> Path:
        config = self._config
        canvas = PdfCanvas(
            path,
            margin_left=config.margin_left,
            margin_right=config.margin_right,
            margin_top=config.margin_top,
            margin_bottom=config.margin_bottom,
            font_size=config.font_size,
            landscape=config.landscape,
        )
        canvas.set_metadata(title=title or "Trombinoscope", subject=subtitle)
        canvas.set_footer(f"Version du {date.today():%d/%m/%Y}")

        photo_width = canvas.content_width / config.columns * (1 - config.column_padding)
        photo_height = photo_width * self._portrait_ratio(people)
        name_height = canvas.paragraph_height("<b>X</b><br/>Y", "Noms", photo_width)
        row_height = photo_height + name_height + config.line_skip

        grid_top = self._draw_header(canvas, title, subtitle)
        available = grid_top - canvas.bottom
        rows_per_page = int(available // row_height)
        info(
            "photo %.1f × %.1f mm, %d ligne(s) par page",
            photo_width / mm,
            photo_height / mm,
            rows_per_page,
        )

        pages = GridPaginator(config).paginate(people, rows_per_page)
        for index, page in enumerate(pages):
            if index > 0:
                canvas.new_page()
                grid_top = self._draw_header(canvas, title, subtitle)
            self._draw_page(canvas, page, grid_top, photo_width, photo_height, row_height)

        result = canvas.save()
        info("PDF écrit : %s (%d page(s))", result, len(pages))
        return result

    # -- détails ------------------------------------------------------------ #

    def _portrait_ratio(self, people: Sequence[Person]) -> float:
        """Rapport hauteur/largeur lu sur le premier portrait disponible.

        Le lire plutôt que le supposer garde la mise en page et le recadrage
        d'accord quand l'appelant change ``FramingConfig.aspect_ratio`` sans
        toucher à la grille.
        """
        for person in people:
            if person.portrait and Path(person.portrait).exists():
                width, height = fit_width(person.portrait, 1.0)
                return height / width
        return 4 / 3

    def _draw_header(self, canvas: PdfCanvas, title: str, subtitle: str) -> float:
        config = self._config
        line = config.font_size
        cursor = canvas.top - config.title_top * line
        if title:
            cursor -= canvas.draw_paragraph(
                title, "Titre", x=canvas.left, y=cursor, width=canvas.content_width
            )
        if subtitle:
            cursor -= canvas.draw_paragraph(
                subtitle, "Centered", x=canvas.left, y=cursor, width=canvas.content_width
            )
        if config.show_logo and self._logo is not None and Path(self._logo).exists():
            self._draw_logo(canvas)
        return cursor - config.title_skip * line

    def _draw_logo(self, canvas: PdfCanvas) -> None:
        """Place le logo dans l'un des quatre coins de la zone de contenu."""
        config = self._config
        width, height = fit_width(self._logo, config.logo_width * mm)
        margin = config.logo_margin * mm
        offset_x, offset_y = (value * mm for value in config.logo_offset)
        vertical, horizontal = corner_parts(config.logo_position)
        x = canvas.right - width - margin if horizontal == "right" else canvas.left + margin
        y = canvas.top - height if vertical == "top" else canvas.bottom
        canvas.draw_image(self._logo, x=x + offset_x, y=y + offset_y, width=width, height=height)

    def _draw_page(
        self,
        canvas: PdfCanvas,
        page: PageLayout,
        grid_top: float,
        photo_width: float,
        photo_height: float,
        row_height: float,
    ) -> None:
        config = self._config
        column_width = canvas.content_width / config.columns

        for cell in page.cells:
            center_x = canvas.left + (cell.column + 0.5) * column_width
            photo_left = center_x - photo_width / 2
            photo_top = grid_top - cell.row * row_height
            photo_bottom = photo_top - photo_height

            source = cell.person.portrait
            image = source if source and Path(source).exists() else self._placeholder
            if source is None or not Path(source).exists():
                debug("pas de portrait pour %s, image de remplacement", cell.person.last_name)
            canvas.draw_image(
                image, x=photo_left, y=photo_bottom, width=photo_width, height=photo_height
            )

            canvas.draw_paragraph(
                f"<b>{_escape(cell.person.last_name)}</b><br/>{_escape(cell.person.first_name)}",
                "Noms",
                x=photo_left,
                y=photo_bottom - 1,
                width=photo_width,
            )

            self._draw_annotations(
                canvas, cell.person, photo_left, photo_bottom, photo_width, photo_height
            )

    def _draw_annotations(
        self,
        canvas: PdfCanvas,
        person: Person,
        photo_left: float,
        photo_bottom: float,
        photo_width: float,
        photo_height: float,
    ) -> None:
        config = self._config
        font, size = config.annotation_font, config.annotation_font_size
        gutter = 0.6 * mm
        left_x = photo_left - gutter
        right_x = photo_left + photo_width + gutter + size

        if config.show_tags and person.tags:
            # Gouttière gauche, texte lu de bas en haut à partir du bas de la photo.
            canvas.draw_rotated_text(
                join_annotations(person.tags),
                x=left_x,
                y=photo_bottom,
                font=font,
                size=size,
            )

        if config.show_groups and person.groups:
            # En disposition "left", les groupes partagent la gouttière gauche mais
            # sont calés sur le haut de la photo, donc écrits à l'envers l'un de
            # l'autre ; en "gutters" ils occupent la gouttière droite.
            legacy = config.annotation_layout == "left"
            canvas.draw_rotated_text(
                join_annotations(person.groups),
                x=left_x if legacy else right_x,
                y=photo_bottom + photo_height if legacy else photo_bottom,
                font=font,
                size=size,
                anchor="end" if legacy else "start",
            )

        if config.show_badges and person.badge:
            # À inset nul, l'étoile est centrée sur le coin de la photo et déborde
            # donc de moitié — c'est voulu, elle se lit comme une pastille posée.
            inset = config.badge_inset * mm
            vertical, horizontal = corner_parts(config.badge_corner)
            canvas.draw_star(
                photo_left + (photo_width - inset if horizontal == "right" else inset),
                photo_bottom + (photo_height - inset if vertical == "top" else inset),
                start_angle=1.5708,
            )


def _escape(text: str) -> str:
    """Échappe les caractères actifs du mini-langage de balisage de ReportLab.

    Sans cela, un nom contenant « & » ou « < » ferait échouer le rendu.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def default_placeholder() -> Path:
    """Silhouette neutre utilisée quand une personne n'a pas de portrait."""
    from importlib.resources import files

    return Path(str(files("trombinoscope").joinpath("assets", "placeholder.png")))


def render_pdf(
    people: Sequence[Person],
    path: Path | str,
    *,
    title: str = "",
    subtitle: str = "",
    config: GridConfig | None = None,
    logo: Path | None = None,
) -> Path:
    """Raccourci sur :meth:`TrombiRenderer.render`."""
    return TrombiRenderer(config, logo=logo).render(people, path, title=title, subtitle=subtitle)
