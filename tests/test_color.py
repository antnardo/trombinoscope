"""Tests du module couleur.

Trois familles :

* les **invariants mathématiques** — aller-retour sRGB, estimateurs qui retrouvent
  une dominante connue ;
* les **garde-fous d'API**, notamment sur les appels OpenCV dont la signature se
  prête aux erreurs ;
* la **propriété d'ensemble** qui justifie tout le module : l'harmonisation
  resserre la dispersion colorimétrique d'un lot.
"""

import cv2
import numpy as np
import pytest

from trombinoscope.color import (
    AutoLevels,
    BatchColorHarmonizer,
    GrayWorldEstimator,
    LuminanceMatcher,
    ShadesOfGrayEstimator,
    WhiteBalancer,
    WhitePatchEstimator,
    build_estimator,
    face_mask,
    linear_to_srgb,
    median_luminance,
    srgb_to_linear,
)
from trombinoscope.models import NO_COLOR, Box, ColorConfig

from .conftest import apply_cast, default_face_box, make_photo


class TestColorSpaces:
    def test_srgb_round_trip_is_identity(self):
        values = np.linspace(0, 1, 256, dtype=np.float32).reshape(1, -1, 1).repeat(3, axis=2)
        assert np.allclose(linear_to_srgb(srgb_to_linear(values)), values, atol=1e-4)

    @pytest.mark.parametrize("value,expected", [(0.0, 0.0), (1.0, 1.0), (0.5, 0.2140)])
    def test_srgb_to_linear_matches_reference_points(self, value: float, expected: float):
        result = srgb_to_linear(np.full((1, 1, 3), value, dtype=np.float32))
        assert result[0, 0, 0] == pytest.approx(expected, abs=1e-3)

    def test_linearization_is_monotonic(self):
        values = np.linspace(0, 1, 64, dtype=np.float32).reshape(1, -1, 1).repeat(3, axis=2)
        linear = srgb_to_linear(values)[0, :, 0]
        assert np.all(np.diff(linear) > 0)


class TestIlluminantEstimators:
    """Sur une image neutre, tout estimateur doit rendre un illuminant neutre."""

    @pytest.fixture
    def neutral(self) -> np.ndarray:
        rng = np.random.default_rng(0)
        return rng.integers(60, 200, size=(120, 120, 3), dtype=np.uint8)

    @pytest.mark.parametrize(
        "estimator",
        [GrayWorldEstimator(), ShadesOfGrayEstimator(p=6.0), WhitePatchEstimator(percentile=97.0)],
        ids=["grayworld", "shades-of-gray", "white-patch"],
    )
    def test_neutral_image_gives_neutral_illuminant(self, estimator, neutral):
        illuminant = estimator.estimate(srgb_to_linear(neutral.astype(np.float32) / 255))
        assert illuminant.max() - illuminant.min() < 0.03

    @pytest.mark.parametrize(
        "estimator",
        [GrayWorldEstimator(), ShadesOfGrayEstimator(p=6.0), WhitePatchEstimator(percentile=97.0)],
        ids=["grayworld", "shades-of-gray", "white-patch"],
    )
    def test_illuminant_is_unit_norm(self, estimator, neutral):
        illuminant = estimator.estimate(srgb_to_linear(neutral.astype(np.float32) / 255))
        assert float(np.linalg.norm(illuminant)) == pytest.approx(1.0, abs=1e-4)

    def test_red_cast_raises_red_component(self, neutral):
        cast = apply_cast(neutral, (0.85, 1.0, 1.15))  # BGR : plus de rouge
        illuminant = ShadesOfGrayEstimator().estimate(srgb_to_linear(cast.astype(np.float32) / 255))
        assert illuminant[2] > illuminant[0]

    def test_mask_restricts_the_estimate(self):
        """Un masque doit isoler la zone : un fond coloré ne doit plus compter.

        Le fond est volontairement non saturé : un canal à 255 serait écarté par le
        filtre anti-écrêtage de l'estimateur, et le test ne mesurerait plus rien.
        """
        image = np.full((100, 100, 3), 128, dtype=np.uint8)
        image[:, :50] = (210, 70, 60)  # moitié gauche franchement bleue
        box = Box(60, 40, 90, 70)  # entièrement dans la moitié droite, neutre
        mask = face_mask(image.shape, box)
        linear = srgb_to_linear(image.astype(np.float32) / 255)

        masked = GrayWorldEstimator().estimate(linear, mask)
        unmasked = GrayWorldEstimator().estimate(linear, None)
        assert masked.max() - masked.min() < unmasked.max() - unmasked.min()

    def test_p_equal_one_reduces_to_grayworld(self, neutral):
        linear = srgb_to_linear(neutral.astype(np.float32) / 255)
        assert np.allclose(
            ShadesOfGrayEstimator(p=1.0).estimate(linear),
            GrayWorldEstimator().estimate(linear),
            atol=1e-5,
        )

    def test_build_estimator_rejects_unknown_name(self):
        with pytest.raises(ValueError, match="inconnue"):
            build_estimator("magique")

    def test_build_estimator_none_disables(self):
        assert build_estimator("none") is None


