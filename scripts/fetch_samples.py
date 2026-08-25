"""Télécharge les portraits d'exemple utilisés par les tests d'intégration.

Ces images ne sont **pas** versionnées. Le dépôt ne contient aucune photographie
de personne : les tests qui en ont besoin les récupèrent à la demande, et les
tests unitaires — qui constituent l'essentiel de la couverture — fonctionnent
entièrement sur des images synthétiques, sans réseau.

Les fichiers retenus sont des portraits de pionnières et pionniers de
l'informatique, hébergés sur Wikimedia Commons sous licence libre : domaine
public, CC BY ou CC BY-SA selon les cas. La licence et l'auteur de chaque image
sont repris dans ``CREDITS.md`` et dans le manifeste écrit à côté des fichiers.

Ils ont aussi l'avantage d'être un vrai cas difficile : contrairement à une série
de portraits de studio, ce sont des photographies prises dans des lieux, à des
époques et avec des matériels totalement différents. C'est précisément la
situation que l'harmonisation colorimétrique doit rattraper.

    uv run python scripts/fetch_samples.py
    uv run python scripts/fetch_samples.py --check   # vérifie sans télécharger
"""

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

USER_AGENT = "trombinoscope-samples/0.1 (https://github.com/antnardo/trombinoscope)"
COMMONS_FILEPATH = "https://commons.wikimedia.org/wiki/Special:FilePath/"
THUMB_WIDTH = 1024

DESTINATION = Path(__file__).resolve().parents[1] / "tests" / "data" / "portraits"


@dataclass(frozen=True)
class Sample:
    """Un fichier d'exemple et sa provenance."""

    commons_file: str
    local_name: str
    person: str
    licence: str
    author: str

    @property
    def url(self) -> str:
        quoted = urllib.parse.quote(self.commons_file.replace(" ", "_"))
        return f"{COMMONS_FILEPATH}{quoted}?width={THUMB_WIDTH}"

    @property
    def page_url(self) -> str:
        quoted = urllib.parse.quote(self.commons_file.replace(" ", "_"))
        return f"https://commons.wikimedia.org/wiki/File:{quoted}"


#: L'ordre définit l'appariement positionnel attendu par les tests : il doit
#: correspondre à l'ordre alphabétique des noms de fichiers locaux.
SAMPLES: tuple[Sample, ...] = (
    Sample(
        "Commodore Grace M. Hopper, USN (covered).jpg",
        "01-hopper.jpg",
        "HOPPER Grace",
        "Domaine public",
        "James S. Davis, U.S. Navy",
    ),
    Sample(
        "Katherine Johnson 1983.jpg",
        "02-johnson.jpg",
        "JOHNSON Katherine",
        "Domaine public",
        "NASA",
    ),
    Sample(
        "Radia Perlman 2009.jpg",
        "03-perlman.jpg",
        "PERLMAN Radia",
        "Domaine public",
        "Scientist-100 (Wikipédia anglophone)",
    ),
    Sample(
        "Margaret Hamilton 1995.jpg",
        "04-hamilton.jpg",
        "HAMILTON Margaret",
        "CC BY-SA 3.0",
        "Daphne Weld Nichols",
    ),
    Sample(
        "Barbara Liskov MIT computer scientist 2010.jpg",
        "05-liskov.jpg",
        "LISKOV Barbara",
        "CC BY-SA 3.0",
        "Kenneth C. Zirkel",
    ),
    Sample(
        "Guido-portrait-2014-drc.jpg",
        "06-vanrossum.jpg",
        "VAN ROSSUM Guido",
        "CC BY-SA 4.0",
        "Daniel Stroud",
    ),
    Sample(
        "KnuthAtOpenContentAlliance.jpg",
        "07-knuth.jpg",
        "KNUTH Donald",
        "CC BY-SA 2.5",
        "Jacob Appelbaum",
    ),
    Sample(
        "Alan Kay (3097597186).jpg",
        "08-kay.jpg",
        "KAY Alan",
        "CC BY 2.0",
        "Marcin Wichary",
    ),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def download(sample: Sample, destination: Path) -> Path:
    target = destination / sample.local_name
    if target.exists():
        print(f"  déjà présent : {sample.local_name}")
        return target
    request = urllib.request.Request(sample.url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    print(f"  téléchargé   : {sample.local_name} ({len(payload) / 1024:.0f} Ko)")
    return target


def write_manifest(destination: Path) -> Path:
    """Écrit le relevé de provenance à côté des images."""
    manifest = {
        "source": "Wikimedia Commons",
        "note": (
            "Images non versionnées, téléchargées à la demande pour les tests "
            "d'intégration. Licences individuelles ci-dessous ; voir CREDITS.md."
        ),
        "width": THUMB_WIDTH,
        "files": [
            {
                "file": sample.local_name,
                "person": sample.person,
                "licence": sample.licence,
                "author": sample.author,
                "commons": sample.commons_file,
                "page": sample.page_url,
                "sha256": sha256(destination / sample.local_name)
                if (destination / sample.local_name).exists()
                else None,
            }
            for sample in SAMPLES
        ],
    }
    path = destination / "MANIFEST.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=DESTINATION)
    parser.add_argument(
        "--check", action="store_true", help="vérifie la présence sans rien télécharger"
    )
    args = parser.parse_args()

    if args.check:
        missing = [s.local_name for s in SAMPLES if not (args.dest / s.local_name).exists()]
        if missing:
            print(f"manquant(s) : {', '.join(missing)}", file=sys.stderr)
            return 1
        print(f"{len(SAMPLES)} portrait(s) présent(s) dans {args.dest}")
        return 0

    print(f"Portraits d'exemple → {args.dest}")
    for sample in SAMPLES:
        try:
            download(sample, args.dest)
        except (urllib.error.URLError, OSError) as exc:
            print(f"  ÉCHEC {sample.local_name} : {exc}", file=sys.stderr)
            return 1

    manifest = write_manifest(args.dest)
    print(f"Manifeste : {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
