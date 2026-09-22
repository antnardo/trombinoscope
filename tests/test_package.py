"""Invariants de l'API publique du paquet.

Un `__all__` qui déclare un nom inexistant ne lève rien à l'import : il casse
`from module import *` et ment sur l'API sans que rien ne le signale. Ces tests
sont là pour que l'écart se voie tout de suite, pas six mois plus tard.
"""

import importlib
import pkgutil

import pytest

import trombinoscope

#: ``__main__.py`` n'expose rien : ce n'est pas un module d'API mais le point
#: d'entrée de ``python -m trombinoscope``.
SANS_API = {"trombinoscope.__main__"}


def modules() -> list[str]:
    noms = [
        info.name
        for info in pkgutil.walk_packages(trombinoscope.__path__, "trombinoscope.")
        if info.name not in SANS_API
    ]
    return ["trombinoscope", *sorted(noms)]


@pytest.mark.parametrize("nom", modules())
def test_chaque_module_declare_un_all(nom):
    assert hasattr(importlib.import_module(nom), "__all__"), f"{nom} n'a pas de __all__"


@pytest.mark.parametrize("nom", modules())
def test_tous_les_noms_declares_existent(nom):
    module = importlib.import_module(nom)
    manquants = [n for n in module.__all__ if not hasattr(module, n)]
    assert not manquants, f"{nom} déclare des noms absents : {manquants}"


@pytest.mark.parametrize("nom", modules())
def test_aucun_nom_prive_n_est_exporte(nom):
    """Les dunders sont exclus : ``__version__`` est une API, pas un détail interne."""
    module = importlib.import_module(nom)
    prives = [
        n
        for n in module.__all__
        if n.startswith("_") and not (n.startswith("__") and n.endswith("__"))
    ]
    assert not prives, f"{nom} exporte des noms privés : {prives}"


def test_import_etoile_fonctionne():
    espace: dict = {}
    exec("from trombinoscope import *", espace)
    assert "build_trombinoscope" in espace
    assert "SegmentationConfig" in espace


def test_la_racine_reexporte_ce_qu_elle_documente():
    """`__init__.py` doit exposer les configurations, sinon la doc ment."""
    for nom in ("ColorConfig", "FramingConfig", "GridConfig", "SegmentationConfig"):
        assert nom in trombinoscope.__all__
        assert hasattr(trombinoscope, nom)
