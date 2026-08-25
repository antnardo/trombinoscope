"""Reproduit le trombinoscope de classe préparatoire, depuis la base SQLite.

C'est la transposition du pilote ``make_trombinoscope.py`` de 2020 sur l'API
actuelle : mêmes réglages de mise en page, même source de données, même nom de
fichier de sortie. Il sert de test grandeur nature et de démonstration de la
conversion d'un schéma métier vers le modèle générique du paquet.

    export TROMBI_RACINE=~/mes-classes/MP  TROMBI_CLASSE=MP2  TROMBI_ANNEE=2025
    uv run python examples/trombi_mp_sqlite.py
    uv run python examples/trombi_mp_sqlite.py --no-detection   # mise en page seule
    uv run python examples/trombi_mp_sqlite.py -o /tmp/essai.pdf
    uv run python examples/trombi_mp_sqlite.py --racine ~/ailleurs/MP --annee 2026

Le dossier de travail se donne par ``TROMBI_RACINE`` ou ``--racine``. Rien n'y est
écrit en dehors du PDF, des portraits recadrés et des images de diagnostic — et
le script **refuse d'écraser un PDF existant** sans ``--force``, le nom de sortie
étant celui d'un document souvent déjà distribué.

Ce fichier lit des données personnelles réelles : il n'est pas exécuté par la
suite de tests et le dossier qu'il vise n'appartient pas au dépôt.
"""

import argparse
import os
import sys
from pathlib import Path

from trombinoscope import (
    BuildOptions,
    ColorConfig,
    FramingConfig,
    GridConfig,
    Person,
    TrombinoscopeBuilder,
    configure,
    open_with_system_viewer,
    render_pdf,
)
from trombinoscope.models import positional_match
from trombinoscope.pdf.canvas import styles
from trombinoscope.roster import load_sqlite, remove_accents

# --------------------------------------------------------------------------- #
# Ce qui vient de l'installation d'origine
# --------------------------------------------------------------------------- #

#: Dossier de travail : il contient ``base.db``, ``photos/`` et ``logo/``.
#: Renseignez ``TROMBI_RACINE`` dans votre environnement, ou passez ``--racine``,
#: pour ne pas inscrire un chemin personnel dans un dépôt public.
RACINE = Path(os.environ.get("TROMBI_RACINE", "trombi")).expanduser()
NOM_CLASSE = os.environ.get("TROMBI_CLASSE", "CLASSE")
ANNEE = int(os.environ.get("TROMBI_ANNEE", "2025"))

BASE = "base.db"
PHOTOS = "photos"
LOGO = "logo/logo.png"

#: Noms présents dans la base mais sans photo dans le dossier.
ABSENTS: tuple[str, ...] = ()

#: ``{NOM: index}`` — quel visage retenir quand la photo en contient plusieurs.
#: L'index est celui affiché sur les images de ``photos/detections``. ``-1``
#: conserve la photo entière, sans recadrage.
CHOIX_VISAGE: dict[str, int] = {}

SEUIL_DETECTION = 0.9

# La requête reprend celle du pilote d'origine, avec des alias qui traduisent le
# schéma métier vers les colonnes attendues par le paquet. `option`, `LV1` et
# `LV2` deviennent une liste d'étiquettes ; `groupe` et `groupecolle` une autre ;
# `cube` — la « cinq-demi » — devient le badge en étoile.
REQUETE = """
    SELECT
        nom,
        prenom,
        cube AS badge,
        TRIM(
            COALESCE(NULLIF(option, ''), '')
            || ';' || COALESCE(NULLIF(LV1, ''), '')
            || ';' || COALESCE(NULLIF(LV2, ''), '')
        ) AS tags,
        CASE WHEN groupe > 0 THEN 'Gr' || groupe ELSE '' END
        || ';'
        || CASE WHEN groupecolle > 0 THEN 'Tr' || groupecolle ELSE '' END AS groupes
    FROM eleves
    ORDER BY nom
"""


def trier_sans_accents(personnes: list[Person]) -> list[Person]:
    """Ordre alphabétique français.

    ``ORDER BY nom`` en SQLite compare les points de code : « Étienne » se
    retrouve après « Zola ». Le tri est donc refait côté Python, sur les noms
    sans diacritiques, comme le faisait le pilote d'origine.
    """
    return sorted(personnes, key=lambda p: remove_accents(p.last_name).upper())


def appliquer_polices() -> None:
    """Réglages typographiques du document d'origine."""
    styles["Titre"].fontName = "Helvetica-Bold"
    styles["Titre"].fontSize = 18
    styles["Noms"].fontName = "Helvetica"
    styles["Noms"].fontSize = 7
    # Interligne volontairement large devant le corps : c'est ce qui aère le bloc
    # nom/prénom sous chaque photo, et ce qui fixe le pas des lignes de la grille.
    styles["Noms"].leading = 12


