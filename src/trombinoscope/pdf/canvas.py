"""Feuille de styles du document.

La mise en page s'appuie entièrement sur :mod:`reportlab_layout` : curseur,
ancrages typographiques, texte pivoté, polygones. Ne reste ici que la feuille de
styles, dérivée de la sienne et complétée des trois styles propres au
trombinoscope.

Le nom du module reste ``canvas`` pour que ``from trombinoscope.pdf.canvas import
styles`` continue de fonctionner dans les scripts existants.
"""

from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab_layout import make_stylesheet

__all__ = ["mm", "styles"]

#: Feuille de styles du document. Les appelants peuvent y régler police et
#: couleur ; la **taille** du bloc nom/prénom, elle, se règle par
#: ``GridConfig.font_size``, le rendu dérivant son propre style.
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
