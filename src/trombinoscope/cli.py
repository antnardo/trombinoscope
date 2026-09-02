"""Interface en ligne de commande.

Trois sous-commandes :

``build``      dossier de photos + CSV → PDF
``template``   écrit un CSV d'exemple
``inspect``    détecte les visages et écrit des images annotées, sans rien produire
               d'autre — pour régler le seuil et repérer les photos à plusieurs
               visages avant de lancer un build complet
"""

import argparse
import sys
from pathlib import Path

from trombinoscope import __version__
from trombinoscope.detection import build_detector
from trombinoscope.imageio import (
    draw_detections,
    find_images,
    open_with_system_viewer,
    read_image,
    write_image,
)
from trombinoscope.log import configure, error, info, set_interactive
from trombinoscope.models import ColorConfig, FramingConfig, GridConfig
from trombinoscope.pipeline import BuildOptions, TrombinoscopeBuilder
from trombinoscope.roster import write_template

WHITE_BALANCE_CHOICES = ("none", "grayworld", "shades-of-gray", "white-patch")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trombinoscope",
        description="Génère un trombinoscope PDF depuis un dossier de photos et un CSV.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="-v pour info, -vv pour debug"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    _add_build(sub.add_parser("build", help="produit le PDF"))
    _add_template(sub.add_parser("template", help="écrit un CSV d'exemple"))
    _add_inspect(sub.add_parser("inspect", help="diagnostique la détection de visages"))
    return parser


def _add_build(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("photos", type=Path, help="dossier contenant les photos")
    parser.add_argument("roster", type=Path, help="CSV ou JSON de la liste des personnes")
    parser.add_argument("-o", "--output", type=Path, default=Path("trombinoscope.pdf"))
    parser.add_argument("--title", default="Trombinoscope")
    parser.add_argument("--subtitle", default="")
    parser.add_argument(
        "--absent",
        nargs="*",
        default=[],
        metavar="NOM",
        help="noms présents dans la liste mais sans photo",
    )
    parser.add_argument("--logo", type=Path, default=None)
    parser.add_argument(
        "--portraits", type=Path, default=None, help="dossier des portraits produits"
    )
    parser.add_argument("--debug-dir", type=Path, default=None, help="images de détection annotées")
    parser.add_argument("--open", action="store_true", help="ouvre le PDF à la fin")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="marque une pause après chaque avertissement, pour un suivi pas à pas",
    )

    detection = parser.add_argument_group("détection")
    detection.add_argument("--backend", choices=("yunet", "haar"), default="yunet")
    detection.add_argument("--confidence", type=float, default=0.6, help="seuil de détection")
    detection.add_argument(
        "--pick",
        action="append",
        default=[],
        metavar="NOM=INDEX",
        help="visage à retenir pour une personne (INDEX négatif = aucun). Répétable.",
    )

    framing = parser.add_argument_group("cadrage")
    framing.add_argument("--face-ratio", type=float, default=0.55)
    framing.add_argument("--aspect-ratio", type=float, default=4 / 3)
    framing.add_argument("--face-y", type=float, default=0.5)
    framing.add_argument("--portrait-width", type=int, default=300)
    framing.add_argument(
        "--align-eyes", action="store_true", help="redresse la ligne des yeux (yunet seulement)"
    )

    color = parser.add_argument_group("couleur")
    color.add_argument("--white-balance", choices=WHITE_BALANCE_CHOICES, default="shades-of-gray")
    color.add_argument("--minkowski-p", type=float, default=6.0)
    color.add_argument(
        "--auto-levels",
        type=float,
        default=0.0,
        metavar="PCT",
        help=(
            "étalement d'histogramme, écrêtage en %% à chaque extrémité. "
            "Désactivé par défaut : il dégrade la cohérence du lot (voir docs/color.md)"
        ),
    )
    color.add_argument(
        "--no-harmonize",
        action="store_true",
        help="corrige chaque photo isolément au lieu de l'aligner sur le lot",
    )
    color.add_argument("--max-gain", type=float, default=2.0)
    color.add_argument(
        "--max-luminance-shift",
        type=float,
        default=20.0,
        metavar="POINTS",
        help=(
            "déplacement maximal de la luminance d'un portrait, en points de L* "
            "(0 pour lever la bride). Protège les photos très sombres ou très "
            "claires, que tirer jusqu'à la médiane du lot délave"
        ),
    )
    color.add_argument(
        "--no-color",
        action="store_true",
        help="ne touche pas du tout aux couleurs : ni balance des blancs, ni exposition",
    )
    color.add_argument(
        "--strength",
        type=float,
        default=1.0,
        help="intensité de la correction de teinte, de 0 (aucune) à 1 (complète)",
    )

    grid = parser.add_argument_group("mise en page")
    grid.add_argument("-c", "--columns", type=int, default=5)
    grid.add_argument("--padding", type=float, default=0.2, help="blanc par colonne, en fraction")
    grid.add_argument("--line-skip", type=float, default=8.0, help="en points")
    grid.add_argument("--font-size", type=float, default=10.0, help="taille des noms, en points")
    grid.add_argument("--landscape", action="store_true")
    grid.add_argument("--no-center-last-row", action="store_true")
    grid.add_argument(
        "--no-shrink-names",
        action="store_true",
        help="laisse les noms trop larges se replier sur deux lignes au lieu de les réduire",
    )
    grid.add_argument(
        "--shrink-floor",
        type=float,
        default=0.6,
        metavar="FRACTION",
        help="plancher de cette réduction, en fraction de --font-size",
    )
    grid.add_argument("--no-tags", action="store_true")
    grid.add_argument("--no-groups", action="store_true")
    grid.add_argument("--no-badges", action="store_true")


