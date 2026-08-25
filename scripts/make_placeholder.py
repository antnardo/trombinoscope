"""Régénère `assets/placeholder.png`, la silhouette affichée quand une photo manque.

L'image est dessinée par ce script plutôt que téléchargée : c'est la seule façon
d'être certain qu'aucune œuvre tierce, et surtout aucun portrait de personne
réelle, ne se retrouve dans la distribution.

    uv run python scripts/make_placeholder.py
"""

from pathlib import Path

import cv2
import numpy as np

WIDTH, HEIGHT = 300, 400
BACKGROUND = (238, 238, 238)  # BGR
SILHOUETTE = (176, 176, 176)


def draw() -> np.ndarray:
    image = np.full((HEIGHT, WIDTH, 3), BACKGROUND, dtype=np.uint8)

    head_center = (WIDTH // 2, int(HEIGHT * 0.36))
    head_radius = int(WIDTH * 0.17)
    cv2.circle(image, head_center, head_radius, SILHOUETTE, thickness=-1, lineType=cv2.LINE_AA)

    # Buste : demi-ellipse dont le sommet arrive juste sous la tête.
    shoulders_center = (WIDTH // 2, int(HEIGHT * 0.92))
    axes = (int(WIDTH * 0.30), int(HEIGHT * 0.30))
    cv2.ellipse(
        image,
        shoulders_center,
        axes,
        angle=0,
        startAngle=180,
        endAngle=360,
        color=SILHOUETTE,
        thickness=-1,
        lineType=cv2.LINE_AA,
    )
    return image


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "src/trombinoscope/assets/placeholder.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(target), draw())
    print(f"écrit : {target} ({target.stat().st_size} octets)")


if __name__ == "__main__":
    main()
