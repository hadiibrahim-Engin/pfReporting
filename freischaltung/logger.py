"""Strukturiertes Logging für das freischaltung-Paket."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

try:
    from rich.logging import RichHandler

    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False

if TYPE_CHECKING:
    pass

_LOG_FORMAT = "%(message)s"
_DATE_FORMAT = "%H:%M:%S"


def get_logger(name: str = "freischaltung") -> logging.Logger:
    """Gibt den konfigurierten Paket-Logger zurück."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        _configure(logger)
    return logger


def _configure(logger: logging.Logger) -> None:
    logger.setLevel(logging.DEBUG)
    if _RICH_AVAILABLE:
        handler: logging.Handler = RichHandler(
            rich_tracebacks=True,
            markup=True,
            show_path=False,
            log_time_format=_DATE_FORMAT,
        )
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    handler.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    logger.propagate = False


class PowerFactoryLogHandler(logging.Handler):
    """Leitet Log-Nachrichten an app.PrintPlain weiter (für PowerFactory)."""

    def __init__(self, pf_print_fn) -> None:
        super().__init__()
        self._print = pf_print_fn

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self._print(msg)
        except Exception:
            self.handleError(record)


def attach_powerfactory_handler(pf_print_fn) -> None:
    """Hängt einen PowerFactory-Ausgabe-Handler an den Paket-Logger."""
    logger = get_logger()
    pf_handler = PowerFactoryLogHandler(pf_print_fn)
    pf_handler.setLevel(logging.INFO)
    logger.addHandler(pf_handler)
