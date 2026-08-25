"""Tests de la pagination et du rendu PDF.

La pagination est testée en isolation, sans ReportLab : c'est de l'arithmétique
sur des indices, donc elle se prête à des assertions exactes plutôt qu'à des
comparaisons d'images.
"""

from pathlib import Path

import pytest
from pypdf import PdfReader

from trombinoscope.models import GridConfig, Person
from trombinoscope.pdf.grid import GridPaginator, TrombiRenderer, centered_columns, render_pdf


def many(count: int) -> list[Person]:
    return [Person(f"NOM{i:02d}", f"Prenom{i:02d}") for i in range(count)]


class TestCenteredColumns:
    @pytest.mark.parametrize(
        "count,columns,expected",
        [
            (5, 5, [0, 1, 2, 3, 4]),  # ligne pleine
            (3, 5, [1, 2, 3]),  # parités identiques → bloc contigu centré
            (1, 5, [2]),  # centré sur la colonne médiane
            (2, 6, [2, 3]),  # parités identiques, colonnes paires
            (4, 6, [1, 2, 3, 4]),
            (2, 5, [1, 3]),  # colonne médiane laissée vide pour rester symétrique
            (4, 7, [1, 2, 4, 5]),
            (3, 6, [1, 2, 3]),  # aucune disposition symétrique : au mieux
        ],
    )
    def test_positions(self, count: int, columns: int, expected: list[int]):
        assert centered_columns(count, columns) == expected

    @pytest.mark.parametrize("count,columns", [(1, 5), (3, 5), (2, 5), (2, 6), (4, 6), (4, 7)])
    def test_layout_is_symmetric_when_parity_allows(self, count: int, columns: int):
        """Somme des positions = count × (columns−1)/2 si et seulement si c'est centré."""
        positions = centered_columns(count, columns)
        assert sum(positions) == pytest.approx(count * (columns - 1) / 2)

    def test_more_items_than_columns_fills_the_row(self):
        assert centered_columns(9, 5) == [0, 1, 2, 3, 4]

    def test_positions_are_unique(self):
        for columns in range(1, 9):
            for count in range(1, columns + 1):
                positions = centered_columns(count, columns)
                assert len(set(positions)) == len(positions) == count
                assert all(0 <= p < columns for p in positions)


class TestGridPaginator:
    @pytest.fixture
    def paginator(self) -> GridPaginator:
        return GridPaginator(GridConfig(columns=5))

    def test_single_page(self, paginator):
        pages = paginator.paginate(many(12), rows_per_page=3)
        assert len(pages) == 1
        assert len(pages[0].cells) == 12

    def test_splits_across_pages(self, paginator):
        pages = paginator.paginate(many(37), rows_per_page=3)
        assert [len(p.cells) for p in pages] == [15, 15, 7]

    def test_every_person_appears_exactly_once(self, paginator):
        people = many(37)
        placed = [cell.person for page in paginator.paginate(people, 3) for cell in page.cells]
        assert placed == people

    def test_no_two_cells_share_a_position(self, paginator):
        for page in paginator.paginate(many(37), 3):
            positions = [(c.row, c.column) for c in page.cells]
            assert len(set(positions)) == len(positions)

    def test_page_numbers_are_sequential(self, paginator):
        assert [p.number for p in paginator.paginate(many(37), 3)] == [1, 2, 3]

    def test_last_row_of_the_last_page_is_centered(self, paginator):
        """8 personnes, 5 colonnes : la dernière ligne en compte 3, centrées."""
        page = paginator.paginate(many(8), rows_per_page=3)[0]
        last = sorted(c.column for c in page.cells if c.row == 1)
        assert last == [1, 2, 3]

    def test_full_pages_are_not_centered(self, paginator):
        """Seule la dernière ligne d'une page incomplète est recentrée."""
        pages = paginator.paginate(many(18), rows_per_page=3)
        first_page_last_row = sorted(c.column for c in pages[0].cells if c.row == 2)
        assert first_page_last_row == [0, 1, 2, 3, 4]

    def test_centering_can_be_disabled(self):
        page = GridPaginator(GridConfig(columns=5, center_last_row=False)).paginate(many(8), 3)[0]
        assert sorted(c.column for c in page.cells if c.row == 1) == [0, 1, 2]

    def test_empty_roster_gives_one_empty_page(self, paginator):
        pages = paginator.paginate([], rows_per_page=3)
        assert len(pages) == 1 and pages[0].cells == []

    def test_zero_rows_per_page_is_a_clear_error(self, paginator):
        with pytest.raises(ValueError, match="hauteur disponible"):
            paginator.paginate(many(5), rows_per_page=0)

    @pytest.mark.parametrize("columns", [1, 2, 3, 4, 5, 7])
    @pytest.mark.parametrize("count", [1, 2, 5, 13, 31])
    def test_all_shapes_place_everyone(self, columns: int, count: int):
        pages = GridPaginator(GridConfig(columns=columns)).paginate(many(count), 4)
        assert sum(len(p.cells) for p in pages) == count


