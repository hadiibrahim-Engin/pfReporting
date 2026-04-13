"""
ranking.py — Rank contingencies by severity and identify critical elements.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from database import db_queries as Q
import config

if TYPE_CHECKING:
    from database.db_manager import DBManager


def top_n_contingencies(db: "DBManager", n: int = None) -> list[dict]:
    """
    Return the top-N contingencies sorted by max loading.

    Adds a `rank` field (1-based) to each result dict.
    """
    n    = n or config.TOP_N_CONTINGENCIES
    rows = Q.get_top_n_contingencies(db, n)
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows


def critical_elements(db: "DBManager") -> list[dict]:
    """
    Return elements with the highest violation frequency.

    Adds a human-readable `priority_label` field.
    """
    rows  = Q.get_critical_elements(db)
    label = {1: "Sofort", 2: "Kurzfristig", 3: "Mittelfristig"}
    for r in rows:
        r["priority_label"] = label.get(r["priority"], "—")
    return rows
