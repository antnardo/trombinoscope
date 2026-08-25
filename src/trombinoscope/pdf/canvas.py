"""Enveloppe minimale autour du canevas ReportLab.

Ne couvre que ce dont la mise en page du trombinoscope a besoin : titre, pied de
page, images, texte droit et pivoté, étoile.

Les coordonnées exposées ici sont celles de ReportLab : origine en bas à gauche,
unité le point PostScript (1/72 pouce). Les marges de configuration sont en
millimètres et converties une seule fois, à la construction.
"""

from collections.abc import Sequence
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Paragraph

__all__ = ["PdfCanvas", "mm", "styles"]

styles = getSampleStyleSheet()
for style in (
    ParagraphStyle(name="Right", parent=styles["Normal"], alignment=TA_RIGHT),
    ParagraphStyle(name="Justify", parent=styles["Normal"], alignment=TA_JUSTIFY),
    ParagraphStyle(name="Centered", parent=styles["Normal"], alignment=TA_CENTER),
    ParagraphStyle(name="Footer", parent=styles["Normal"], alignment=TA_RIGHT, fontSize=9),
    ParagraphStyle(name="Heading1Centered", parent=styles["Heading1"], alignment=TA_CENTER),
):
    if style.name not in styles:
        styles.add(style)

styles.add(ParagraphStyle(name="Titre", parent=styles["Heading1Centered"]))
styles.add(ParagraphStyle(name="Noms", parent=styles["Centered"], leading=11))


