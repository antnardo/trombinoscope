"""Tests du chargement de la liste des personnes."""

import json
from pathlib import Path

import pytest

from trombinoscope.roster import (
    RosterLoader,
    load_roster,
    load_sqlite,
    normalize_key,
    remove_accents,
    write_template,
)


@pytest.fixture
def loader() -> RosterLoader:
    return RosterLoader()


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


class TestNormalization:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Prénom", "prenom"),
            ("NOM", "nom"),
            ("Groupe de colle", "groupe_de_colle"),
            ("first-name", "first_name"),
            ("  Tags  ", "tags"),
        ],
    )
    def test_normalize_key(self, raw: str, expected: str):
        assert normalize_key(raw) == expected

    @pytest.mark.parametrize(
        "raw,expected", [("Élève", "Eleve"), ("Noël", "Noel"), ("çà", "ca"), ("abc", "abc")]
    )
    def test_remove_accents(self, raw: str, expected: str):
        assert remove_accents(raw) == expected


class TestCsvLoading:
    def test_minimal_csv_with_only_names(self, loader, tmp_path):
        path = write(tmp_path / "r.csv", "nom\nHOPPER\nKNUTH\n")
        people = loader.load(path)
        assert [p.last_name for p in people] == ["HOPPER", "KNUTH"]

    def test_full_csv(self, loader, tmp_path):
        path = write(
            tmp_path / "r.csv",
            "nom,prenom,tags,groupes,badge\nHOPPER,Grace,Maths;Info,Gr1;Tr2,1\n",
        )
        person = loader.load(path)[0]
        assert (person.last_name, person.first_name) == ("HOPPER", "Grace")
        assert person.tags == ("Maths", "Info")
        assert person.groups == ("Gr1", "Tr2")
        assert person.badge is True

    def test_accented_headers_are_recognized(self, loader, tmp_path):
        path = write(tmp_path / "r.csv", "Nom,Prénom\nHOPPER,Grace\n")
        assert loader.load(path)[0].first_name == "Grace"

    def test_english_headers_are_recognized(self, loader, tmp_path):
        path = write(tmp_path / "r.csv", "last_name,first_name\nHOPPER,Grace\n")
        assert loader.load(path)[0].first_name == "Grace"

    def test_semicolon_delimited_file(self, loader, tmp_path):
        path = write(tmp_path / "r.csv", "nom;prenom\nHOPPER;Grace\n")
        assert loader.load(path)[0].first_name == "Grace"

    def test_tab_delimited_file(self, loader, tmp_path):
        path = write(tmp_path / "r.csv", "nom\tprenom\nHOPPER\tGrace\n")
        assert loader.load(path)[0].first_name == "Grace"

    def test_bom_is_stripped(self, loader, tmp_path):
        """Un export Excel commence par un BOM UTF-8, qui collait à la première colonne."""
        path = tmp_path / "r.csv"
        path.write_bytes("nom,prenom\nHOPPER,Grace\n".encode("utf-8-sig"))
        assert loader.load(path)[0].last_name == "HOPPER"

    def test_comma_inside_a_cell_still_splits_tags(self, loader, tmp_path):
        path = write(tmp_path / "r.csv", 'nom,tags\nHOPPER,"Maths, Info"\n')
        assert loader.load(path)[0].tags == ("Maths", "Info")

    def test_unknown_columns_are_ignored(self, loader, tmp_path):
        path = write(tmp_path / "r.csv", "nom,ine,classe\nHOPPER,12345,MP2\n")
        assert loader.load(path)[0].last_name == "HOPPER"

    def test_order_is_preserved(self, loader, tmp_path):
        names = ["ZOLA", "ARAGON", "MOLIERE"]
        path = write(tmp_path / "r.csv", "nom\n" + "\n".join(names) + "\n")
        assert [p.last_name for p in loader.load(path)] == names

    def test_first_name_only_becomes_the_last_name(self, loader, tmp_path):
        path = write(tmp_path / "r.csv", "nom,prenom\n,Grace\n")
        assert loader.load(path)[0].last_name == "Grace"

    def test_blank_rows_are_skipped(self, loader, tmp_path):
        path = write(tmp_path / "r.csv", "nom,prenom\nHOPPER,Grace\n,\nKNUTH,Donald\n")
        assert len(loader.load(path)) == 2

    @pytest.mark.parametrize(
        "value,expected",
        [
            ("1", True),
            ("oui", True),
            ("VRAI", True),
            ("x", True),
            ("0", False),
            ("", False),
            ("non", False),
        ],
    )
    def test_badge_values(self, loader, tmp_path, value: str, expected: bool):
        path = write(tmp_path / "r.csv", f"nom,badge\nHOPPER,{value}\n")
        assert loader.load(path)[0].badge is expected


