"""
data_assembler.py — Assemble the complete Jinja2 context dict from the DB.

Single public function: assemble_context(db_path, **meta) -> dict
All chart data is JSON-serialized here so templates only need {{ var | safe }}.
"""

from __future__ import annotations
import datetime
import uuid
from pathlib import Path

from database.db_manager import DBManager
from database import db_queries as Q
from analysis import kpi_calculator, violation_detector, ranking
from reporting import chart_builder
import config


def assemble_context(
    db_path: str | Path | None = None,
    *,
    scenario: str  = config.DEFAULT_SCENARIO,
    netzname: str  = "Unbekanntes Netz",
    unternehmen: str = config.DEFAULT_COMPANY,
    ersteller: str = config.DEFAULT_DEPARTMENT,
    version: str   = config.DEFAULT_VERSION,
) -> dict:
    """
    Build and return the complete Jinja2 template context dict.

    Parameters
    ----------
    db_path     : Path to the SQLite database (default: config.DB_PATH)
    scenario    : Scenario label shown on the cover page
    netzname    : Network / project name
    unternehmen : Company name
    ersteller   : Responsible department / person
    version     : Report version string
    """
    db_path = db_path or config.DB_PATH

    with DBManager(db_path) as db:
        # ── Analysis ──────────────────────────────────────────────────────────
        kpis         = kpi_calculator.calculate_kpis(db)
        load_viol    = violation_detector.loading_violations(db)
        volt_viol    = violation_detector.voltage_violations(db)
        top_cont     = ranking.top_n_contingencies(db, config.TOP_N_CONTINGENCIES)
        crit_el      = ranking.critical_elements(db)
        full_list    = Q.get_full_contingency_list(db)
        all_branches = Q.get_all_branches(db)
        all_nodes    = Q.get_all_nodes(db)

    # ── Topology summary ──────────────────────────────────────────────────────
    def count(lst, key, val): return sum(1 for x in lst if x.get(key) == val)

    topologie = [
        {"komponente": "Knoten gesamt",              "anzahl": len(all_nodes),                         "details": "Alle Spannungsebenen"},
        {"komponente": "Leitungen / Freileitungen",  "anzahl": count(all_branches,"branch_type","line"),   "details": "Freileitungen"},
        {"komponente": "Kabel",                      "anzahl": count(all_branches,"branch_type","cable"),  "details": "Erdkabel"},
        {"komponente": "Transformatoren",            "anzahl": count(all_branches,"branch_type","transformer"), "details": "2-Wickler"},
        {"komponente": "Analysierte Kontingenzen",   "anzahl": kpis["total_contingencies_analyzed"],    "details": "N-1 Einzelausfall"},
    ]

    # ── Charts ────────────────────────────────────────────────────────────────
    pareto_json       = chart_builder.pareto_chart_data(top_cont)
    loading_bar_json  = chart_builder.loading_bar_chart_data(load_viol)
    voltage_scat_json = chart_builder.voltage_scatter_data(volt_viol)

    # ── Report metadata ───────────────────────────────────────────────────────
    now = datetime.date.today()

    return {
        # ── Cover ─────────────────────────────────────────────────────────────
        "unternehmen":      unternehmen,
        "netzname":         netzname,
        "datum":            now.strftime("%d.%m.%Y"),
        "szenario":         scenario,
        "bericht_id":       f"OER-{now.strftime('%Y-%m%d')}-{uuid.uuid4().hex[:4].upper()}",
        "version":          version,
        "ersteller":        ersteller,
        "deckblatt_infos":  [
            {"label": "Berechnungssoftware", "wert": "DIgSILENT PowerFactory 2024"},
            {"label": "Klassifizierung",     "wert": "Intern / Vertraulich"},
            {"label": "Erstellt am",         "wert": now.strftime("%d.%m.%Y")},
        ],
        "szenarien_tags": [scenario, "N-1 Analyse", "110 kV", "20 kV", "0,4 kV"],

        # ── KPIs ──────────────────────────────────────────────────────────────
        "kpis": kpis,
        "executive_summary_text": _build_executive_text(kpis, netzname, scenario),

        # ── Methodology ───────────────────────────────────────────────────────
        "methodik_parameter": [
            {"parameter": "Berechnungsmethode",      "wert": "AC-Lastfluss (Newton-Raphson)"},
            {"parameter": "Konvergenzkriterium",      "wert": "10⁻⁶ pu"},
            {"parameter": "Belastungsgrenzwert",      "wert": f"{config.LOADING_CRITICAL_PCT:.0f} %"},
            {"parameter": "Spannungsband",            "wert": f"{config.VOLTAGE_MIN_PU:.2f} – {config.VOLTAGE_MAX_PU:.2f} pu"},
            {"parameter": "Analysierte Kontingenzen", "wert": "N-1 (Einzelausfall)"},
            {"parameter": "Szenario",                 "wert": scenario},
        ],
        "topologie": topologie,
        "normen": config.DEFAULT_NORMS,

        # ── Top-10 ────────────────────────────────────────────────────────────
        "top_contingencies":  top_cont,
        "pareto_chart_data":  pareto_json,

        # ── Detail ────────────────────────────────────────────────────────────
        "loading_violations":    load_viol,
        "voltage_violations":    volt_viol,
        "critical_elements":     crit_el,
        "loading_bar_chart_data": loading_bar_json,
        "voltage_scatter_data":   voltage_scat_json,

        # ── SLD ───────────────────────────────────────────────────────────────
        "sld_image_path": "",     # Set externally if an SLD image is available

        # ── Measures (placeholder — extend with real data source) ─────────────
        "massnahmen": _placeholder_massnahmen(crit_el),

        # ── Appendix ──────────────────────────────────────────────────────────
        "full_contingency_list": full_list,
    }


# ── Private helpers ───────────────────────────────────────────────────────────

def _build_executive_text(kpis: dict, netzname: str, scenario: str) -> str:
    return (
        f'Das Netz "{netzname}" wurde im Szenario "{scenario}" auf N-1-Konformität geprüft. '
        f'Von {kpis["total_contingencies_analyzed"]:,} analysierten Einzel-Kontingenzszenarien '
        f'führen {kpis["critical_violations_count"]} zu kritischen Überlastungen (> 100 %) '
        f'und {kpis["warning_count"]} zu Warnungen (80–100 %). '
        f'Die maximale Betriebsmittelbelastung beträgt {kpis["max_loading_pct"]:.1f} % '
        f'({kpis["max_loading_element"]}). '
        f'Der N-1-Erfüllungsgrad liegt bei {kpis["n1_compliance_rate_pct"]:.1f} %.'
    ).replace(",", ".")


def _placeholder_massnahmen(crit_el: list[dict]) -> list[dict]:
    """Generate basic measure placeholders from critical elements."""
    rows = []
    for i, el in enumerate(crit_el[:5], start=1):
        rows.append({
            "prio":         el.get("priority", 1),
            "massnahme":    f"Maßnahme für {el['element_name']} prüfen und umsetzen",
            "element":      el["element_name"],
            "typ":          "Netzverstärkung",
            "aufwand":      "Mittel",
            "wirkung":      f"Reduktion Max.-Belastung (aktuell {el['max_loading_pct']:.1f} %)",
            "verantwortlich": "Netzplanung",
        })
    return rows