class TestWhiteBalancer:
    @pytest.fixture
    def balancer(self) -> WhiteBalancer:
        return WhiteBalancer(ShadesOfGrayEstimator(p=6.0), max_gain=2.0)

    def test_corrects_a_known_cast(self, balancer):
        rng = np.random.default_rng(1)
        neutral = rng.integers(70, 190, size=(150, 150, 3), dtype=np.uint8)
        cast = apply_cast(neutral, (0.75, 1.0, 1.25))

        corrected = balancer.balance(cast)

        before = balancer.estimate(cast)
        after = balancer.estimate(corrected)
        assert after.max() - after.min() < before.max() - before.min()

    def test_gains_are_clamped(self, balancer):
        extreme = np.array([0.01, 0.5, 0.99], dtype=np.float32)
        gains = balancer.gains(extreme)
        assert gains.max() <= 2.0 + 1e-6
        assert gains.min() >= 0.5 - 1e-6

    def test_gains_preserve_overall_level(self, balancer):
        """La moyenne géométrique des gains vaut 1 : la teinte bouge, pas l'exposition."""
        gains = balancer.gains(np.array([0.3, 0.6, 0.75], dtype=np.float32))
        assert float(np.exp(np.mean(np.log(gains)))) == pytest.approx(1.0, abs=1e-5)

    def test_neutral_target_gives_unit_gains(self, balancer):
        neutral = np.full(3, 1 / np.sqrt(3), dtype=np.float32)
        assert np.allclose(balancer.gains(neutral), 1.0, atol=1e-5)

    def test_rejects_max_gain_below_one(self):
        with pytest.raises(ValueError, match="max_gain"):
            WhiteBalancer(GrayWorldEstimator(), max_gain=0.5)

    @pytest.mark.parametrize("strength", [-0.1, 1.5])
    def test_rejects_out_of_range_strength(self, strength: float):
        with pytest.raises(ValueError, match="strength"):
            WhiteBalancer(GrayWorldEstimator(), strength=strength)

    def test_zero_strength_disables_the_correction(self):
        balancer = WhiteBalancer(ShadesOfGrayEstimator(), strength=0.0)
        assert np.allclose(balancer.gains(np.array([0.3, 0.6, 0.75], dtype=np.float32)), 1.0)

    @pytest.mark.parametrize("strength", [0.25, 0.5, 0.75])
    def test_partial_strength_lies_between_identity_and_full(self, strength: float):
        illuminant = np.array([0.3, 0.6, 0.75], dtype=np.float32)
        full = WhiteBalancer(ShadesOfGrayEstimator(), strength=1.0).gains(illuminant)
        partial = WhiteBalancer(ShadesOfGrayEstimator(), strength=strength).gains(illuminant)
        # Sur le canal le plus corrigé, le gain partiel est plus proche de 1.
        channel = int(np.argmax(np.abs(np.log(full))))
        assert abs(np.log(partial[channel])) < abs(np.log(full[channel]))

    def test_partial_strength_still_preserves_the_overall_level(self):
        gains = WhiteBalancer(ShadesOfGrayEstimator(), strength=0.4).gains(
            np.array([0.3, 0.6, 0.75], dtype=np.float32)
        )
        assert float(np.exp(np.mean(np.log(gains)))) == pytest.approx(1.0, abs=1e-5)


