"""Mesure et illustre l'effet de l'harmonisation colorimétrique.

Produit deux choses :

* un tableau de métriques — dispersion chromatique et dispersion de luminance du
  lot, avant et après, pour chaque méthode de balance des blancs ;
* une planche de comparaison PNG, une ligne par méthode, pour juger à l'œil.

C'est le support chiffré de ``docs/color.md`` et l'artefact publié par la CI.

    uv run python scripts/fetch_samples.py
    uv run python scripts/color_bench.py --output artifacts
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from trombinoscope.color import BatchColorHarmonizer
from trombinoscope.detection import build_detector
from trombinoscope.framing import PortraitFramer
from trombinoscope.imageio import find_images, read_image, write_image
from trombinoscope.models import Box, ColorConfig, FramingConfig

METHODS = ("none", "grayworld", "shades-of-gray", "white-patch")
DEFAULT_SAMPLES = Path(__file__).resolve().parents[1] / "tests" / "data" / "portraits"


@dataclass(frozen=True)
class Metrics:
    """Ce qu'on cherche à réduire : l'écart entre les portraits d'un même lot."""

    chroma_spread: float
    luminance_spread: float

    def __str__(self) -> str:
        return f"chroma {self.chroma_spread:.4f}  luminance {self.luminance_spread:5.2f}"


def measure(portraits: list[tuple[np.ndarray, Box | None]]) -> Metrics:
    """Dispersion du lot, mesurée avec un harmoniseur neutre servant de sonde."""
    probe = BatchColorHarmonizer(ColorConfig())
    samples = [probe.measure(image, box) for image, box in portraits]
    illuminants = np.stack([s.illuminant for s in samples])
    chroma = illuminants / illuminants.sum(axis=1, keepdims=True)
    return Metrics(
        chroma_spread=float(chroma.std(axis=0).mean()),
        luminance_spread=float(np.std([s.luminance for s in samples])),
    )


def crop_all(folder: Path, width: int) -> list[tuple[np.ndarray, Box | None]]:
    """Recadre chaque photo du dossier : on ne compare que ce qui finit dans le PDF."""
    detector = build_detector("yunet", confidence=0.6)
    framer = PortraitFramer(FramingConfig(width=width))
    portraits = []
    for path in find_images(folder):
        image = read_image(path)
        detections = detector.detect(image)
        best = detections[0] if detections else None
        portraits.append((framer.frame(image, best), framer.framed_box(image, best)))
    return portraits


def harmonize(
    portraits: list[tuple[np.ndarray, Box | None]], config: ColorConfig
) -> list[tuple[np.ndarray, Box | None]]:
    harmonizer = BatchColorHarmonizer(config)
    for image, box in portraits:
        harmonizer.measure(image, box)
    return [(harmonizer.transform(image, box), box) for image, box in portraits]


