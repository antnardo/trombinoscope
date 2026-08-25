"""Tour complet des réglages, en six étapes commentées.

Chaque section est indépendante et écrit son propre PDF, pour qu'on puisse
comparer les résultats côte à côte.

    uv run python scripts/fetch_samples.py          # portraits d'exemple
    uv run python examples/02_options.py --sortie /tmp/demo

Les portraits utilisés sont ceux de `tests/data/portraits`, téléchargés depuis
Wikimedia Commons sous licence libre. Voir CREDITS.md.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

from trombinoscope import (
    BatchColorHarmonizer,
    BuildOptions,
    ColorConfig,
    FramingConfig,
    GridConfig,
    GridPaginator,
    Person,
    PortraitFramer,
    TrombinoscopeBuilder,
    configure,
    find_images,
    load_roster,
    read_image,
    render_pdf,
    write_image,
)
from trombinoscope.models import Box, Detection

RACINE = Path(__file__).resolve().parent.parent
PHOTOS = RACINE / "tests" / "data" / "portraits"
LISTE = Path(__file__).resolve().parent / "classe-exemple.csv"


def titre(numero: int, texte: str) -> None:
    print(f"\n{'─' * 70}\n{numero}. {texte}\n{'─' * 70}")


# --------------------------------------------------------------------------- #


def etape_1_defauts(sortie: Path) -> None:
    """Les réglages par défaut suffisent dans la plupart des cas."""
    titre(1, "Réglages par défaut")
    rapport = TrombinoscopeBuilder(BuildOptions(title="Défauts")).build(
        PHOTOS, LISTE, sortie / "1-defauts.pdf", portrait_dir=sortie / "portraits"
    )
    print(rapport.summary())


def etape_2_cadrage(sortie: Path) -> None:
    """`face_ratio` est le réglage qui change le plus l'allure d'une planche.

    C'est la fraction de la largeur du cadre occupée par le visage — constante
    pour tout le lot, quelle que soit la distance de prise de vue.
    """
    titre(2, "Cadrage : face_ratio, face_y, align_eyes")
    for nom, cadrage in {
        "large": FramingConfig(face_ratio=0.35),
        "classique": FramingConfig(face_ratio=0.55),
        "serre": FramingConfig(face_ratio=0.70, face_y=0.40),
        "redresse": FramingConfig(face_ratio=0.55, align_eyes=True),
    }.items():
        options = BuildOptions(title=f"Cadrage {nom}", framing=cadrage)
        TrombinoscopeBuilder(options).build(
            PHOTOS, LISTE, sortie / f"2-cadrage-{nom}.pdf", portrait_dir=sortie / f"p-{nom}"
        )
        print(f"  {nom:10s} face_ratio={cadrage.face_ratio} face_y={cadrage.face_y}")


def etape_3_couleur(sortie: Path) -> None:
    """L'harmonisation vise la médiane du lot, pas le gris neutre.

    `--no-harmonize` (ici `harmonize_batch=False`) corrige chaque photo isolément :
    meilleure neutralité par image, mais aucune cohérence d'exposition entre elles.
    """
    titre(3, "Couleur : méthode, intensité, harmonisation de lot")
    for nom, couleur in {
        "aucune": ColorConfig(white_balance="none", harmonize_batch=False),
        "lot": ColorConfig(),
        "lot-douce": ColorConfig(strength=0.7),
        "photo-par-photo": ColorConfig(harmonize_batch=False),
    }.items():
        options = BuildOptions(title=f"Couleur {nom}", color=couleur)
        TrombinoscopeBuilder(options).build(
            PHOTOS, LISTE, sortie / f"3-couleur-{nom}.pdf", portrait_dir=sortie / f"c-{nom}"
        )
        print(f"  {nom:16s} {couleur.white_balance}, strength={couleur.strength}")


def etape_4_mise_en_page(sortie: Path) -> None:
    """Deux dispositions d'annotations, et le placement du logo et de l'étoile."""
    titre(4, "Mise en page")
    gens = load_roster(LISTE)
    for nom, grille in {
        "gouttieres": GridConfig(columns=4),
        "gouttiere-gauche": GridConfig(columns=4, annotation_layout="left"),
        "paysage": GridConfig(columns=6, landscape=True),
        "sobre": GridConfig(columns=4, show_tags=False, show_groups=False, show_badges=False),
    }.items():
        render_pdf(gens, sortie / f"4-page-{nom}.pdf", title=f"Page {nom}", config=grille)
        print(f"  {nom:18s} {grille.columns} colonnes, layout={grille.annotation_layout}")


def etape_5_diagnostic(sortie: Path) -> None:
    """Le rapport dit ce qui a échoué. Rien n'est avalé silencieusement."""
    titre(5, "Diagnostic : absents, choix de visage, rapport")
    # KAY est dans la liste mais pas photographié : `absent` décale l'appariement
    # d'un cran plutôt que de le casser. Les deux personnes ajoutées à la fin,
    # elles, n'ont aucune photo disponible : le rapport les signale.
    gens = [*load_roster(LISTE), Person("SANS-PHOTO", "Une"), Person("SANS-PHOTO", "Deux")]
    options = BuildOptions(
        title="Diagnostic",
        absent=("KAY",),  # dans la liste, mais pas photographié
        face_choice={"KNUTH": 0},  # index du visage à retenir sur sa photo
        confidence=0.6,
        debug_dir=sortie / "detections",  # images annotées, pour régler --pick
    )
    rapport = TrombinoscopeBuilder(options).build(
        PHOTOS, gens, sortie / "5-diagnostic.pdf", portrait_dir=sortie / "d"
    )
    print(f"  {rapport.summary()}")
    print(f"  ok = {rapport.ok}")
    for nom in rapport.unmatched_people:
        print(f"  sans photo : {nom}")
    for chemin in rapport.unmatched_photos:
        print(f"  photo en trop : {chemin.name}")


