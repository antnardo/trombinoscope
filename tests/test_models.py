"""Tests des structures de données et de l'appariement positionnel."""

from pathlib import Path

import pytest

from trombinoscope.models import (
    Box,
    BuildReport,
    ColorConfig,
    FramingConfig,
    GridConfig,
    Person,
    positional_match,
)

from .conftest import landmarks_for


class TestBox:
    def test_dimensions(self):
        box = Box(10, 20, 40, 60)
        assert (box.width, box.height, box.area) == (30, 40, 1200)

    def test_center(self):
        assert Box(0, 0, 10, 20).center == (5.0, 10.0)

    @pytest.mark.parametrize("args", [(10, 10, 10, 20), (10, 10, 20, 10), (10, 10, 5, 5)])
    def test_degenerate_box_is_rejected(self, args):
        with pytest.raises(ValueError, match="dégénérée"):
            Box(*args)

    def test_scaled_keeps_the_center(self):
        box = Box(10, 10, 30, 50)
        assert Box.center.fget(box.scaled(0.5)) == box.center

    def test_scaled_shrinks_dimensions(self):
        scaled = Box(0, 0, 40, 40).scaled(0.5)
        assert (scaled.width, scaled.height) == (20, 20)

    def test_clipped_stays_inside_the_image(self):
        clipped = Box(-20, -30, 500, 900).clipped(100, 200)
        assert (clipped.x0, clipped.y0, clipped.x1, clipped.y1) == (0, 0, 100, 200)

    def test_from_xywh_rounds(self):
        assert Box.from_xywh(10.4, 20.6, 30.5, 40.5) == Box(10, 21, 41, 61)

    def test_is_hashable(self):
        assert len({Box(0, 0, 10, 10), Box(0, 0, 10, 10)}) == 1


class TestLandmarks:
    def test_level_eyes_give_zero_angle(self):
        assert landmarks_for(Box(0, 0, 100, 130)).eye_angle_deg == pytest.approx(0.0, abs=1e-6)

    def test_tilted_eyes_give_a_positive_angle(self):
        assert landmarks_for(Box(0, 0, 100, 130), tilt=0.1).eye_angle_deg > 0

    def test_eye_center_is_between_the_eyes(self):
        marks = landmarks_for(Box(0, 0, 100, 130))
        assert marks.eye_center[0] == pytest.approx(50.0)


class TestPerson:
    def test_display_name_joins_both_parts(self):
        assert Person("HOPPER", "Grace").display_name == "HOPPER Grace"

    def test_display_name_without_first_name(self):
        assert Person("HOPPER").display_name == "HOPPER"

    def test_with_portrait_returns_a_copy(self):
        original = Person("KNUTH", "Donald")
        updated = original.with_portrait(Path("k.jpg"))
        assert original.portrait is None
        assert updated.portrait == Path("k.jpg")


class TestConfigValidation:
    @pytest.mark.parametrize("value", [0.0, -0.1, 1.5])
    def test_face_ratio_must_be_in_range(self, value: float):
        with pytest.raises(ValueError, match="face_ratio"):
            FramingConfig(face_ratio=value)

    @pytest.mark.parametrize("value", [-0.1, 1.1])
    def test_face_y_must_be_in_range(self, value: float):
        with pytest.raises(ValueError, match="face_y"):
            FramingConfig(face_y=value)

    def test_width_must_be_positive(self):
        with pytest.raises(ValueError, match="width"):
            FramingConfig(width=0)

    def test_height_follows_the_aspect_ratio(self):
        assert FramingConfig(width=300, aspect_ratio=4 / 3).height == 400

    def test_columns_must_be_at_least_one(self):
        with pytest.raises(ValueError, match="columns"):
            GridConfig(columns=0)

    @pytest.mark.parametrize("value", [-0.1, 1.0, 2.0])
    def test_column_padding_must_be_in_range(self, value: float):
        with pytest.raises(ValueError, match="column_padding"):
            GridConfig(column_padding=value)

    def test_default_color_config_harmonizes(self):
        assert ColorConfig().harmonize_batch is True


class TestPositionalMatch:
    @pytest.fixture
    def photos(self) -> list[Path]:
        return [Path(f"{i}.jpg") for i in range(1, 6)]

    def test_pairs_in_order(self, people, photos):
        pairs, _, _ = positional_match(people, photos)
        assert [p.last_name for p, _ in pairs] == [p.last_name for p in people]

    def test_absent_people_are_skipped(self, people, photos):
        pairs, _, extra = positional_match(people, photos[:4], absent=["JOHNSON"])
        assert [p.last_name for p, _ in pairs] == ["HOPPER", "PERLMAN", "KNUTH", "KAY"]
        assert extra == []

    def test_absent_matching_is_case_insensitive(self, people, photos):
        pairs, _, _ = positional_match(people, photos, absent=["johnson"])
        assert "JOHNSON" not in [p.last_name for p, _ in pairs]

    def test_missing_photos_are_reported(self, people, photos):
        _, missing, _ = positional_match(people, photos[:2])
        assert missing == ["PERLMAN", "KNUTH", "KAY"]

    def test_extra_photos_are_reported(self, people, photos):
        _, _, extra = positional_match(people[:2], photos)
        assert len(extra) == 3

    def test_alignment_survives_a_shorter_photo_list(self, people, photos):
        """Manquer de photos tronque l'appariement, sans décaler ce qui précède."""
        pairs, _, _ = positional_match(people, photos[:3])
        assert all(
            person.last_name == expected.last_name
            for (person, _), expected in zip(pairs, people[:3], strict=True)
        )


class TestBuildReport:
    def test_ok_when_nothing_went_wrong(self):
        assert BuildReport(people=[Person("A")], photos=[Path("a.jpg")]).ok

    def test_not_ok_when_a_face_is_missing(self):
        assert not BuildReport(no_face=[Path("a.jpg")]).ok

    def test_summary_mentions_every_problem(self):
        report = BuildReport(
            people=[Person("A")],
            photos=[Path("a.jpg")],
            no_face=[Path("a.jpg")],
            multiple_faces=[Path("b.jpg")],
            unmatched_people=["B"],
            unmatched_photos=[Path("c.jpg")],
        )
        summary = report.summary()
        for fragment in ("sans visage", "plusieurs visages", "sans photo", "sans personne"):
            assert fragment in summary