def mise_en_page() -> GridConfig:
    """Grille identique à celle du pilote de 2020."""
    return GridConfig(
        columns=7,
        column_padding=0.1,
        line_skip=5.0,
        margin_left=8.0,
        margin_right=8.0,
        margin_top=5.0,
        margin_bottom=5.0,
        font_size=12.0,
        # En hauteurs de ligne, comme dans le pilote d'origine : une ligne de blanc
        # au-dessus du titre, deux en dessous.
        title_top=1.0,
        title_skip=2.0,
        landscape=False,
        center_last_row=True,
        # Les deux séries d'étiquettes dans la gouttière gauche et l'étoile en bas
        # à droite : c'est la disposition d'origine, que le défaut du paquet ne
        # reprend pas.
        annotation_layout="left",
        badge_corner="bottom-right",
        # Le logo mord de 4,5 mm sur la marge haute : il se cale à un demi
        # millimètre du bord de page, pas du cadre de contenu.
        logo_position="top-right",
        logo_width=30.0,
        logo_offset=(0.0, 4.5),
        annotation_font="Courier",
        annotation_font_size=1.7 * 72 / 25.4,  # 1,7 mm, converti en points
    )


def construire(
    racine: Path,
    annee: int,
    classe: str,
    *,
    detection: bool,
    couleur: bool,
    sortie: Path | None = None,
) -> Path:
    base = racine / BASE
    photos = racine / PHOTOS
    sortie = sortie or racine / f"Trombi_{classe}_{annee - 2000}.pdf"
    logo = racine / LOGO

    appliquer_polices()
    personnes = trier_sans_accents(load_sqlite(base, REQUETE))
    print(f"{len(personnes)} élève(s) dans {base.name}")

    if not detection:
        # Mise en page seule, sur les portraits déjà produits par un passage
        # précédent. Pratique pour itérer sur la grille sans repayer la détection.
        portraits = sorted((racine / "portraits").glob("*.portrait.jpg"))
        if not portraits:
            print(
                f"aucun portrait dans {racine / 'portraits'} : lancez d'abord sans --no-detection",
                file=sys.stderr,
            )
            raise SystemExit(1)
        attendus, _, _ = positional_match(personnes, portraits, ABSENTS)
        for personne, portrait in attendus:
            personne.portrait = portrait
        return render_pdf(
            personnes,
            sortie,
            title=f"Trombinoscope {classe} {annee}-{annee + 1}",
            config=mise_en_page(),
            logo=logo if logo.exists() else None,
        )

    options = BuildOptions(
        title=f"Trombinoscope {classe} {annee}-{annee + 1}",
        absent=ABSENTS,
        face_choice=CHOIX_VISAGE,
        confidence=SEUIL_DETECTION,
        logo=logo if logo.exists() else None,
        debug_dir=photos / "detections",
        framing=FramingConfig(
            aspect_ratio=4 / 3,
            face_ratio=0.55,
            face_y=0.5,
            width=300,
        ),
        color=ColorConfig()
        if couleur
        else ColorConfig(white_balance="none", harmonize_batch=False),
        grid=mise_en_page(),
    )

    rapport = TrombinoscopeBuilder(options).build(
        photos, personnes, sortie, portrait_dir=racine / "portraits"
    )
    print(rapport.summary())
    for chemin in rapport.multiple_faces:
        print(f"  plusieurs visages : {chemin.name} — voir {photos / 'detections'}")
    for chemin in rapport.no_face:
        print(f"  aucun visage : {chemin.name}")
    return rapport.pdf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--racine", type=Path, default=RACINE)
    parser.add_argument("--annee", type=int, default=ANNEE)
    parser.add_argument("--classe", default=NOM_CLASSE)
    parser.add_argument(
        "-o",
        "--sortie",
        type=Path,
        default=None,
        help="chemin du PDF ; par défaut RACINE/Trombi_CLASSE_AA.pdf",
    )
    parser.add_argument(
        "--force", action="store_true", help="autorise l'écrasement du PDF s'il existe déjà"
    )
    parser.add_argument(
        "--no-detection",
        action="store_true",
        help="réutilise les portraits déjà recadrés, pour itérer sur la mise en page",
    )
    parser.add_argument(
        "--no-couleur",
        action="store_true",
        help="désactive l'harmonisation colorimétrique",
    )
    parser.add_argument("--open", action="store_true", help="ouvre le PDF à la fin")
    parser.add_argument("-v", "--verbose", action="count", default=1)
    args = parser.parse_args()

    configure(args.verbose)
    if not args.racine.is_dir():
        print(f"dossier introuvable : {args.racine}", file=sys.stderr)
        return 2

    sortie = args.sortie or args.racine / f"Trombi_{args.classe}_{args.annee - 2000}.pdf"
    if sortie.exists() and not args.force:
        print(
            f"{sortie} existe déjà. Relancez avec --force pour l'écraser, "
            "ou avec -o pour écrire ailleurs.",
            file=sys.stderr,
        )
        return 2

    pdf = construire(
        args.racine,
        args.annee,
        args.classe,
        detection=not args.no_detection,
        couleur=not args.no_couleur,
        sortie=sortie,
    )
    print(f"PDF : {pdf}")
    if args.open:
        open_with_system_viewer(pdf)
    return 0


if __name__ == "__main__":
    sys.exit(main())