class TestAutoLevels:
    def test_apply_actually_applies_the_gain(self):
        """Le gain doit être appliqué, pas absorbé par un paramètre de sortie.

        ``cv2.convertScaleAbs`` a pour signature ``(src, dst, alpha, beta)`` : un
        appel positionnel ``(image, alpha, beta)`` enverrait le gain dans ``dst``
        et le décalage de noir en position ``alpha``, sans lever d'erreur. Ce test
        échoue si les arguments nommés disparaissent.
        """
        image = np.full((4, 4, 3), 100, dtype=np.uint8)
        assert AutoLevels().apply(image, alpha=2.0, beta=0.0)[0, 0, 0] == 200

    def test_apply_adds_the_offset(self):
        image = np.full((4, 4, 3), 100, dtype=np.uint8)
        assert AutoLevels().apply(image, alpha=1.0, beta=25.0)[0, 0, 0] == 125

    def test_flat_image_is_left_alone(self):
        """Plage dynamique nulle : identité, et surtout pas de division par zéro."""
        flat = np.full((32, 32, 3), 240, dtype=np.uint8)
        assert AutoLevels().levels(flat) == (1.0, 0.0)
        assert np.array_equal(AutoLevels().transform(flat), flat)

    def test_stretches_a_compressed_histogram(self):
        image = np.linspace(100, 150, 64, dtype=np.uint8).reshape(8, 8, 1).repeat(3, axis=2)
        stretched = AutoLevels(clip_percent=0.0).transform(image)
        assert stretched.max() - stretched.min() > image.max() - image.min()

    def test_gain_is_bounded(self):
        image = np.linspace(120, 124, 64, dtype=np.uint8).reshape(8, 8, 1).repeat(3, axis=2)
        alpha, _ = AutoLevels(clip_percent=0.0, max_gain=3.0).levels(image)
        assert alpha <= 3.0

    @pytest.mark.parametrize("clip", [-1.0, 50.0, 80.0])
    def test_rejects_invalid_clip(self, clip: float):
        with pytest.raises(ValueError, match="clip_percent"):
            AutoLevels(clip)


class TestLuminanceMatcher:
    @pytest.fixture
    def matcher(self) -> LuminanceMatcher:
        return LuminanceMatcher()

    def test_brings_median_luminance_to_target(self, matcher):
        dark = np.full((64, 64, 3), 60, dtype=np.uint8)
        result = matcher.transform(dark, target=150.0)
        assert median_luminance(result) == pytest.approx(150.0, abs=6.0)

    def test_gamma_is_one_when_already_on_target(self, matcher):
        assert matcher.gamma_for(120.0, 120.0) == pytest.approx(1.0, abs=1e-6)

    def test_gamma_is_clamped(self, matcher):
        assert matcher.gamma_for(250.0, 5.0) <= 2.5
        assert matcher.gamma_for(5.0, 250.0) >= 0.4

    def test_correction_never_clips(self, matcher):
        """Le gamma est monotone : remonter une image sombre ne brûle pas les blancs."""
        image = np.linspace(0, 255, 256, dtype=np.uint8).reshape(16, 16, 1).repeat(3, axis=2)
        lifted = matcher.apply(image, gamma=0.5)
        assert lifted.max() == 255
        assert np.all(np.diff(np.sort(lifted.reshape(-1))) >= 0)


