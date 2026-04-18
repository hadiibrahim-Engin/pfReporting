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
    """Return configured package logger instance.

    Args:
        name: Logger name.

    Returns:
        Configured ``logging.Logger`` instance.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        _configure(logger)
    return logger


def _configure(logger: logging.Logger) -> None:
    """Apply package logging defaults and attach stream/rich handlers.

    Args:
        logger: Logger instance to configure.
    """
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

    Args:
        title: Step title text.
        step: Optional current step number.
        total: Optional total number of steps.

    Appears as a bordered block in the PowerFactory output window when
    the PowerFactoryLogHandler is attached, e.g.:

        ============================================================
          Step 1/3  -  QDS Simulation & Database Write
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
        """Initialize handler with PowerFactory print callback.

        Args:
            pf_print_fn: Callable compatible with ``app.PrintPlain``.
        """
        super().__init__()
        self._print = pf_print_fn

    def emit(self, record: logging.LogRecord) -> None:
        """Forward formatted log record to PowerFactory output.

        Args:
            record: Standard logging record instance.
        """
        try:
            msg = self.format(record)
            self._print(msg)
        except Exception:
            self.handleError(record)


def attach_powerfactory_handler(pf_print_fn) -> None:
    """Attach PF output forwarding handler to package logger.

    Args:
        pf_print_fn: Callable compatible with ``app.PrintPlain``.
    """
    logger = get_logger()
    pf_handler = PowerFactoryLogHandler(pf_print_fn)
    pf_handler.setLevel(logging.INFO)
    logger.addHandler(pf_handler)
