"""Utility functions for formatting and display."""
from __future__ import annotations

import re


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
