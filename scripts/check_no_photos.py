"""Vérifie qu'aucune photographie n'est présente dans une distribution.

Le paquet embarque volontairement une seule image — la silhouette de
remplacement, dessinée par ``make_placeholder.py`` — et aucune photographie de
personne. Ce garde-fou est exécuté par la CI sur la roue et sur l'archive source,
parce qu'une distribution est irrévocable : un fichier publié par erreur sur PyPI
ne peut pas être vraiment retiré.

    python scripts/check_no_photos.py dist/*.whl dist/*.tar.gz
"""

import sys
import tarfile
import zipfile
from collections.abc import Iterator
from pathlib import Path

#: Extensions qui ne peuvent être qu'une photographie. Le PNG n'y figure pas :
#: la silhouette de remplacement en est un, et elle est autorisée nommément.
PHOTO_SUFFIXES = (".jpg", ".jpeg", ".heic", ".heif", ".tif", ".tiff", ".webp")

#: Seules images légitimement distribuées.
ALLOWED = ("trombinoscope/assets/placeholder.png",)


def members(path: Path) -> Iterator[str]:
    if path.suffix == ".whl" or path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            yield from archive.namelist()
    elif path.name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(path) as archive:
            yield from archive.getnames()
    else:
        raise ValueError(f"format d'archive non reconnu : {path}")


def _is_unexpected(name: str) -> bool:
    lowered = name.lower()
    if lowered.endswith(PHOTO_SUFFIXES):
        return True
    return lowered.endswith(".png") and not any(name.endswith(ok) for ok in ALLOWED)


def offending(path: Path) -> list[str]:
    return [name for name in members(path) if _is_unexpected(name)]


def main(argv: list[str]) -> int:
    if not argv:
        print("usage : check_no_photos.py ARCHIVE...", file=sys.stderr)
        return 2

    failures = 0
    for argument in argv:
        path = Path(argument)
        if not path.exists():
            print(f"introuvable : {path}", file=sys.stderr)
            return 2
        found = offending(path)
        if found:
            failures += 1
            print(f"::error::images inattendues dans {path.name}", file=sys.stderr)
            for name in found:
                print(f"  {name}", file=sys.stderr)
        else:
            print(f"{path.name} : aucune photographie")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
