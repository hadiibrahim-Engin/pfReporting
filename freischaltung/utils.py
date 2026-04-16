"""Hilfsfunktionen für Formatierung und Darstellung."""
from __future__ import annotations

import re


def sanitize_name(name: str | None, max_len: int = 120) -> str:
    """Wandelt einen beliebigen Namen in einen sicheren Bezeichner um."""
    s = re.sub(r"[^\w\-]", "_", name or "")
    if not s:
        s = "col"
    if s[0].isdigit():
        s = "_" + s
    return s[:max_len]


def format_pu(value: float) -> str:
    """Formatiert einen p.u.-Wert mit 4 Nachkommastellen."""
    return f"{value:.4f}"


def format_pct(value: float, decimals: int = 1) -> str:
    """Formatiert einen Prozentwert."""
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{decimals}f}"


def bar_width(loading_pct: float, scale: float = 0.66) -> str:
    """
    Gibt die CSS-Breite für den Auslastungsbalken zurück.
    scale=0.66 → 100 % Auslastung entspricht 66 % Balkenbreite,
    damit der Label-Text noch sichtbar ist.
    """
    width = loading_pct * scale
    return f"{width:.3f}%"


def status_class(status: str) -> str:
    """Gibt die CSS-Klasse für ein Badge zurück."""
    mapping = {
        "ok": "badge-ok",
        "warning": "badge-warnung",
        "violation": "badge-verletzung",
    }
    return mapping.get(status, "badge-ok")


def bar_class(status: str) -> str:
    """Gibt die CSS-Klasse für einen Balken zurück."""
    mapping = {
        "ok": "bar-ok",
        "warning": "bar-warnung",
        "violation": "bar-verletzung",
    }
    return mapping.get(status, "bar-ok")


def badge_label(status: str) -> str:
    """Gibt das deutsche Anzeigelabel für einen Status zurück."""
    mapping = {
        "ok": "OK",
        "warning": "WARNUNG",
        "violation": "VERLETZUNG",
    }
    return mapping.get(status, "OK")
