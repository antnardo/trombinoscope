"""Tests de l'interface en ligne de commande."""

from pathlib import Path

import pytest
from pypdf import PdfReader

from trombinoscope.cli import _options_from, _parse_picks, build_parser, main
from trombinoscope.roster import load_roster


def parse(*argv: str):
    return build_parser().parse_args(["build", "photos", "r.csv", *argv])


class TestParsePicks:
    def test_single_entry(self):
        assert _parse_picks(["HOPPER=1"]) == {"HOPPER": 1}

    def test_multiple_entries(self):
        assert _parse_picks(["A=0", "B=2"]) == {"A": 0, "B": 2}

    def test_negative_index(self):
        assert _parse_picks(["A=-1"]) == {"A": -1}

    def test_surrounding_spaces_are_trimmed(self):
        assert _parse_picks([" A =1"]) == {"A": 1}

    def test_missing_equals_is_rejected(self):
        with pytest.raises(ValueError, match="NOM=INDEX"):
            _parse_picks(["HOPPER"])

    def test_non_integer_index_is_rejected(self):
        with pytest.raises(ValueError, match="entier"):
            _parse_picks(["HOPPER=premier"])


class TestOptionMapping:
    def test_defaults_are_sane(self):
        options = _options_from(parse())
        assert options.grid.columns == 5
        assert options.framing.face_ratio == 0.55
        assert options.color.white_balance == "shades-of-gray"
        assert options.color.harmonize_batch is True

    def test_negative_flags_invert_the_config(self):
        options = _options_from(
            parse(
                "--no-harmonize", "--no-tags", "--no-groups", "--no-badges", "--no-center-last-row"
            )
        )
        assert options.color.harmonize_batch is False
        assert (options.grid.show_tags, options.grid.show_groups) == (False, False)
        assert options.grid.show_badges is False
        assert options.grid.center_last_row is False

    def test_auto_levels_zero_disables_it(self):
        assert _options_from(parse("--auto-levels", "0")).color.auto_levels_clip is None

    def test_auto_levels_value_is_kept(self):
        assert _options_from(parse("--auto-levels", "1.5")).color.auto_levels_clip == 1.5

    def test_framing_flags(self):
        options = _options_from(
            parse(
                "--face-ratio",
                "0.4",
                "--aspect-ratio",
                "1.5",
                "--portrait-width",
                "500",
                "--align-eyes",
            )
        )
        assert options.framing.face_ratio == 0.4
        assert options.framing.aspect_ratio == 1.5
        assert options.framing.width == 500
        assert options.framing.align_eyes is True

    def test_absent_accepts_several_names(self):
        assert _options_from(parse("--absent", "A", "B")).absent == ("A", "B")

    def test_invalid_config_is_caught_at_construction(self):
        with pytest.raises(ValueError, match="face_ratio"):
            _options_from(parse("--face-ratio", "2.0"))


class TestParserRejections:
    def test_command_is_required(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_unknown_backend_is_rejected(self):
        with pytest.raises(SystemExit):
            parse("--backend", "dlib")

    def test_unknown_white_balance_is_rejected(self):
        with pytest.raises(SystemExit):
            parse("--white-balance", "magique")


class TestTemplateCommand:
    def test_writes_a_loadable_file(self, tmp_path, capsys):
        target = tmp_path / "modele.csv"
        assert main(["template", str(target)]) == 0
        assert len(load_roster(target)) == 2
        assert "Modèle écrit" in capsys.readouterr().out


class TestBuildCommand:
    def test_produces_the_pdf_even_without_detected_faces(
        self, tmp_path, photo_dir, roster_csv, capsys
    ):
        """Les images synthétiques ne contiennent pas de vrai visage.

        Le PDF doit malgré tout sortir — chaque photo est simplement mise au format
        sans recadrage — et le code de retour doit signaler le problème plutôt que
        de le taire.
        """
        output = tmp_path / "out.pdf"
        code = main(
            [
                "build",
                str(photo_dir),
                str(roster_csv),
                "-o",
                str(output),
                "--title",
                "CLI",
                "--columns",
                "3",
            ]
        )
        assert code == 1
        assert "CLI" in PdfReader(output).pages[0].extract_text()
        assert str(output) in capsys.readouterr().out

    @pytest.mark.integration
    def test_end_to_end_on_real_portraits(self, tmp_path, sample_photos: list[Path], capsys):
        output = tmp_path / "out.pdf"
        roster = tmp_path / "r.csv"
        roster.write_text(
            "nom\n" + "\n".join(p.stem.upper() for p in sample_photos) + "\n", encoding="utf-8"
        )
        code = main(
            [
                "build",
                str(sample_photos[0].parent),
                str(roster),
                "-o",
                str(output),
                "--title",
                "Pionniers",
                "--columns",
                "4",
                "--align-eyes",
            ]
        )
        assert code == 0
        assert "Pionniers" in PdfReader(output).pages[0].extract_text()

    def test_returns_one_when_something_is_missing(self, tmp_path, photo_dir, capsys):
        roster = tmp_path / "r.csv"
        roster.write_text("nom\n" + "\n".join(f"P{i}" for i in range(9)), encoding="utf-8")
        code = main(["build", str(photo_dir), str(roster), "-o", str(tmp_path / "o.pdf")])
        assert code == 1

    def test_missing_folder_returns_two(self, tmp_path, roster_csv):
        code = main(
            ["build", str(tmp_path / "absent"), str(roster_csv), "-o", str(tmp_path / "o.pdf")]
        )
        assert code == 2

    def test_missing_roster_returns_two(self, tmp_path, photo_dir):
        code = main(
            ["build", str(photo_dir), str(tmp_path / "absent.csv"), "-o", str(tmp_path / "o.pdf")]
        )
        assert code == 2

    def test_bad_pick_returns_two(self, tmp_path, photo_dir, roster_csv):
        code = main(
            [
                "build",
                str(photo_dir),
                str(roster_csv),
                "-o",
                str(tmp_path / "o.pdf"),
                "--pick",
                "nawak",
            ]
        )
        assert code == 2

    def test_portraits_go_where_asked(self, tmp_path, photo_dir, roster_csv):
        main(
            [
                "build",
                str(photo_dir),
                str(roster_csv),
                "-o",
                str(tmp_path / "o.pdf"),
                "--portraits",
                str(tmp_path / "pp"),
            ]
        )
        assert list((tmp_path / "pp").glob("*.jpg"))


class TestInspectCommand:
    def test_writes_annotated_images(self, tmp_path, photo_dir, capsys):
        code = main(["inspect", str(photo_dir), "-o", str(tmp_path / "det")])
        # Les photos synthétiques ne contiennent pas de vrai visage : le code de
        # retour signale le problème, ce qui est le comportement attendu.
        assert code == 1
        assert len(list((tmp_path / "det").glob("*.detections.jpg"))) == 5
        assert "visage(s)" in capsys.readouterr().out

    @pytest.mark.integration
    def test_returns_zero_on_real_portraits(self, tmp_path, sample_photos: list[Path]):
        folder = sample_photos[0].parent
        assert main(["inspect", str(folder), "-o", str(tmp_path / "det")]) == 0


class TestVersion:
    def test_version_flag_exits_cleanly(self, capsys):
        with pytest.raises(SystemExit) as exit_info:
            build_parser().parse_args(["--version"])
        assert exit_info.value.code == 0
        assert "trombinoscope" in capsys.readouterr().out
