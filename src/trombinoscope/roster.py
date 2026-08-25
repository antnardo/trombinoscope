"""Chargement de la liste des personnes.

Le format d'échange est le CSV — produit par n'importe quel tableur ou export
d'ENT —, le JSON, ou une requête SQLite. Les colonnes sont librement nommées et
reconnues par alias.

Colonnes reconnues (insensibles à la casse et aux accents) :

===============  ==========================================================
``nom``          nom de famille — seule colonne obligatoire
``prenom``       prénom
``tags``         étiquettes affichées en bas de la photo, séparées par ``;``
``groupes``      étiquettes affichées en haut de la photo, séparées par ``;``
``badge``        ``1``/``oui``/``true`` pour afficher l'étoile
===============  ==========================================================

Toute colonne non reconnue est ignorée, ce qui permet de donner directement un
export complet sans le retailler.
"""

import csv
import json
import sqlite3
import unicodedata
from collections.abc import Iterable, Sequence
from pathlib import Path

from trombinoscope.log import info, warning
from trombinoscope.models import Person

#: Séparateur des étiquettes à l'intérieur d'une cellule.
TAG_SEPARATOR = ";"

_TRUE_VALUES = {"1", "true", "vrai", "oui", "yes", "y", "o", "x"}

_ALIASES: dict[str, tuple[str, ...]] = {
    "last_name": ("nom", "lastname", "last_name", "name", "surname", "famille"),
    "first_name": ("prenom", "firstname", "first_name", "given", "prenoms"),
    "tags": ("tags", "tag", "options", "etiquettes", "labels"),
    "groups": ("groupes", "groupe", "groups", "group"),
    "badge": ("badge", "etoile", "star", "cube", "flag"),
}


def normalize_key(value: str) -> str:
    """Minuscules, sans accents ni espaces — pour reconnaître ``Prénom`` comme ``prenom``."""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.strip().lower().replace(" ", "_").replace("-", "_")


def remove_accents(value: str) -> str:
    """Retire les diacritiques d'une chaîne.

    Utile pour trier une liste de noms français : l'ordre naturel de Python place
    « Étienne » après « Zola ».
    """
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _split_tags(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    separator = TAG_SEPARATOR if TAG_SEPARATOR in value else ","
    return tuple(part.strip() for part in value.split(separator) if part.strip())


def _as_bool(value: str | bool | int | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return str(value or "").strip().lower() in _TRUE_VALUES


class RosterLoader:
    """Construit une liste de :class:`Person` depuis un CSV ou un JSON.

    L'ordre du fichier est conservé : c'est lui qui définit l'appariement
    positionnel avec les photos triées, et donc l'ordre d'affichage dans le PDF.
    """

    def __init__(self, *, tag_separator: str = TAG_SEPARATOR) -> None:
        self._tag_separator = tag_separator

    def load(self, path: Path | str) -> list[Person]:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(path)
        people = self.load_json(path) if path.suffix.lower() == ".json" else self.load_csv(path)
        info("%d personne(s) chargée(s) depuis %s", len(people), path.name)
        return people

    def load_csv(self, path: Path | str) -> list[Person]:
        path = Path(path)
        text = path.read_text(encoding="utf-8-sig")
        dialect = self._sniff(text)
        rows = list(csv.DictReader(text.splitlines(), dialect=dialect))
        if not rows:
            raise ValueError(f"aucune ligne de données dans {path}")
        return self.from_rows(rows)

    def load_json(self, path: Path | str) -> list[Person]:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("people") or data.get("personnes") or []
        if not isinstance(data, list):
            raise ValueError("le JSON doit être une liste d'objets")
        return self.from_rows(data)

    def from_rows(self, rows: Iterable[dict]) -> list[Person]:
        """Convertit des lignes déjà lues (dictionnaires) en personnes."""
        people: list[Person] = []
        for number, row in enumerate(rows, start=1):
            fields = {normalize_key(str(k)): v for k, v in row.items() if k is not None}
            person = self._build(fields, number)
            if person is not None:
                people.append(person)
        if not people:
            raise ValueError("aucune personne exploitable : une colonne 'nom' est-elle présente ?")
        return people

    def _build(self, fields: dict, number: int) -> Person | None:
        last_name = self._pick(fields, "last_name")
        first_name = self._pick(fields, "first_name")
        if not last_name and not first_name:
            warning("ligne %d ignorée : ni nom ni prénom", number)
            return None
        if not last_name:
            last_name, first_name = first_name, ""

        return Person(
            last_name=str(last_name).strip(),
            first_name=str(first_name or "").strip(),
            tags=self._tags(fields, "tags"),
            groups=self._tags(fields, "groups"),
            badge=_as_bool(self._pick(fields, "badge")),
        )

    def _pick(self, fields: dict, key: str) -> str | None:
        for alias in _ALIASES[key]:
            value = fields.get(alias)
            if value not in (None, ""):
                return value
        return None

    def _tags(self, fields: dict, key: str) -> tuple[str, ...]:
        value = self._pick(fields, key)
        if isinstance(value, list | tuple):
            return tuple(str(v).strip() for v in value if str(v).strip())
        separator = self._tag_separator
        if not value:
            return ()
        text = str(value)
        chosen = separator if separator in text else ","
        return tuple(part.strip() for part in text.split(chosen) if part.strip())

    @staticmethod
    def _sniff(text: str) -> type[csv.Dialect] | csv.Dialect:
        sample = "\n".join(text.splitlines()[:5])
        try:
            return csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            return csv.excel


def load_roster(path: Path | str) -> list[Person]:
    """Raccourci sur :meth:`RosterLoader.load`."""
    return RosterLoader().load(path)


def load_sqlite(
    database: Path | str, query: str, params: Sequence = (), *, tag_separator: str = TAG_SEPARATOR
) -> list[Person]:
    """Charge une liste depuis une base SQLite, via une requête libre.

    Les colonnes du résultat sont interprétées comme celles d'un CSV : nommez-les,
    au besoin avec ``AS``, parmi les alias reconnus (``nom``, ``prenom``, ``tags``,
    ``groupes``, ``badge``). Toute autre colonne est ignorée, ce qui permet de
    pointer une base existante sans la modifier.

    L'ordre de la requête est conservé : c'est lui qui définit l'appariement
    positionnel avec les photos, donc l'ordre d'affichage. Pensez à un ``ORDER BY``
    — et, pour des noms français, voyez :func:`remove_accents`, l'ordre SQL plaçant
    « Étienne » après « Zola ».

    >>> load_sqlite("base.db", "SELECT nom, prenom FROM eleves ORDER BY nom")
    """
    database = Path(database)
    if not database.exists():
        raise FileNotFoundError(database)

    # Ouverture en lecture seule : ce paquet ne doit jamais écrire dans la base
    # de quelqu'un d'autre.
    uri = f"file:{database.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = [dict(row) for row in connection.execute(query, params)]

    people = RosterLoader(tag_separator=tag_separator).from_rows(rows)
    info("%d personne(s) chargée(s) depuis %s", len(people), database.name)
    return people


def write_template(path: Path | str, *, rows: Sequence[str] = ()) -> Path:
    """Écrit un CSV d'exemple, pour démarrer sans deviner le format."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["nom", "prenom", "tags", "groupes", "badge"])
        if rows:
            for name in rows:
                writer.writerow([name, "", "", "", ""])
        else:
            writer.writerow(["DUPONT", "Marie", "LV2 ALL;Spé Maths", "Gr1;Tr3", "1"])
            writer.writerow(["MARTIN", "Paul", "LV2 ESP", "Gr2;Tr1", ""])
    return path
