"""Utility functions for formatting and display."""
from __future__ import annotations

import re


def sanitize_name(name: str | None, max_len: int = 120) -> str:
    """Convert an arbitrary name into a safe identifier."""
    s = re.sub(r"[^\w\-]", "_", name or "")
    if not s:
        s = "col"
    if s[0].isdigit():
        s = "_" + s
    return s[:max_len]


def format_pu(value: float) -> str:
    """Format a p.u. value with 4 decimal places."""
    return f"{value:.4f}"


def format_pct(value: float, decimals: int = 1) -> str:
    """Format a percentage value."""
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{decimals}f}"


def bar_width(loading_pct: float, scale: float = 0.66) -> str:
    """
    Return the CSS width for the loading bar.
    scale=0.66 → 100% loading corresponds to 66% bar width
    so the label text remains visible.
    """
    width = loading_pct * scale
    return f"{width:.3f}%"


def status_class(status: str) -> str:
    """Return the CSS class for a badge."""
    mapping = {
        "ok": "badge-ok",
        "warning": "badge-warning",
        "violation": "badge-violation",
    }
    return mapping.get(status, "badge-ok")


def bar_class(status: str) -> str:
    """Return the CSS class for a bar."""
    mapping = {
        "ok": "bar-ok",
        "warning": "bar-warning",
        "violation": "bar-violation",
    }
    return mapping.get(status, "bar-ok")


def badge_label(status: str) -> str:
    """Return the display label for a status."""
    mapping = {
        "ok": "OK",
        "warning": "WARNING",
        "violation": "VIOLATION",
    }
    return mapping.get(status, "OK")
