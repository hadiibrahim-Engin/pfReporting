"""
kpi_calculator.py — Derive all KPIs from the database.

Returns a single flat dict consumed by data_assembler.py → Jinja2 context.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from database import db_queries as Q
import config

if TYPE_CHECKING:
    from database.db_manager import DBManager


def calculate_kpis(db: "DBManager") -> dict:
    """Return the full KPI dict for the report context."""
    raw = Q.get_kpi_summary(db)

    # Derive prio-1 measure count from critical elements
    crit_elements = Q.get_critical_elements(db)
    prio1_count   = sum(1 for e in crit_elements if e["priority"] == 1)

    return {
        # ── Volume ────────────────────────────────────────────────────────────
        "total_contingencies_analyzed": raw.get("total_contingencies", 0),
        "critical_violations_count":    raw.get("critical_violations",  0),
        "warning_count":                raw.get("warning_violations",   0),
        # ── Max loading ───────────────────────────────────────────────────────
        "max_loading_pct":              round(raw.get("max_loading_pct", 0.0) or 0.0, 1),
        "max_loading_element":          raw.get("max_loading_element", "—"),
        # ── Voltage ───────────────────────────────────────────────────────────
        "voltage_violation_count":      raw.get("voltage_violations", 0),
        "affected_nodes_count":         raw.get("affected_nodes",     0),
        # ── Compliance ───────────────────────────────────────────────────────
        "n1_compliance_rate_pct":       raw.get("n1_compliance_rate_pct", 0.0),
        # ── Measures ─────────────────────────────────────────────────────────
        "prio1_measures_count":         prio1_count,
    }


def print_kpi_summary(kpis: dict) -> None:
    """Pretty-print KPIs to stdout (used by `main.py analyze`)."""
    w = 42
    print("=" * w)
    print(" KPI SUMMARY".center(w))
    print("=" * w)
    rows = [
        ("Analysierte Kontingenzen",   kpis["total_contingencies_analyzed"]),
        ("Kritische Verletzungen",      kpis["critical_violations_count"]),
        ("Warnungen (80–100 %)",        kpis["warning_count"]),
        ("Max. Belastung [%]",          f'{kpis["max_loading_pct"]:.1f}'),
        ("Max. Belastung Element",      kpis["max_loading_element"]),
        ("Spannungsverletzungen",       kpis["voltage_violation_count"]),
        ("Betroffene Knoten",           kpis["affected_nodes_count"]),
        ("N-1 Erfüllungsgrad [%]",      f'{kpis["n1_compliance_rate_pct"]:.1f}'),
        ("Maßnahmen Prio 1",            kpis["prio1_measures_count"]),
    ]
    for label, value in rows:
        print(f"  {label:<30} {value}")
    print("=" * w)
