"""
html_renderer.py — Jinja2 rendering engine with custom filters.

Usage:
    from reporting.html_renderer import render_report
    render_report(context, template_path, output_path)
"""

from __future__ import annotations
from pathlib import Path
import logging

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    select_autoescape,
)

import config

log = logging.getLogger(__name__)


# ── Custom Jinja2 filters ─────────────────────────────────────────────────────

def _filter_pct_color(value: float) -> str:
    """Return a Tailwind text-colour class based on loading percentage."""
    if value > 100:
        return "text-danger font-bold"
    if value > 80:
        return "text-warn-600 font-semibold"
    return "text-accent-600"


def _filter_severity_badge(level: str) -> str:
    """Return an HTML badge string for the given severity label."""
    mapping = {
        "Kritisch": '<span class="badge b-crit"><i class="fa-solid fa-circle-exclamation"></i> Kritisch</span>',
        "Warnung":  '<span class="badge b-warn"><i class="fa-solid fa-triangle-exclamation"></i> Warnung</span>',
        "OK":       '<span class="badge b-ok"><i class="fa-solid fa-circle-check"></i> OK</span>',
    }
    return mapping.get(level, level)


def _filter_format_mw(value: float) -> str:
    """Format a MW value with German decimal separator."""
    return f"{value:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _filter_pu_to_kv(u_pu: float, nominal_kv: float) -> str:
    """Convert per-unit voltage to kV string."""
    return f"{u_pu * nominal_kv:.2f} kV"


def _filter_prio_badge(level: int) -> str:
    cls = {1: "p1", 2: "p2", 3: "p3"}.get(int(level), "p3")
    return f'<span class="prio-c {cls}">{level}</span>'


# ── Renderer ──────────────────────────────────────────────────────────────────

def render_report(
    context: dict,
    template_path: str | Path | None = None,
    output_path: str | Path | None   = None,
) -> Path:
    """
    Render the Jinja2 template with `context` and write to `output_path`.

    Parameters
    ----------
    context       : Full context dict from data_assembler.assemble_context()
    template_path : Path to the .html template (default: config.TEMPLATE)
    output_path   : Destination HTML file (default: config.HTML_OUTPUT)

    Returns
    -------
    Path : Absolute path of the written file.
    """
    template_path = Path(template_path or config.TEMPLATE)
    output_path   = Path(output_path   or config.HTML_OUTPUT)

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    # ── Build Jinja2 environment ───────────────────────────────────────────────
    env = Environment(
        loader          = FileSystemLoader(str(template_path.parent)),
        autoescape      = select_autoescape(["html"]),
        undefined       = StrictUndefined,
        trim_blocks     = True,
        lstrip_blocks   = True,
    )

    # ── Register filters ───────────────────────────────────────────────────────
    env.filters["pct_color"]      = _filter_pct_color
    env.filters["severity_badge"] = _filter_severity_badge
    env.filters["format_mw"]      = _filter_format_mw
    env.filters["pu_to_kv"]       = _filter_pu_to_kv
    env.filters["prio_badge"]     = _filter_prio_badge

    # ── Render ─────────────────────────────────────────────────────────────────
    template = env.get_template(template_path.name)
    html     = template.render(**context)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    log.info("HTML report written to %s (%d bytes)", output_path, len(html))
    return output_path.resolve()
