"""Logging setup with verbose toggle."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure and return the kvmsync logger.

    Parameters
    ----------
    verbose : bool
        When *True*, set the logger level to DEBUG so that
        per-keystroke and D-Bus signal details are emitted.
    """
    log = logging.getLogger("kvmsync")
    log.setLevel(logging.DEBUG if verbose else logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(fmt)
    log.addHandler(handler)

    return log