def etape_6_briques(sortie: Path) -> None:
    """Chaque étape s'utilise seule, sans passer par le pipeline."""
    titre(6, "Les briques séparément")

    # a) recadrer sans produire de PDF, avec un détecteur maison
    class DetecteurFixe:
        """N'importe quel objet avec `detect(image) -> list[Detection]` convient."""

        def detect(self, image: np.ndarray) -> list[Detection]:
            h, w = image.shape[:2]
            return [Detection(box=Box(w // 4, h // 5, 3 * w // 4, 3 * h // 5), confidence=1.0)]

    photo = read_image(find_images(PHOTOS)[0])
    portrait = PortraitFramer(FramingConfig(width=200)).frame(
        photo, DetecteurFixe().detect(photo)[0]
    )
    write_image(sortie / "6a-recadrage-seul.jpg", portrait)
    print(f"  a) recadrage seul       → {portrait.shape[1]}×{portrait.shape[0]} px")

    # b) harmoniser un lot d'images quelconques, sans détection ni PDF
    images = [read_image(p) for p in find_images(PHOTOS)]
    harmoniseur = BatchColorHarmonizer(ColorConfig(estimate_on_face=False))
    for image in images:
        harmoniseur.measure(image, None)  # passe 1 : mesurer tout le lot
    corriges = [harmoniseur.transform(image, None) for image in images]  # passe 2
    reference = harmoniseur.reference_illuminant
    bgr = " ".join(f"{c}={v:.3f}" for c, v in zip("BGR", reference, strict=True))
    print(f"  b) illuminant du lot    → {bgr}")
    write_image(sortie / "6b-harmonise.jpg", corriges[0])

    # c) pagination seule : de l'arithmétique, testable sans ReportLab
    pages = GridPaginator(GridConfig(columns=5)).paginate(load_roster(LISTE), rows_per_page=2)
    for page in pages:
        derniere = page.rows - 1
        occupees = sorted(c.column for c in page.cells if c.row == derniere)
        print(
            f"  c) page {page.number} : {len(page.cells)} cellules, "
            f"dernière ligne aux colonnes {occupees}"
        )


# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sortie", type=Path, default=Path("demo-trombinoscope"))
    parser.add_argument("-v", "--verbose", action="count", default=0)
    args = parser.parse_args()

    configure(args.verbose)
    if not PHOTOS.is_dir() or not find_images(PHOTOS):
        print(
            f"aucune photo dans {PHOTOS}\nlancez d'abord : uv run python scripts/fetch_samples.py",
            file=sys.stderr,
        )
        return 1

    args.sortie.mkdir(parents=True, exist_ok=True)
    for etape in (
        etape_1_defauts,
        etape_2_cadrage,
        etape_3_couleur,
        etape_4_mise_en_page,
        etape_5_diagnostic,
        etape_6_briques,
    ):
        etape(args.sortie)

    print(f"\n{len(list(args.sortie.glob('*.pdf')))} PDF écrits dans {args.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