def _add_template(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("output", type=Path, nargs="?", default=Path("classe.csv"))


def _add_inspect(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("photos", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("detections"))
    parser.add_argument("--backend", choices=("yunet", "haar"), default="yunet")
    parser.add_argument("--confidence", type=float, default=0.6)


# --------------------------------------------------------------------------- #


def _parse_picks(entries: list[str]) -> dict[str, int]:
    picks: dict[str, int] = {}
    for entry in entries:
        name, _, value = entry.partition("=")
        if not _:
            raise ValueError(f"--pick attend NOM=INDEX, reçu {entry!r}")
        try:
            picks[name.strip()] = int(value)
        except ValueError:
            raise ValueError(f"--pick : index non entier dans {entry!r}") from None
    return picks


def _color_from(args: argparse.Namespace) -> ColorConfig:
    """Configuration colorimétrique. ``--no-color`` court-circuite tout le reste."""
    if args.no_color:
        return ColorConfig(white_balance="none", auto_levels_clip=None, harmonize_batch=False)
    return ColorConfig(
        white_balance=args.white_balance,
        minkowski_p=args.minkowski_p,
        auto_levels_clip=args.auto_levels if args.auto_levels > 0 else None,
        harmonize_batch=not args.no_harmonize,
        max_gain=args.max_gain,
        strength=args.strength,
        max_luminance_shift=(args.max_luminance_shift if args.max_luminance_shift > 0 else None),
    )


def _options_from(args: argparse.Namespace) -> BuildOptions:
    return BuildOptions(
        title=args.title,
        subtitle=args.subtitle,
        absent=tuple(args.absent),
        face_choice=_parse_picks(args.pick),
        detector_backend=args.backend,
        confidence=args.confidence,
        logo=args.logo,
        debug_dir=args.debug_dir,
        framing=FramingConfig(
            aspect_ratio=args.aspect_ratio,
            face_ratio=args.face_ratio,
            face_y=args.face_y,
            width=args.portrait_width,
            align_eyes=args.align_eyes,
        ),
        color=_color_from(args),
        grid=GridConfig(
            columns=args.columns,
            column_padding=args.padding,
            line_skip=args.line_skip,
            font_size=args.font_size,
            landscape=args.landscape,
            center_last_row=not args.no_center_last_row,
            shrink_long_names=not args.no_shrink_names,
            name_shrink_floor=args.shrink_floor,
            show_tags=not args.no_tags,
            show_groups=not args.no_groups,
            show_badges=not args.no_badges,
        ),
    )


def _run_build(args: argparse.Namespace) -> int:
    set_interactive(args.interactive)
    report = TrombinoscopeBuilder(_options_from(args)).build(
        args.photos, args.roster, args.output, portrait_dir=args.portraits
    )
    print(report.summary())
    print(f"PDF : {report.pdf}")
    if args.open and report.pdf:
        open_with_system_viewer(report.pdf)
    return 0 if report.ok else 1


def _run_template(args: argparse.Namespace) -> int:
    path = write_template(args.output)
    print(f"Modèle écrit : {path}")
    return 0


def _run_inspect(args: argparse.Namespace) -> int:
    detector = build_detector(args.backend, confidence=args.confidence)
    photos = find_images(args.photos)
    args.output.mkdir(parents=True, exist_ok=True)
    problems = 0
    for photo in photos:
        image = read_image(photo)
        detections = detector.detect(image)
        marker = "  " if len(detections) == 1 else "!!"
        print(f"{marker} {photo.name}: {len(detections)} visage(s)")
        if len(detections) != 1:
            problems += 1
        write_image(
            args.output / f"{photo.stem}.detections.jpg", draw_detections(image, detections)
        )
    info("images annotées dans %s", args.output)
    return 0 if problems == 0 else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure(args.verbose)
    runners = {"build": _run_build, "template": _run_template, "inspect": _run_inspect}
    try:
        return runners[args.command](args)
    except (FileNotFoundError, NotADirectoryError) as exc:
        error("fichier ou dossier introuvable : %s", exc)
        return 2
    except ValueError as exc:
        error("%s", exc)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
