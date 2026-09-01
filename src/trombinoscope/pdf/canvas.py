"""Feuille de styles et primitives propres au trombinoscope.

La mise en page s'appuie sur :mod:`reportlab_layout`, qui apporte le curseur, les
ancrages typographiques et le texte pivoté. Ne reste ici que ce qui est
spécifique à ce document : trois styles, et l'étoile de badge — un polygone que
``ShapePainter`` ne couvre pas encore.

Le nom du module reste ``canvas`` pour que ``from trombinoscope.pdf.canvas import
styles`` continue de fonctionner dans les scripts existants.
"""

import math

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab_layout import make_stylesheet

__all__ = ["draw_star", "mm", "styles"]

#: Feuille de styles du document. Dérivée de celle de ``reportlab_layout``, à
#: laquelle s'ajoutent les trois styles propres au trombinoscope. Les appelants
#: peuvent y régler police et couleur ; la **taille** du bloc nom/prénom, elle,
#: se règle par ``GridConfig.font_size``, le rendu dérivant son propre style.
styles = make_stylesheet()

for style in (
    ParagraphStyle(name="Centered", parent=styles["Normal"], alignment=TA_CENTER),
    ParagraphStyle(name="Heading1Centered", parent=styles["Heading1"], alignment=TA_CENTER),
):
    if style.name not in styles:
        styles.add(style)

if "Titre" not in styles:
    styles.add(ParagraphStyle(name="Titre", parent=styles["Heading1Centered"]))
if "Noms" not in styles:
    styles.add(ParagraphStyle(name="Noms", parent=styles["Centered"]))
if "Pied" not in styles:
    styles.add(ParagraphStyle(name="Pied", parent=styles["Normal"], alignment=TA_RIGHT, fontSize=9))


def draw_star(
    canvas: Canvas,
    x: float,
    y: float,
    *,
    radius: float = 1.0 * mm,
    vertices: int = 5,
    leap: int = 2,
    start_angle: float = math.pi / 2,
) -> None:
    """Étoile pleine sur pastille blanche, centrée en ``(x, y)``.

    Le polygone est tracé en sautant ``leap`` sommets sur ``vertices`` : c'est ce
    qui donne les branches croisées d'une étoile à cinq pointes plutôt qu'un
    pentagone. La pastille blanche dessous garantit la lisibilité quelle que soit
    la photo, l'étoile étant posée à cheval sur son coin.
    """
    canvas.saveState()
    canvas.setFillColor(colors.white)
    canvas.setStrokeColor(colors.black)
    canvas.setLineWidth(0.4)
    canvas.circle(x, y, radius * 1.5, stroke=1, fill=1)

    canvas.setFillColor(colors.black)
    canvas.setLineJoin(1)
    path = canvas.beginPath()
    step = 2 * math.pi * leap / vertices
    angle = start_angle
    path.moveTo(x + radius * math.cos(angle), y + radius * math.sin(angle))
    for _ in range(vertices - 1):
        angle += step
        path.lineTo(x + radius * math.cos(angle), y + radius * math.sin(angle))
    path.close()
    canvas.drawPath(path, stroke=1, fill=1, fillMode=1)
    canvas.restoreState()