class TestTrombiRenderer:
    def test_produces_a_readable_pdf(self, tmp_path, people):
        path = render_pdf(people, tmp_path / "t.pdf", title="Ma classe")
        reader = PdfReader(path)
        assert len(reader.pages) == 1
        assert "Ma classe" in reader.pages[0].extract_text()

    def test_every_name_appears(self, tmp_path, people):
        path = render_pdf(people, tmp_path / "t.pdf", config=GridConfig(columns=3))
        text = PdfReader(path).pages[0].extract_text()
        for person in people:
            assert person.last_name in text

    def test_tags_and_groups_appear(self, tmp_path, people):
        path = render_pdf(people, tmp_path / "t.pdf")
        text = PdfReader(path).pages[0].extract_text()
        assert "Maths" in text and "Gr1" in text

    def test_tags_can_be_hidden(self, tmp_path, people):
        path = render_pdf(people, tmp_path / "t.pdf", config=GridConfig(show_tags=False))
        assert "Maths" not in PdfReader(path).pages[0].extract_text()

    def test_groups_can_be_hidden(self, tmp_path, people):
        path = render_pdf(people, tmp_path / "t.pdf", config=GridConfig(show_groups=False))
        assert "Gr1" not in PdfReader(path).pages[0].extract_text()

    def test_missing_portraits_fall_back_to_the_placeholder(self, tmp_path, people):
        """Aucune personne n'a de portrait ici : le rendu doit quand même aboutir."""
        assert all(p.portrait is None for p in people)
        assert render_pdf(people, tmp_path / "t.pdf").exists()

    def test_paginates_a_large_roster(self, tmp_path):
        path = render_pdf(many(60), tmp_path / "t.pdf", config=GridConfig(columns=5))
        assert len(PdfReader(path).pages) >= 2

    def test_landscape_swaps_the_page_dimensions(self, tmp_path, people):
        portrait = PdfReader(render_pdf(people, tmp_path / "p.pdf")).pages[0].mediabox
        paysage = (
            PdfReader(render_pdf(people, tmp_path / "l.pdf", config=GridConfig(landscape=True)))
            .pages[0]
            .mediabox
        )
        assert portrait.width < portrait.height
        assert paysage.width > paysage.height

    def test_markup_characters_in_names_are_escaped(self, tmp_path):
        """Un nom contenant « & » ou « < » doit traverser le balisage de ReportLab."""
        path = render_pdf([Person("DUPONT & FILS", "<Jean>")], tmp_path / "t.pdf")
        assert "DUPONT & FILS" in PdfReader(path).pages[0].extract_text()

    def test_metadata_carries_the_title(self, tmp_path, people):
        path = render_pdf(people, tmp_path / "t.pdf", title="Promo 2026")
        assert PdfReader(path).metadata.title == "Promo 2026"

    def test_footer_is_present(self, tmp_path, people):
        path = render_pdf(people, tmp_path / "t.pdf")
        assert "Version du" in PdfReader(path).pages[0].extract_text()

    def test_missing_logo_is_ignored(self, tmp_path, people):
        renderer = TrombiRenderer(GridConfig(), logo=Path("inexistant.png"))
        assert renderer.render(people, tmp_path / "t.pdf").exists()