class PdfCanvas:
    """Canevas paginé avec marges et pied de page.

    Il n'y a pas de curseur vertical implicite : chaque méthode de dessin reçoit
    ses coordonnées, ce qui rend la position de chaque élément traçable depuis
    l'appelant.
    """

    def __init__(
        self,
        path: Path | str,
        *,
        margin_left: float = 8.0,
        margin_right: float = 8.0,
        margin_top: float = 5.0,
        margin_bottom: float = 5.0,
        font_size: float = 12.0,
        landscape: bool = False,
        page_size: tuple[float, float] | None = None,
    ) -> None:
        if page_size is None:
            page_size = (A4[1], A4[0]) if landscape else A4
        self.path = Path(path)
        self.page_width, self.page_height = page_size
        self.left = margin_left * mm
        self.right = self.page_width - margin_right * mm
        self.top = self.page_height - margin_top * mm
        self.bottom = margin_bottom * mm
        self.font_size = font_size
        self.page_number = 1

        self._canvas = rl_canvas.Canvas(str(self.path), pagesize=page_size)
        self._canvas.setFontSize(font_size)
        self._footer: str | None = None

    # -- géométrie ---------------------------------------------------------- #

    @property
    def content_width(self) -> float:
        return self.right - self.left

    @property
    def content_height(self) -> float:
        return self.top - self.bottom

    @property
    def raw(self) -> rl_canvas.Canvas:
        """Canevas ReportLab sous-jacent, pour les cas non couverts ici."""
        return self._canvas

    # -- métadonnées -------------------------------------------------------- #

    def set_metadata(self, *, title: str = "", author: str = "", subject: str = "") -> None:
        self._canvas.setTitle(title)
        self._canvas.setAuthor(author)
        self._canvas.setSubject(subject)

    def set_footer(self, text: str | None) -> None:
        self._footer = text

    # -- dessin ------------------------------------------------------------- #

    def draw_paragraph(
        self, text: str, style_name: str, *, x: float, y: float, width: float
    ) -> float:
        """Dessine un paragraphe dont le haut de bloc est à ``y``.

        Renvoie la hauteur **totale** occupée, ``spaceBefore`` et ``spaceAfter`` du
        style compris : c'est ce que consomme un flowable ReportLab, et ce qu'il
        faut retrancher au curseur pour enchaîner correctement. Les styles à espace
        nul — ``Noms``, ``Footer`` — se comportent comme avant.
        """
        paragraph = Paragraph(text, styles[style_name])
        _, height = paragraph.wrap(width, self.content_height)
        before = paragraph.getSpaceBefore()
        paragraph.drawOn(self._canvas, x, y - before - height)
        return before + height + paragraph.getSpaceAfter()

    def paragraph_height(self, text: str, style_name: str, width: float) -> float:
        _, height = Paragraph(text, styles[style_name]).wrap(width, self.content_height)
        return height

    def draw_image(
        self, path: Path | str, *, x: float, y: float, width: float, height: float
    ) -> None:
        """Dessine une image dont le coin *bas gauche* est à ``(x, y)``."""
        self._canvas.drawImage(
            str(path), x, y, width=width, height=height, preserveAspectRatio=False, mask="auto"
        )

    def draw_rotated_text(
        self,
        text: str,
        *,
        x: float,
        y: float,
        font: str,
        size: float,
        anchor: str = "start",
        color=colors.black,
    ) -> None:
        """Écrit ``text`` à la verticale, de bas en haut, ancré en ``(x, y)``.

        ``anchor`` vaut ``"start"`` (le texte part de ``y`` vers le haut) ou
        ``"end"`` (le texte se termine en ``y``).
        """
        self._canvas.saveState()
        self._canvas.setFont(font, size)
        self._canvas.setFillColor(color)
        self._canvas.rotate(90)
        if anchor == "end":
            self._canvas.drawRightString(y, -x, text)
        else:
            self._canvas.drawString(y, -x, text)
        self._canvas.restoreState()

    def text_width(self, text: str, font: str, size: float) -> float:
        return stringWidth(text, font, size)

    def draw_star(
        self,
        x: float,
        y: float,
        *,
        radius: float = 1.0 * mm,
        vertices: int = 5,
        leap: int = 2,
        start_angle: float = 0.0,
    ) -> None:
        """Étoile pleine sur pastille blanche, centrée en ``(x, y)``."""
        import math

        self._canvas.saveState()
        self._canvas.setFillColor(colors.white)
        self._canvas.setStrokeColor(colors.black)
        self._canvas.setLineWidth(0.4)
        self._canvas.circle(x, y, radius * 1.5, stroke=1, fill=1)

        self._canvas.setFillColor(colors.black)
        self._canvas.setLineJoin(1)
        path = self._canvas.beginPath()
        step = 2 * math.pi * leap / vertices
        angle = start_angle
        path.moveTo(x + radius * math.cos(angle), y + radius * math.sin(angle))
        for _ in range(vertices - 1):
            angle += step
            path.lineTo(x + radius * math.cos(angle), y + radius * math.sin(angle))
        path.close()
        self._canvas.drawPath(path, stroke=1, fill=1, fillMode=1)
        self._canvas.restoreState()

    # -- pagination --------------------------------------------------------- #

    def new_page(self) -> None:
        self._draw_footer()
        self._canvas.showPage()
        self._canvas.setFontSize(self.font_size)
        self.page_number += 1

    def save(self) -> Path:
        self._draw_footer()
        self._canvas.save()
        return self.path

    def _draw_footer(self) -> None:
        if not self._footer:
            return
        self.draw_paragraph(
            self._footer,
            "Footer",
            x=self.left,
            y=self.bottom,
            width=self.content_width,
        )


def image_size(path: Path | str) -> tuple[int, int]:
    """Dimensions en pixels d'un fichier image, sans le décoder entièrement."""
    from PIL import Image

    with Image.open(path) as handle:
        return handle.size


def fit_width(path: Path | str, width: float) -> tuple[float, float]:
    """Dimensions ``(largeur, hauteur)`` d'une image mise à ``width``, ratio conservé."""
    pixel_width, pixel_height = image_size(path)
    return width, width * pixel_height / pixel_width


def join_annotations(parts: Sequence[str]) -> str:
    """Assemble des étiquettes en une ligne, en ignorant les vides."""
    return ", ".join(part for part in parts if part)