def contact_sheet(rows: list[tuple[str, list[np.ndarray]]], label_height: int = 26) -> np.ndarray:
    """Empile les variantes, une ligne par méthode, avec son intitulé."""
    height, width = rows[0][1][0].shape[:2]
    columns = len(rows[0][1])
    sheet = np.full((len(rows) * (height + label_height), columns * width, 3), 255, dtype=np.uint8)
    for index, (label, images) in enumerate(rows):
        top = index * (height + label_height)
        cv2.putText(
            sheet, label, (6, top + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA
        )
        for column, image in enumerate(images):
            sheet[
                top + label_height : top + label_height + height,
                column * width : (column + 1) * width,
            ] = image
    return sheet


#: Dominantes simulant une même séance photo dont la balance des blancs de
#: l'appareil dérive : tungstène, néon, lumière du jour, ombre bleutée.
SESSION_CASTS = (
    (0.82, 0.98, 1.20),
    (0.95, 1.10, 0.92),
    (1.00, 1.00, 1.00),
    (1.22, 1.02, 0.86),
    (0.90, 0.96, 1.12),
    (1.10, 1.05, 0.94),
)


def controlled_experiment(portrait: np.ndarray, box: Box | None) -> tuple[list, list, str]:
    """Le cas d'usage réel : une seule séance, un seul sujet, éclairage qui dérive.

    On part d'un portrait unique, on lui applique des dominantes connues, puis on
    harmonise. Contrairement au lot de photos hétéroclites, la vérité terrain est
    ici connue : toutes les images devraient redevenir identiques.
    """
    variants = [
        (
            np.clip(portrait.astype(np.float32) * np.array(cast, dtype=np.float32), 0, 255).astype(
                np.uint8
            ),
            box,
        )
        for cast in SESSION_CASTS
    ]
    corrected = harmonize(variants, ColorConfig())

    before = measure(variants)
    after = measure(corrected)
    # Écart maximal entre deux images du lot, en niveaux : la mesure la plus parlante.
    spread_before = _max_pairwise_gap([image for image, _ in variants])
    spread_after = _max_pairwise_gap([image for image, _ in corrected])
    summary = (
        f"séance simulée : chroma {before.chroma_spread:.4f} → {after.chroma_spread:.4f}, "
        f"écart max entre deux portraits {spread_before:.1f} → {spread_after:.1f} niveaux"
    )
    return [image for image, _ in variants], [image for image, _ in corrected], summary


def _max_pairwise_gap(images: list[np.ndarray]) -> float:
    """Plus grand écart moyen absolu entre deux images du lot."""
    stack = np.stack([image.astype(np.float32) for image in images])
    means = stack.reshape(len(images), -1, 3).mean(axis=1)
    return float(max(np.abs(a - b).mean() for a in means for b in means))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES)
    parser.add_argument("--output", type=Path, default=Path("artifacts"))
    parser.add_argument("--width", type=int, default=200)
    args = parser.parse_args()

    if not args.samples.is_dir() or not find_images(args.samples):
        print(
            f"aucune photo dans {args.samples} — lancez d'abord scripts/fetch_samples.py",
            file=sys.stderr,
        )
        return 1

    originals = crop_all(args.samples, args.width)
    baseline = measure(originals)
    print(f"{'méthode':>16}  {'lot brut → lot corrigé'}")
    print(f"{'(aucune)':>16}  {baseline}")

    rows: list[tuple[str, list[np.ndarray]]] = [("brut", [image for image, _ in originals])]
    report_lines = [
        "| méthode | dispersion chromatique | dispersion de luminance |",
        "| --- | --- | --- |",
        f"| brut (aucune correction) | {baseline.chroma_spread:.4f} | "
        f"{baseline.luminance_spread:.2f} |",
    ]

    for method in METHODS:
        if method == "none":
            continue
        corrected = harmonize(originals, ColorConfig(white_balance=method))
        metrics = measure(corrected)
        print(f"{method:>16}  {metrics}")
        rows.append((method, [image for image, _ in corrected]))
        report_lines.append(
            f"| {method} | {metrics.chroma_spread:.4f} "
            f"({_delta(baseline.chroma_spread, metrics.chroma_spread)}) | "
            f"{metrics.luminance_spread:.2f} "
            f"({_delta(baseline.luminance_spread, metrics.luminance_spread)}) |"
        )

    # Le cas « photo par photo » : la comparaison qui justifie l'approche par lot.
    isolated = harmonize(originals, ColorConfig(harmonize_batch=False))
    isolated_metrics = measure(isolated)
    print(f"{'photo par photo':>16}  {isolated_metrics}")
    rows.append(("photo par photo", [image for image, _ in isolated]))
    report_lines.append(
        f"| shades-of-gray, **sans** harmonisation de lot | "
        f"{isolated_metrics.chroma_spread:.4f} "
        f"({_delta(baseline.chroma_spread, isolated_metrics.chroma_spread)}) | "
        f"{isolated_metrics.luminance_spread:.2f} "
        f"({_delta(baseline.luminance_spread, isolated_metrics.luminance_spread)}) |"
    )

    for strength in (0.5, 0.75):
        metrics = measure(harmonize(originals, ColorConfig(strength=strength)))
        print(f"{f'strength={strength}':>16}  {metrics}")
        report_lines.append(
            f"| shades-of-gray, strength={strength} | {metrics.chroma_spread:.4f} "
            f"({_delta(baseline.chroma_spread, metrics.chroma_spread)}) | "
            f"{metrics.luminance_spread:.2f} "
            f"({_delta(baseline.luminance_spread, metrics.luminance_spread)}) |"
        )

    args.output.mkdir(parents=True, exist_ok=True)
    sheet = write_image(args.output / "comparaison-couleur.png", contact_sheet(rows))

    before, after, summary = controlled_experiment(*originals[0])
    print(f"\n{summary}")
    report_lines += ["", f"Expérience contrôlée — {summary}."]
    controlled = write_image(
        args.output / "seance-simulee.png",
        contact_sheet([("dominantes appliquées", before), ("après harmonisation", after)]),
    )

    report = args.output / "comparaison-couleur.md"
    report.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"\nplanches : {sheet}\n           {controlled}\ntableau  : {report}")
    return 0


def _delta(before: float, after: float) -> str:
    if before == 0:
        return "—"
    return f"{(after - before) / before:+.0%}"


if __name__ == "__main__":
    sys.exit(main())
