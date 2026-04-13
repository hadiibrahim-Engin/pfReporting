"""
violation_detector.py — Detect and classify loading and voltage violations.

Both functions return lists of dicts ready for the Jinja2 template context.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from database import db_queries as Q
import config

if TYPE_CHECKING:
    from database.db_manager import DBManager


def loading_violations(
    db: "DBManager",
    threshold: float = None,
) -> list[dict]:
    """
    Return all branch results above `threshold` (default: LOADING_WARNING_PCT).

    Adds derived fields:
        severity   – 'Kritisch' | 'Warnung'
        limit_pct  – always 100.0 (thermal limit)
        exceedance – loading_pct - limit_pct
    """
    threshold = threshold if threshold is not None else config.LOADING_WARNING_PCT
    rows = Q.get_loading_violations(db, threshold)

    for r in rows:
        r["limit_pct"]  = config.LOADING_CRITICAL_PCT
        r["exceedance"] = round(r["loading_pct"] - config.LOADING_CRITICAL_PCT, 1)
        # severity is already set by the SQL CASE expression

    return rows


def voltage_violations(
    db: "DBManager",
    u_min: float = None,
    u_max: float = None,
) -> list[dict]:
    """
    Return all node results outside the voltage band [u_min, u_max].

    Adds derived field:
        deviation_pct  – (u_pu − 1.0) × 100, signed
    """
    u_min = u_min if u_min is not None else config.VOLTAGE_MIN_PU
    u_max = u_max if u_max is not None else config.VOLTAGE_MAX_PU
    rows = Q.get_voltage_violations(db, u_min, u_max)
    # deviation_pct and type already computed in SQL
    return rows