class TestAnnotationLayout:
    """Les deux dispositions d'annotations doivent produire un PDF lisible."""

    @pytest.fixture
    def person(self) -> Person:
        return Person("HOPPER", "Grace", tags=("SI", "ANG"), groups=("Gr1", "Tr3"), badge=True)

    @pytest.mark.parametrize("layout", ["gutters", "left"])
    def test_both_layouts_keep_the_text(self, tmp_path, person, layout: str):
        path = render_pdf([person], tmp_path / "t.pdf", config=GridConfig(annotation_layout=layout))
        text = PdfReader(path).pages[0].extract_text()
        assert "SI, ANG" in text and "Gr1, Tr3" in text

    def test_layouts_place_the_groups_differently(self, tmp_path, person):
        gutters = render_pdf(
            [person], tmp_path / "g.pdf", config=GridConfig(annotation_layout="gutters")
        ).read_bytes()
        left = render_pdf(
            [person], tmp_path / "l.pdf", config=GridConfig(annotation_layout="left")
        ).read_bytes()
        assert gutters != left

    @pytest.mark.parametrize("corner", ["top-right", "bottom-right", "top-left", "bottom-left"])
    def test_every_badge_corner_renders(self, tmp_path, person, corner: str):
        path = render_pdf([person], tmp_path / "t.pdf", config=GridConfig(badge_corner=corner))
        assert path.exists()

    def test_unknown_layout_is_rejected(self):
        with pytest.raises(ValueError, match="annotation_layout"):
            GridConfig(annotation_layout="milieu")

    def test_unknown_badge_corner_is_rejected(self):
        with pytest.raises(ValueError, match="badge_corner"):
            GridConfig(badge_corner="centre")


class TestLogoAndBadgePlacement:
    @pytest.fixture
    def logo(self, tmp_path) -> Path:
        import cv2
        import numpy as np

        path = tmp_path / "logo.png"
        cv2.imwrite(str(path), np.full((60, 90, 3), 30, dtype=np.uint8))
        return path

    @pytest.mark.parametrize("position", ["top-right", "bottom-right", "top-left", "bottom-left"])
    def test_every_logo_position_renders(self, tmp_path, people, logo, position: str):
        renderer = TrombiRenderer(GridConfig(logo_position=position), logo=logo)
        assert renderer.render(people, tmp_path / f"{position}.pdf").exists()

    def test_logo_offset_moves_the_logo(self, tmp_path, people, logo):
        plain = (
            TrombiRenderer(GridConfig(), logo=logo).render(people, tmp_path / "a.pdf").read_bytes()
        )
        shifted = (
            TrombiRenderer(GridConfig(logo_offset=(0.0, 5.0)), logo=logo)
            .render(people, tmp_path / "b.pdf")
            .read_bytes()
        )
        assert plain != shifted

    def test_logo_can_be_hidden(self, tmp_path, people, logo):
        with_logo = (
            TrombiRenderer(GridConfig(), logo=logo)
            .render(people, tmp_path / "a.pdf")
            .stat()
            .st_size
        )
        without = (
            TrombiRenderer(GridConfig(show_logo=False), logo=logo)
            .render(people, tmp_path / "b.pdf")
            .stat()
            .st_size
        )
        assert without < with_logo

    def test_badge_inset_moves_the_star(self, tmp_path):
        person = Person("HOPPER", "Grace", badge=True)
        centred = render_pdf(
            [person], tmp_path / "a.pdf", config=GridConfig(badge_inset=0.0)
        ).read_bytes()
        inset = render_pdf(
            [person], tmp_path / "b.pdf", config=GridConfig(badge_inset=2.0)
        ).read_bytes()
        assert centred != inset

    def test_unknown_logo_position_is_rejected(self):
        with pytest.raises(ValueError, match="logo_position"):
            GridConfig(logo_position="milieu")
