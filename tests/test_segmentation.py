"""Tests du détourage de fond.

Deux propriétés comptent, et une seule est évidente. La première : composer sur un
aplat doit remplacer le fond sans toucher au sujet. La seconde, plus importante,
est que **le garde-fou refuse un mauvais masque** — sur un document nominatif, un
visage mutilé est bien pire qu'un fond hétérogène, donc chaque mode d'échec
connu a son test.

Aucun test unitaire ne charge le modèle : la segmentation est injectée par un
bouchon, et les masques sont construits à la main pour que les seuils soient
exercés exactement, pas approximativement.
"""

import numpy as np
import pytest

from trombinoscope.models import Box, SegmentationConfig
from trombinoscope.segmentation import (
    BackgroundReplacer,
    MaskQuality,
    SelfieSegmenter,
    assess_mask,
    replace_background,
    segmenter_model_path,
)

from .conftest import StubSegmenter, clean_mask, default_face_box, make_photo

WHITE = (255, 255, 255)


# --------------------------------------------------------------------------- #
# Garde-fou
# --------------------------------------------------------------------------- #


class TestAssessMask:
    """Chaque test correspond à un mode d'échec observé sur de vraies photos."""

    def test_masque_plausible_est_accepte(self):
        quality = assess_mask(clean_mask(), default_face_box())
        assert quality.ok
        assert quality.reason is None
        assert quality.components == 1

    def test_visage_hors_du_masque_est_refuse(self):
        face = default_face_box()
        mask = clean_mask(face=face)
        mask[face.y0 : face.y1, face.x0 : face.x1] = 0.0
        quality = assess_mask(mask, face)
        assert not quality.ok
        assert "visage" in quality.reason

    @pytest.mark.parametrize(
        ("fill", "attendu"),
        [(0.0, "sujet sur 0%"), (1.0, "sujet sur 100%")],
    )
    def test_masque_uniforme_est_refuse(self, fill, attendu):
        mask = np.full((800, 600), fill, dtype=np.float32)
        quality = assess_mask(mask, None)
        assert not quality.ok
        assert attendu in quality.reason

    def test_fragment_detache_est_refuse(self):
        """Un objet saturé derrière le sujet laisse une composante séparée.

        L'écart avec le sujet est volontaire : ``connectedComponents`` travaille en
        8-connexité, donc deux zones simplement mitoyennes n'en font qu'une.
        """
        mask = clean_mask()
        mask[500:700, 20:120] = 1.0
        quality = assess_mask(mask, default_face_box())
        assert not quality.ok
        assert "fragment" in quality.reason

    def test_fragment_minuscule_est_ignore(self):
        """En dessous de min_component_fraction, ce n'est pas un fragment mais du bruit."""
        mask = clean_mask()
        mask[600:606, 20:26] = 1.0
        assert assess_mask(mask, default_face_box()).ok

    def test_masque_flou_est_refuse(self):
        """Trop de pixels à alpha intermédiaire : le contour n'est pas décidé."""
        face = default_face_box()
        mask = np.full((800, 600), 0.5, dtype=np.float32)
        mask[face.y0 : face.y1, face.x0 : face.x1] = 1.0
        quality = assess_mask(mask, face)
        assert not quality.ok

    def test_sujet_touchant_le_bord_haut_est_refuse(self):
        mask = clean_mask()
        mask[0:5, 200:400] = 1.0
        quality = assess_mask(mask, default_face_box())
        assert not quality.ok
        assert "coupé" in quality.reason

    def test_bord_haut_tolere_si_configure(self):
        mask = clean_mask()
        mask[0:5, 200:400] = 1.0
        config = SegmentationConfig(reject_touching_top=False)
        assert assess_mask(mask, default_face_box(), config).ok

    def test_sans_visage_les_autres_indicateurs_decident(self):
        """Quand la détection échoue, le meilleur indicateur manque sans tout bloquer."""
        quality = assess_mask(clean_mask(), None)
        assert quality.face_coverage is None
        assert quality.ok

    def test_sans_visage_un_masque_aberrant_reste_refuse(self):
        quality = assess_mask(np.ones((800, 600), dtype=np.float32), None)
        assert not quality.ok

    def test_couverture_mesuree_sur_la_boite_du_visage(self):
        face = Box(100, 100, 200, 200)
        mask = np.zeros((400, 400), dtype=np.float32)
        mask[100:150, 100:200] = 1.0  # exactement la moitié haute de la boîte
        assert assess_mask(mask, face).face_coverage == pytest.approx(0.5)


def test_mask_quality_describe_mentionne_les_quatre_indicateurs():
    quality = MaskQuality(
        face_coverage=0.97, foreground=0.4, components=1, ambiguous=0.03, touches_top=False
    )
    texte = quality.describe()
    assert "97%" in texte and "40%" in texte and "1 composante" in texte
    assert quality.ok


def test_mask_quality_sans_visage_affiche_na():
    quality = MaskQuality(
        face_coverage=None, foreground=0.4, components=1, ambiguous=0.03, touches_top=False
    )
    assert "n/a" in quality.describe()


# --------------------------------------------------------------------------- #
# Compositing
# --------------------------------------------------------------------------- #


