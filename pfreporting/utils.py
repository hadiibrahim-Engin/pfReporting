"""Utility functions for formatting and display."""
from __future__ import annotations

import datetime
import re
from typing import Any


def sanitize_name(name: str | None, max_len: int = 120) -> str:
    """Normalize an arbitrary label to a safe identifier-like string.

    Args:
        name: Source label that may include spaces or special characters.
        max_len: Maximum output length.

    Returns:
        Sanitized identifier string.

    Replaces non-word characters with ``_``, enforces a non-empty fallback
    (``"col"``), prefixes leading digits with ``_``, and truncates to
    ``max_len`` characters.
    """
    s = re.sub(r"[^\w\-]", "_", name or "")
    if not s:
        s = "col"
    if s[0].isdigit():
        s = "_" + s
    return s[:max_len]


def format_pu(value: float) -> str:
    """Format a p.u. value with four decimals.

    Args:
        value: Per-unit value.

    Returns:
        Formatted numeric string.
    """
    return f"{value:.4f}"


def format_pct(value: float, decimals: int = 1) -> str:
    """Format a signed percentage-like value.

    Args:
        value: Numeric value to render.
        decimals: Number of digits after decimal point.

    Returns:
        Signed formatted string.
    """
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{decimals}f}"


def bar_width(loading_pct: float, scale: float = 0.66) -> str:
    """
    Return CSS width string for the loading bar.

    Args:
        loading_pct: Loading percent value.
        scale: Multiplicative factor converting percent to CSS width.

    Returns:
        CSS width string with percent suffix.

    The formula is ``width = loading_pct * scale``. The default scale of 0.66
    keeps labels readable when loading values approach or exceed 100%.
    """
    width = loading_pct * scale
    return f"{width:.3f}%"


def status_class(status: str) -> str:
    """Map status string to badge CSS class.

    Args:
        status: Status key (``ok``, ``warning``, ``violation``).

    Returns:
        CSS class name for badge rendering.

    Unknown statuses fall back to ``badge-ok``.
    """
    mapping = {
        "ok": "badge-ok",
        "warning": "badge-warning",
        "violation": "badge-violation",
    }
    return mapping.get(status, "badge-ok")


def bar_class(status: str) -> str:
    """Map status string to loading-bar CSS class.

    Args:
        status: Status key (``ok``, ``warning``, ``violation``).

    Returns:
        CSS class name for loading-bar rendering.

    Unknown statuses fall back to ``bar-ok``.
    """
    mapping = {
        "ok": "bar-ok",
        "warning": "bar-warning",
        "violation": "bar-violation",
    }
    return mapping.get(status, "bar-ok")


def badge_label(status: str) -> str:
    """Map status string to an uppercase display label.

    Args:
        status: Status key (``ok``, ``warning``, ``violation``).

    Returns:
        Human-readable uppercase label.

    Unknown statuses fall back to ``OK``.
    """
    mapping = {
        "ok": "OK",
        "warning": "WARNING",
        "violation": "VIOLATION",
    }
    return mapping.get(status, "OK")


def parse_datetime_input(value: str | datetime.datetime | None) -> datetime.datetime | None:
    """Parse user-facing datetime strings used in configuration.

    Supported formats include:
    - ``YYYY-MM-DD HH:MM[:SS]``
    - ``DD.MM.YYYY HH:MM[:SS]``
    - ``YYYY/MM/DD HH:MM[:SS]``
    - ISO 8601 via ``datetime.fromisoformat``
    """
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value.replace(tzinfo=None)

    s = str(value).strip()
    if not s:
        return None

    try:
        return datetime.datetime.fromisoformat(s).replace(tzinfo=None)
    except ValueError:
        pass

    patterns = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%Y/%m/%d",
    ]
    for pattern in patterns:
        try:
            return datetime.datetime.strptime(s, pattern)
        except ValueError:
            continue
    return None


def parse_study_time_start(value: Any) -> datetime.datetime | None:
    """Parse ``iStudyTime`` from PowerFactory study case into datetime."""
    if value is None:
        return None

    if isinstance(value, (int, float)):
        digits = str(int(value))
    else:
        digits = str(value).strip()

    if digits.isdigit():
        if len(digits) >= 14:
            try:
                return datetime.datetime.strptime(digits[:14], "%Y%m%d%H%M%S")
            except ValueError:
                pass
        if len(digits) >= 12:
            try:
                return datetime.datetime.strptime(digits[:12], "%Y%m%d%H%M")
            except ValueError:
                pass
        if len(digits) >= 8:
            try:
                return datetime.datetime.strptime(digits[:8], "%Y%m%d")
            except ValueError:
                pass

    return parse_datetime_input(str(value))


def resolve_qds_datetime_hours(
    start_datetime: str | datetime.datetime | None,
    end_datetime: str | datetime.datetime | None,
    study_time_start_raw: Any,
) -> tuple[float | None, float | None, list[str]]:
    """Convert absolute datetime overrides to QDS hours.

    Returns ``(start_h, end_h, notes)`` where notes contains warning texts.
    """
    notes: list[str] = []
    start_dt = parse_datetime_input(start_datetime)
    end_dt = parse_datetime_input(end_datetime)

    if start_datetime and start_dt is None:
        notes.append(f"Invalid start_datetime format: {start_datetime}")
    if end_datetime and end_dt is None:
        notes.append(f"Invalid end_datetime format: {end_datetime}")

    if start_dt and end_dt and end_dt <= start_dt:
        notes.append("end_datetime must be later than start_datetime")
        return None, None, notes

    if not start_dt and not end_dt:
        return None, None, notes

    study_dt = parse_study_time_start(study_time_start_raw)
    if study_dt is not None:
        start_h = (start_dt - study_dt).total_seconds() / 3600.0 if start_dt else None
        end_h = (end_dt - study_dt).total_seconds() / 3600.0 if end_dt else None
        return start_h, end_h, notes

    if start_dt and end_dt:
        notes.append(
            "Could not read study time start; using relative datetime span "
            "(start_datetime -> 0h, end_datetime -> duration)."
        )
        return 0.0, (end_dt - start_dt).total_seconds() / 3600.0, notes

    notes.append(
        "Could not read study time start; datetime override requires both "
        "start_datetime and end_datetime."
    )
    return None, None, notes