class TestBatchColorHarmonizer:
    """La propriété qui justifie le module : le lot devient cohérent."""

    @pytest.fixture
    def casts(self) -> list[tuple[float, float, float]]:
        return [(1.0, 1.0, 1.0), (1.3, 0.95, 0.8), (0.75, 1.0, 1.25), (1.15, 1.1, 0.9)]

    @pytest.fixture
    def batch(self, casts) -> list[np.ndarray]:
        base = make_photo(width=240, height=320)
        return [apply_cast(base, cast) for cast in casts]

    @staticmethod
    def _spread(images: list[np.ndarray], box: Box) -> tuple[float, float]:
        """Dispersion chromatique et dispersion de luminance d'un lot."""
        probe = BatchColorHarmonizer(ColorConfig())
        samples = [probe.measure(image, box) for image in images]
        illuminants = np.stack([s.illuminant for s in samples])
        chroma = illuminants / illuminants.sum(axis=1, keepdims=True)
        return float(chroma.std(axis=0).mean()), float(np.std([s.luminance for s in samples]))

    def test_reduces_chromatic_spread(self, batch):
        box = default_face_box(240, 320)
        harmonizer = BatchColorHarmonizer(ColorConfig())
        for image in batch:
            harmonizer.measure(image, box)
        corrected = [harmonizer.transform(image, box) for image in batch]

        before, _ = self._spread(batch, box)
        after, _ = self._spread(corrected, box)
        assert after < before * 0.7, f"dispersion chromatique {before:.4f} → {after:.4f}"

    def test_reduces_luminance_spread(self):
        """Bride levée : on teste ici l'alignement sur le lot, pas sa modération.

        Le défaut brime volontairement le déplacement des photos aberrantes ;
        c'est l'objet de :class:`TestMaxLuminanceShift`.
        """
        base = make_photo(width=240, height=320)
        box = default_face_box(240, 320)
        batch = [
            np.clip(base.astype(np.float32) * factor, 0, 255).astype(np.uint8)
            for factor in (0.6, 0.85, 1.0, 1.2)
        ]
        harmonizer = BatchColorHarmonizer(ColorConfig(max_luminance_shift=None))
        for image in batch:
            harmonizer.measure(image, box)
        corrected = [harmonizer.transform(image, box) for image in batch]

        _, before = self._spread(batch, box)
        _, after = self._spread(corrected, box)
        assert after < before * 0.5, f"dispersion de luminance {before:.1f} → {after:.1f}"

    def test_reference_is_the_median_not_the_mean(self):
        """Une photo aberrante ne doit pas entraîner la référence du lot.

        C'est le seul argument en faveur de la médiane contre la moyenne.
        """
        base = make_photo(width=200, height=260)
        box = default_face_box(200, 260)
        normal = [apply_cast(base, (1.0, 1.0, 1.0))] * 5
        outlier = apply_cast(base, (0.2, 1.0, 3.0))

        with_outlier = BatchColorHarmonizer(ColorConfig())
        for image in [*normal, outlier]:
            with_outlier.measure(image, box)
        without = BatchColorHarmonizer(ColorConfig())
        for image in normal:
            without.measure(image, box)

        assert np.allclose(
            with_outlier.reference_illuminant, without.reference_illuminant, atol=0.02
        )

    def test_reference_is_none_before_any_measurement(self):
        harmonizer = BatchColorHarmonizer(ColorConfig())
        assert harmonizer.reference_illuminant is None
        assert harmonizer.reference_luminance is None

    def test_transform_without_measurement_does_not_crash(self, batch):
        harmonizer = BatchColorHarmonizer(ColorConfig())
        assert harmonizer.transform(batch[0], None).shape == batch[0].shape

    def test_disabled_white_balance_leaves_hue_alone(self, batch):
        config = ColorConfig(white_balance="none", auto_levels_clip=None, harmonize_batch=False)
        harmonizer = BatchColorHarmonizer(config)
        assert np.array_equal(harmonizer.transform(batch[1], None), batch[1])

    def test_reset_clears_samples(self, batch):
        harmonizer = BatchColorHarmonizer(ColorConfig())
        harmonizer.measure(batch[0], None)
        harmonizer.reset()
        assert harmonizer.reference_illuminant is None

    def test_strength_is_honoured_end_to_end(self, batch):
        """Le réglage doit atteindre les gains, pas rester dans la configuration."""
        box = default_face_box(240, 320)
        results = {}
        for strength in (0.0, 1.0):
            harmonizer = BatchColorHarmonizer(ColorConfig(strength=strength))
            for image in batch:
                harmonizer.measure(image, box)
            results[strength] = harmonizer.transform(batch[1], box)
        assert not np.array_equal(results[0.0], results[1.0])

    def test_simulated_session_converges(self):
        """Le cas d'usage visé : un seul sujet, une seule séance, éclairage qui dérive.

        La vérité terrain est connue — toutes les images devraient redevenir
        identiques — donc l'assertion peut être franche.
        """
        base = make_photo(width=200, height=260)
        box = default_face_box(200, 260)
        casts = [(0.82, 0.98, 1.20), (1.22, 1.02, 0.86), (1.0, 1.0, 1.0), (0.95, 1.10, 0.92)]
        variants = [apply_cast(base, cast) for cast in casts]

        harmonizer = BatchColorHarmonizer(ColorConfig())
        for image in variants:
            harmonizer.measure(image, box)
        corrected = [harmonizer.transform(image, box) for image in variants]

        assert self._max_gap(corrected) < self._max_gap(variants) / 2

    @staticmethod
    def _max_gap(images: list[np.ndarray]) -> float:
        means = (
            np.stack([image.astype(np.float32) for image in images])
            .reshape(len(images), -1, 3)
            .mean(axis=1)
        )
        return float(max(np.abs(a - b).mean() for a in means for b in means))