class TestReplaceBackground:
    def test_le_fond_prend_la_couleur_demandee(self):
        image = np.full((100, 100, 3), 30, dtype=np.uint8)
        mask = np.zeros((100, 100), dtype=np.float32)
        result = replace_background(image, mask, WHITE)
        assert (result == 255).all()

    def test_le_sujet_est_preserve_a_l_identique(self):
        """Sous alpha = 1, l'aller-retour sRGB → linéaire → sRGB ne doit rien décaler."""
        rng = np.random.default_rng(0)
        image = rng.integers(0, 256, (60, 60, 3), dtype=np.uint8)
        mask = np.ones((60, 60), dtype=np.float32)
        result = replace_background(image, mask, WHITE, erode_px=0)
        assert np.array_equal(result, image)

    def test_l_erosion_retire_le_lisere_de_contour(self):
        mask = np.zeros((100, 100), dtype=np.float32)
        mask[40:60, 40:60] = 1.0
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        sans = replace_background(image, mask, WHITE, erode_px=0, alpha_gain=1.0)
        avec = replace_background(image, mask, WHITE, erode_px=3, alpha_gain=1.0)
        assert (avec == 255).sum() > (sans == 255).sum()

    def test_le_gain_alpha_retrecit_la_zone_de_melange(self):
        """C'est le remède au halo : moins de pixels intermédiaires, moins de liseré."""
        ramp = np.tile(np.linspace(0.0, 1.0, 100, dtype=np.float32), (100, 1))
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        doux = replace_background(image, ramp, WHITE, alpha_gain=1.0, erode_px=0)
        raide = replace_background(image, ramp, WHITE, alpha_gain=8.0, erode_px=0)
        intermediaires = lambda img: ((img > 10) & (img < 245)).sum()  # noqa: E731
        assert intermediaires(raide) < intermediaires(doux)

    def test_gain_alpha_neutre_laisse_le_masque_intact(self):
        ramp = np.tile(np.linspace(0.0, 1.0, 50, dtype=np.float32), (50, 1))
        image = np.zeros((50, 50, 3), dtype=np.uint8)
        a = replace_background(image, ramp, WHITE, alpha_gain=1.0, erode_px=0)
        b = replace_background(image, ramp.copy(), WHITE, alpha_gain=1.0, erode_px=0)
        assert np.array_equal(a, b)

    def test_melange_en_lumiere_lineaire_et_non_en_srgb(self):
        """À alpha 0,5 entre noir et blanc, le sRGB naïf donnerait 128 ; la lumière
        linéaire donne ~188. C'est précisément ce qui évite d'assombrir le contour."""
        image = np.zeros((10, 10, 3), dtype=np.uint8)
        mask = np.full((10, 10), 0.5, dtype=np.float32)
        value = int(replace_background(image, mask, WHITE, alpha_gain=1.0, erode_px=0)[5, 5, 0])
        assert value > 180
        assert value != 128

    def test_taille_incoherente_leve_une_erreur(self):
        image = np.zeros((10, 10, 3), dtype=np.uint8)
        with pytest.raises(ValueError, match="même taille"):
            replace_background(image, np.zeros((20, 20), dtype=np.float32))


# --------------------------------------------------------------------------- #
# Assemblage
# --------------------------------------------------------------------------- #


class TestBackgroundReplacer:
    def test_compute_delegue_au_segmenteur_injecte(self):
        stub = StubSegmenter()
        replacer = BackgroundReplacer(segmenter=stub)
        mask, quality = replacer.compute(make_photo(), default_face_box())
        assert stub.calls == 1
        assert quality.ok
        assert mask.shape == (800, 600)

    def test_compute_ne_modifie_pas_l_image(self):
        photo = make_photo()
        original = photo.copy()
        BackgroundReplacer(segmenter=StubSegmenter()).compute(photo, default_face_box())
        assert np.array_equal(photo, original)

    def test_apply_utilise_la_couleur_de_la_configuration(self):
        config = SegmentationConfig(background=(0, 0, 255), erode_px=0)
        replacer = BackgroundReplacer(config, segmenter=StubSegmenter())
        image = np.zeros((50, 50, 3), dtype=np.uint8)
        result = replacer.apply(image, np.zeros((50, 50), dtype=np.float32))
        assert tuple(result[0, 0]) == (0, 0, 255)

    def test_masque_douteux_est_signale_sans_lever(self):
        mauvais = np.ones((800, 600), dtype=np.float32)
        replacer = BackgroundReplacer(segmenter=StubSegmenter(mauvais))
        _, quality = replacer.compute(make_photo(), default_face_box())
        assert not quality.ok


# --------------------------------------------------------------------------- #
# Modèle empaqueté
# --------------------------------------------------------------------------- #


def test_le_modele_est_livre_avec_le_paquet():
    path = segmenter_model_path()
    assert path.exists()
    assert path.suffix == ".tflite"


def test_licence_apache_livree_a_cote_du_modele():
    """Apache-2.0 impose de joindre le texte de la licence au fichier redistribué."""
    licence = segmenter_model_path().parent / "LICENSE-Apache-2.0.txt"
    assert licence.exists()
    assert "Apache License" in licence.read_text()


def test_image_non_bgr_est_refusee():
    with pytest.raises(ValueError, match="BGR"):
        SelfieSegmenter().mask(np.zeros((10, 10), dtype=np.uint8))


@pytest.mark.integration
def test_le_vrai_modele_detoure_un_portrait(sample_photos):
    """Le seul test qui charge le réseau : il vérifie qu'il tourne et qu'il tient
    les seuils du garde-fou sur de vraies photos."""
    from trombinoscope.detection import YuNetDetector
    from trombinoscope.imageio import read_image

    image = read_image(sample_photos[0])
    detections = YuNetDetector().detect(image)
    mask, quality = BackgroundReplacer(segmenter=SelfieSegmenter()).compute(
        image, detections[0].box if detections else None
    )
    assert mask.shape == image.shape[:2]
    assert float(mask.min()) >= 0.0 and float(mask.max()) <= 1.0
    assert quality.ok, quality.reason