class TestJsonLoading:
    def test_list_of_objects(self, loader, tmp_path):
        path = tmp_path / "r.json"
        path.write_text(
            json.dumps([{"nom": "HOPPER", "prenom": "Grace", "tags": ["Maths"]}]), encoding="utf-8"
        )
        person = loader.load(path)[0]
        assert person.last_name == "HOPPER"
        assert person.tags == ("Maths",)

    def test_wrapped_in_a_people_key(self, loader, tmp_path):
        path = tmp_path / "r.json"
        path.write_text(json.dumps({"people": [{"nom": "KNUTH"}]}), encoding="utf-8")
        assert loader.load(path)[0].last_name == "KNUTH"

    def test_scalar_json_is_rejected(self, loader, tmp_path):
        path = tmp_path / "r.json"
        path.write_text(json.dumps(42), encoding="utf-8")
        with pytest.raises(ValueError, match="liste"):
            loader.load(path)


class TestErrors:
    def test_missing_file(self, loader):
        with pytest.raises(FileNotFoundError):
            loader.load("nulle-part.csv")

    def test_header_only_file(self, loader, tmp_path):
        path = write(tmp_path / "r.csv", "nom,prenom\n")
        with pytest.raises(ValueError, match="aucune ligne"):
            loader.load(path)

    def test_file_without_a_name_column(self, loader, tmp_path):
        path = write(tmp_path / "r.csv", "ine,classe\n12345,MP2\n")
        with pytest.raises(ValueError, match="nom"):
            loader.load(path)


class TestTemplate:
    def test_template_is_reloadable(self, tmp_path):
        """Le modèle proposé doit passer le chargeur : sinon il induit en erreur."""
        path = write_template(tmp_path / "modele.csv")
        people = load_roster(path)
        assert len(people) == 2
        assert people[0].tags == ("LV2 ALL", "Spé Maths")

    def test_template_accepts_a_list_of_names(self, tmp_path):
        path = write_template(tmp_path / "m.csv", rows=["HOPPER", "KNUTH", "KAY"])
        assert [p.last_name for p in load_roster(path)] == ["HOPPER", "KNUTH", "KAY"]

    def test_template_creates_parent_directories(self, tmp_path):
        path = write_template(tmp_path / "a" / "b" / "m.csv")
        assert path.exists()


class TestSqliteLoading:
    @pytest.fixture
    def database(self, tmp_path: Path) -> Path:
        import sqlite3

        path = tmp_path / "base.db"
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE eleves (nom TEXT, prenom TEXT, cube INTEGER, "
                "option TEXT, LV1 TEXT, groupe INTEGER)"
            )
            connection.executemany(
                "INSERT INTO eleves VALUES (?, ?, ?, ?, ?, ?)",
                [
                    ("HOPPER", "Grace", 1, "SI", "ANG", 1),
                    ("KNUTH", "Donald", 0, "Info", "ALL", 2),
                ],
            )
        return path

    def test_reads_names_in_query_order(self, database):
        people = load_sqlite(database, "SELECT nom, prenom FROM eleves ORDER BY nom")
        assert [p.last_name for p in people] == ["HOPPER", "KNUTH"]

    def test_query_order_is_preserved(self, database):
        people = load_sqlite(database, "SELECT nom FROM eleves ORDER BY nom DESC")
        assert [p.last_name for p in people] == ["KNUTH", "HOPPER"]

    def test_aliases_map_business_columns(self, database):
        """Le schéma métier se traduit avec des AS, sans toucher à la base."""
        people = load_sqlite(
            database,
            "SELECT nom, prenom, cube AS badge, option || ';' || LV1 AS tags, "
            "'Gr' || groupe AS groupes FROM eleves ORDER BY nom",
        )
        assert people[0].tags == ("SI", "ANG")
        assert people[0].groups == ("Gr1",)
        assert people[0].badge is True
        assert people[1].badge is False

    def test_parameters_are_bound(self, database):
        people = load_sqlite(database, "SELECT nom FROM eleves WHERE groupe = ?", (2,))
        assert [p.last_name for p in people] == ["KNUTH"]

    def test_missing_database_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_sqlite(tmp_path / "absente.db", "SELECT 1")

    def test_database_is_opened_read_only(self, database):
        """Le paquet ne doit jamais écrire dans la base de quelqu'un d'autre."""
        import sqlite3

        with pytest.raises(sqlite3.OperationalError):
            load_sqlite(database, "DELETE FROM eleves")
        assert len(load_sqlite(database, "SELECT nom FROM eleves")) == 2