class TestFaceMask:
    def test_returns_none_without_box(self):
        assert face_mask((100, 100, 3), None) is None

    def test_mask_is_inside_the_box(self):
        box = Box(20, 30, 60, 90)
        mask = face_mask((120, 120, 3), box)
        ys, xs = np.nonzero(mask)
        assert xs.min() >= box.x0 and xs.max() <= box.x1
        assert ys.min() >= box.y0 and ys.max() <= box.y1

    def test_mask_is_smaller_than_the_box(self):
        """L'ellipse est resserrée pour exclure cheveux et bord de fond."""
        box = Box(20, 30, 60, 90)
        assert int(face_mask((120, 120, 3), box).sum()) < box.area

    def test_box_outside_image_is_clipped(self):
        mask = face_mask((50, 50, 3), Box(40, 40, 200, 200))
        assert mask.shape == (50, 50)


class TestMaxLuminanceShift:
    """Une photo très éloignée du lot ne doit pas être tirée jusqu'à la médiane.

    L'y forcer lui coûte son contraste : le gamma qui la déplace comprime la
    plage d'un côté. Mesuré sur un lot réel de 39 portraits, la contrainte à
    20 points ramène la perte de contraste de 18 % à 7 %.
    """

    @pytest.fixture
    def lot(self) -> list[np.ndarray]:
        """Cinq portraits groupés, plus un nettement plus sombre.

        Le visage est texturé : sur l'ovale uniforme de ``make_photo`` il n'y
        aurait aucun contraste à perdre, et le test ne mesurerait rien.
        """
        rng = np.random.default_rng(3)
        base = make_photo(width=200, height=260)
        bruit = rng.normal(0, 22, base.shape).astype(np.float32)
        base = np.clip(base.astype(np.float32) + bruit, 0, 255).astype(np.uint8)
        clairs = [
            np.clip(base.astype(np.float32) * f, 0, 255).astype(np.uint8)
            for f in (0.98, 1.0, 1.02, 1.0, 0.99)
        ]
        sombre = np.clip(base.astype(np.float32) * 0.45, 0, 255).astype(np.uint8)
        return [*clairs, sombre]

    @staticmethod
    def _corriger(lot, config, box):
        harmoniseur = BatchColorHarmonizer(config)
        for image in lot:
            harmoniseur.measure(image, box)
        return [harmoniseur.transform(image, box) for image in lot]

    def test_la_bride_limite_le_deplacement(self, lot):
        box = default_face_box(200, 260)
        mask = face_mask(lot[-1].shape, box)
        avant = median_luminance(lot[-1], mask)
        bride = self._corriger(lot, ColorConfig(max_luminance_shift=15.0), box)[-1]
        assert abs(median_luminance(bride, mask) - avant) <= 15.0 + 3.0

    def test_sans_bride_la_photo_rejoint_la_mediane(self, lot):
        box = default_face_box(200, 260)
        mask = face_mask(lot[-1].shape, box)
        avant = median_luminance(lot[-1], mask)
        libre = self._corriger(lot, ColorConfig(max_luminance_shift=None), box)[-1]
        assert abs(median_luminance(libre, mask) - avant) > 15.0

    def test_la_bride_preserve_le_contraste(self, lot):
        """L'objectif de la bride : garder du modelé sur la photo aberrante."""
        box = default_face_box(200, 260)
        mask = face_mask(lot[-1].shape, box)

        def contraste(image):
            return float(cv2.cvtColor(image, cv2.COLOR_BGR2LAB)[:, :, 0][mask].std())

        libre = self._corriger(lot, ColorConfig(max_luminance_shift=None), box)[-1]
        bride = self._corriger(lot, ColorConfig(max_luminance_shift=15.0), box)[-1]
        assert contraste(bride) > contraste(libre)

    def test_les_photos_proches_ne_sont_pas_affectees(self, lot):
        """La bride ne doit rien changer à celles qui étaient déjà dans le lot."""
        box = default_face_box(200, 260)
        libre = self._corriger(lot, ColorConfig(max_luminance_shift=None), box)[1]
        bride = self._corriger(lot, ColorConfig(max_luminance_shift=20.0), box)[1]
        assert np.array_equal(libre, bride)

    @pytest.mark.parametrize("valeur", [0.0, -5.0])
    def test_bride_invalide(self, valeur: float):
        with pytest.raises(ValueError, match="max_luminance_shift"):
            ColorConfig(max_luminance_shift=valeur)

    def test_none_est_accepte(self):
        assert ColorConfig(max_luminance_shift=None).max_luminance_shift is None


