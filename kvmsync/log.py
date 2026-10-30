"""Logging setup with verbose toggle."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def add_file_handler(path: str) -> None:
    """Also write kvmsync logs to *path* (rotated at 1 MB, 3 backups).

    Used on Windows, where the daemon runs under pythonw without a console.
    """
    from logging.handlers import RotatingFileHandler

    handler = RotatingFileHandler(
        path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    logging.getLogger("kvmsync").addHandler(handler)


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

    # pythonw has no console: sys.stdout is None.
    if sys.stdout is None:
        return log

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%H:%M:%S"))
    log.addHandler(handler)

    return log
