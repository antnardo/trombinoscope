"""Le plus court chemin : un dossier de photos, une liste, un PDF.

Trois lignes utiles. Tout le reste de ce fichier est du confort de ligne de
commande et des messages.

    uv run python examples/01_minimal.py photos/ classe.csv

Le CSV n'a besoin que d'une colonne `nom` :

    nom,prenom
    HOPPER,Grace
    KNUTH,Donald

Les photos sont appariées aux personnes **par position**, dans l'ordre
alphabétique des noms de fichiers. Nommez-les `01.jpg`, `02.jpg`… plutôt que
`1.jpg`, `2.jpg`, `10.jpg`, sinon `10` se glisse entre `1` et `2`.
"""

import sys
from pathlib import Path

from trombinoscope import build_trombinoscope, configure


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    photos, liste = Path(sys.argv[1]), Path(sys.argv[2])
    sortie = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("trombinoscope.pdf")

    configure(verbosity=1)  # sans cet appel, la bibliothèque n'écrit rien

    rapport = build_trombinoscope(photos, liste, sortie, title="Trombinoscope")

    print(rapport.summary())
    print(f"PDF : {rapport.pdf}")
    # `ok` est faux dès qu'une personne n'a pas de photo, qu'une photo n'a pas de
    # personne, ou qu'un visage n'a pas été détecté. Le PDF est produit malgré tout.
    return 0 if rapport.ok else 1


if __name__ == "__main__":
    sys.exit(main())