class TestColorConfigDisabled:
    """`disabled()` et `NO_COLOR` doivent vraiment ne rien faire."""

    @pytest.fixture
    def lot(self) -> list[np.ndarray]:
        rng = np.random.default_rng(7)
        return [rng.integers(30, 230, (70, 60, 3), dtype=np.uint8) for _ in range(4)]

    def test_les_images_ressortent_identiques(self, lot):
        harmoniseur = BatchColorHarmonizer(ColorConfig.disabled())
        for image in lot:
            harmoniseur.measure(image, None)
        assert all(np.array_equal(harmoniseur.transform(i, None), i) for i in lot)

    def test_no_color_est_la_meme_chose(self):
        assert ColorConfig.disabled() == NO_COLOR

    def test_les_trois_traitements_sont_coupes(self):
        """Notamment `harmonize_batch`, qui porte aussi la normalisation d'exposition."""
        config = ColorConfig.disabled()
        assert config.white_balance == "none"
        assert config.harmonize_batch is False
        assert config.auto_levels_clip is None

    def test_couper_la_seule_balance_ne_suffit_pas(self, lot):
        """Le piège documenté : `white_balance="none"` laisse passer l'exposition."""
        harmoniseur = BatchColorHarmonizer(ColorConfig(white_balance="none"))
        for image in lot:
            harmoniseur.measure(image, None)
        assert not all(np.array_equal(harmoniseur.transform(i, None), i) for i in lot)

    def test_no_color_est_exporte_a_la_racine(self):
        import trombinoscope

        assert trombinoscope.NO_COLOR is NO_COLOR
