"""
chart_builder.py — Build Chart.js-compatible dataset dicts.

All functions return a Python dict that is then JSON-serialized in
data_assembler.py and injected into the Jinja2 template as {{ var | safe }}.
"""

from __future__ import annotations
import json


# ── Colour helpers ─────────────────────────────────────────────────────────────

def _loading_color(pct: float, alpha: float = 0.85) -> str:
    r, g, b = (227, 6, 19) if pct > 100 else (245, 166, 35) if pct > 80 else (0, 48, 135)
    return f"rgba({r},{g},{b},{alpha})"


# ── Pareto chart (bar + cumulative line) ───────────────────────────────────────

def pareto_chart_data(top10: list[dict]) -> str:
    """
    Build the Pareto chart payload for the Top-10 section.

    Returns JSON string with keys: labels, loading_pct, cumulative_pct.
    """
    labels      = [r["contingency_name"] for r in top10]
    loads       = [round(r["max_loading_pct"], 1) for r in top10]
    total       = sum(loads)
    cum, cum_pct = 0.0, []
    for v in loads:
        cum += v
        cum_pct.append(round(cum / total * 100, 1) if total else 0.0)

    return json.dumps({
        "labels":       labels,
        "loading_pct":  loads,
        "cumulative_pct": cum_pct,
    })


# ── Loading bar chart (horizontal bars, top-20 violations) ───────────────────

def loading_bar_chart_data(violations: list[dict], top_n: int = 20) -> str:
    """
    Build horizontal bar chart payload for the loading-violation section.

    Returns JSON string with keys: labels, values, colors.
    """
    rows   = violations[:top_n]
    labels = [f'{r["branch_name"]} / {r["contingency_name"]}' for r in rows]
    values = [round(r["loading_pct"], 1) for r in rows]
    colors = [_loading_color(v) for v in values]

    return json.dumps({
        "labels": labels,
        "values": values,
        "colors": colors,
    })


# ── Voltage scatter (u_pu per node) ──────────────────────────────────────────

def voltage_scatter_data(v_violations: list[dict]) -> str:
    """
    Build scatter-plot data for voltage violations.

    Returns JSON string with keys: labels, u_pu_values.
    """
    labels = [r["node_name"] for r in v_violations]
    values = [round(r["u_pu"], 4) for r in v_violations]

    return json.dumps({
        "labels":     labels,
        "u_pu_values": values,
    })
