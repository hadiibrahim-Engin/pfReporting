"""Structured logging for the pfreporting package."""
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


def get_logger(name: str = "pfreporting") -> logging.Logger:
    """Return the configured package logger."""
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


def log_step_header(
    title: str,
    step: int | None = None,
    total: int | None = None,
) -> None:
    """Print a clearly visible step header to the package logger.

    Appears as a bordered block in the PowerFactory output window when
    the PowerFactoryLogHandler is attached, e.g.:

        ============================================================
          Step 1/3  –  QDS Simulation & Database Write
        ============================================================
    """
    logger = logging.getLogger("pfreporting")
    sep = "=" * 60
    if step is not None and total is not None:
        label = f"  Step {step}/{total}  \u2013  {title}"
    else:
        label = f"  {title}"
    logger.info("")
    logger.info(sep)
    logger.info(label)
    logger.info(sep)


class PowerFactoryLogHandler(logging.Handler):
    """Forwards log messages to app.PrintPlain (for PowerFactory)."""

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
    """Attach a PowerFactory output handler to the package logger."""
    logger = get_logger()
    pf_handler = PowerFactoryLogHandler(pf_print_fn)
    pf_handler.setLevel(logging.INFO)
    logger.addHandler(pf_handler)
