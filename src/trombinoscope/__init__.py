"""Génère un trombinoscope PDF depuis un dossier de photos et une liste de personnes.

Usage minimal :

    >>> from trombinoscope import build_trombinoscope
    >>> report = build_trombinoscope("photos/", "classe.csv", "trombi.pdf")
    >>> print(report.summary())

Ce module n'expose que l'API publique. Les modules internes restent importables
pour les usages avancés (utiliser le recadrage sans le PDF, la correction couleur
sans la détection…), mais leur signature peut changer entre versions mineures.

Aucun modèle n'est chargé à l'import : la première détection paie le chargement du
réseau, pas le simple ``import trombinoscope``.
"""

from trombinoscope.color import (
    AutoLevels,
    BatchColorHarmonizer,
    GrayWorldEstimator,
    LuminanceMatcher,
    ShadesOfGrayEstimator,
    WhiteBalancer,
    WhitePatchEstimator,
)
from trombinoscope.detection import (
    FaceDetector,
    HaarCascadeDetector,
    YuNetDetector,
    build_detector,
)
from trombinoscope.framing import PortraitFramer
from trombinoscope.imageio import find_images, open_with_system_viewer, read_image, write_image
from trombinoscope.log import configure, set_interactive
from trombinoscope.models import (
    Box,
    BuildReport,
    ColorConfig,
    Detection,
    FramingConfig,
    GridConfig,
    Landmarks,
    Person,
)
from trombinoscope.pdf.grid import GridPaginator, TrombiRenderer, render_pdf
from trombinoscope.pipeline import BuildOptions, TrombinoscopeBuilder, build_trombinoscope
from trombinoscope.roster import (
    RosterLoader,
    load_roster,
    load_sqlite,
    remove_accents,
    write_template,
)

__version__ = "0.1.1"

__all__ = [
    "AutoLevels",
    "BatchColorHarmonizer",
    "Box",
    "BuildOptions",
    "BuildReport",
    "ColorConfig",
    "Detection",
    "FaceDetector",
    "FramingConfig",
    "GrayWorldEstimator",
    "GridConfig",
    "GridPaginator",
    "HaarCascadeDetector",
    "Landmarks",
    "LuminanceMatcher",
    "Person",
    "PortraitFramer",
    "RosterLoader",
    "ShadesOfGrayEstimator",
    "TrombiRenderer",
    "TrombinoscopeBuilder",
    "WhiteBalancer",
    "WhitePatchEstimator",
    "YuNetDetector",
    "__version__",
    "build_detector",
    "build_trombinoscope",
    "configure",
    "find_images",
    "load_roster",
    "load_sqlite",
    "open_with_system_viewer",
    "read_image",
    "remove_accents",
    "render_pdf",
    "set_interactive",
    "write_image",
    "write_template",
]
