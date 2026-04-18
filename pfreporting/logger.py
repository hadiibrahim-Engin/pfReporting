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

    Subsequent calls with the same name return the same logger instance,
    preventing duplicate handler registration.

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
    logger = get_logger()
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
    """Forwards log messages to PowerFactory output window with appropriate formatting.
    
    Uses different print methods based on log level:
    - ERROR/CRITICAL: app.PrintError() (displayed as red/error)
    - WARNING: app.PrintWarn() (displayed as yellow/warning)
    - INFO: app.PrintInfo() (displayed as blue/info)
    - DEBUG: app.PrintPlain() (normal text)
    """

    def __init__(self, app) -> None:
        """Initialize handler with PowerFactory app object.

        Args:
            app: PowerFactory Application object with PrintError, PrintWarn, PrintInfo, PrintPlain methods.
        """
        super().__init__()
        self._app = app

    def emit(self, record: logging.LogRecord) -> None:
        """Forward formatted log record to PowerFactory output with appropriate method.

        Args:
            record: Standard logging record instance.
        """
        try:
            msg = self.format(record)
            
            # Route to appropriate PowerFactory output method based on level
            if record.levelno >= logging.ERROR:
                self._app.PrintError(msg)
            elif record.levelno >= logging.WARNING:
                self._app.PrintWarn(msg)
            elif record.levelno >= logging.INFO:
                self._app.PrintInfo(msg)
            else:  # DEBUG
                self._app.PrintPlain(msg)
        except Exception:
            self.handleError(record)


def attach_powerfactory_handler(app) -> None:
    """Attach PowerFactory output handler to package logger.

    Uses app.PrintError/PrintWarn/PrintInfo/PrintPlain based on log level.
    Removes all existing handlers and replaces them with PowerFactoryLogHandler
    to prevent duplicate log messages.

    Args:
        app: PowerFactory Application object.
    """
    logger = get_logger()
    
    # Remove ALL handlers to prevent duplication
    # (RichHandler from _configure + any previous PowerFactoryLogHandler instances)
    for handler in logger.handlers[:]:  # Copy list to avoid mutation issues
        logger.removeHandler(handler)
    
    # Add only the PowerFactory handler
    pf_handler = PowerFactoryLogHandler(app)
    pf_handler.setLevel(logging.INFO)
    logger.addHandler(pf_handler)
