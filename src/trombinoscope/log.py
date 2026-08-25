"""Journalisation du paquet, bâtie sur ``logging`` de la bibliothèque standard.

Le paquet écrit sur le logger ``trombinoscope`` et n'installe aucun handler à
l'import : c'est à l'application appelante de décider où vont les messages.
:func:`configure` en pose un, lisible, pour les usages en ligne de commande.

:func:`warning` peut marquer une pause avant de poursuivre, mais seulement si
l'appelant l'a demandé via :func:`set_interactive` — une bibliothèque importée ne
doit jamais bloquer sur ``input()``.
"""

import logging
import sys

LOGGER = logging.getLogger("trombinoscope")

_INTERACTIVE = False


def set_interactive(enabled: bool) -> None:
    """Active (ou non) la pause « Appuyez sur une touche » après chaque avertissement.

    Désactivé par défaut.
    """
    global _INTERACTIVE
    _INTERACTIVE = enabled


def configure(verbosity: int = 0, stream=None) -> None:
    """Configure un handler console lisible.

    ``verbosity`` 0 → WARNING, 1 → INFO, 2 ou plus → DEBUG.
    """
    level = {0: logging.WARNING, 1: logging.INFO}.get(verbosity, logging.DEBUG)
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    LOGGER.handlers.clear()
    LOGGER.addHandler(handler)
    LOGGER.setLevel(level)
    LOGGER.propagate = False


def info(message: str, *args: object) -> None:
    LOGGER.info(message, *args)


def debug(message: str, *args: object) -> None:
    LOGGER.debug(message, *args)


def warning(message: str, *args: object) -> None:
    """Avertit, et ne marque une pause que si :func:`set_interactive` l'a demandé."""
    LOGGER.warning(message, *args)
    if _INTERACTIVE:
        try:
            input("Appuyez sur Entrée pour continuer...")
        except (EOFError, KeyboardInterrupt):  # pragma: no cover - dépend du tty
            set_interactive(False)


def error(message: str, *args: object) -> None:
    LOGGER.error(message, *args)
