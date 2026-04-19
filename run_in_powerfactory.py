"""
run_in_powerfactory.py
======================
PowerFactory IntScript - main script for De-Energization Assessment.

Execution:
    Create this script as an IntScript inside PowerFactory (e.g. in the
    Study Case or Network Data folder) and run it via "Execute Script".
    The script no longer requires an IntReport parent - it can run standalone.

Prerequisites - making the package available (one of three options):
    Option A  As an installed package in the PF venv:
              In the PF venv:  uv pip install -e <path>
    Option B  Set the path manually (PKG_PATH below):
              sys.path.insert(0, r"C:\\PF_Tools\\pfReporting")
    Option C  Place in the same directory as the script (no sys.path needed)

Execution modes (set EXECUTION_MODE below):
    ExecutionMode.FULL              — all reports: main + executive summary + QDS detail + LF comparison
    ExecutionMode.HTML_ONLY         — main report only (skips executive summary)
    ExecutionMode.SUMMARY_ONLY      — executive summary PDF-ready page only
    ExecutionMode.CALCULATIONS_ONLY — run PF calculations without generating HTML
    ExecutionMode.TABLES_ONLY       — like HTML_ONLY but skips QDS charts

IMPORTANT — "already deleted" error:
    PowerFactory caches Python modules between script runs.  All code that
    touches the 'app' object MUST live inside main() so it is re-executed
    on every run with a fresh application reference.  Never store 'app' at
    module level.
"""
import sys
import os

# ============================================================================
# sys.path setup — module-level is safe (no PowerFactory objects involved)
# ============================================================================

# Option B: set package path manually (leave empty if installed via pip/uv)
PKG_PATH = ""   # e.g. r"C:\PF_Tools\pfReporting"
if PKG_PATH and PKG_PATH not in sys.path:
    sys.path.insert(0, PKG_PATH)

# Option C: always add the directory of this script
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# ============================================================================
# Static configuration — module-level is safe (no PowerFactory objects)
# ============================================================================
import powerfactory  # type: ignore  # noqa: E402  (after sys.path is set)

from pfreporting.config import (
    CalculationOptions,
    N1Config,
    PFReportConfig,
    QDSConfig,
    ReportConfig,
    ThermalConfig,
    VoltageConfig,
    VizRequest,
)
from pfreporting.pipeline import ExecutionMode, run_full_workflow

# ---------------------------------------------------------------------------
# CONFIG — edit this block to match your network and study case
# ---------------------------------------------------------------------------
CONFIG = PFReportConfig(

    # -- Which calculations to run --------------------------------------------
    calc=CalculationOptions(
        run_qds=True,        # Quasi-dynamic simulation + time series charts
        run_loadflow=False,  # Static load flow (disabled — kept for future use)
        run_voltage=True,    # Voltage band check for all nodes
        run_thermal=True,    # Thermal loading of all lines and transformers
        run_n1=False,        # N-1 contingency analysis (disabled — kept for future use)
    ),

    # -- QDS time range (optional overrides) ----------------------------------
    qds=QDSConfig(
        start_datetime=None,  # e.g. "2026-04-19 00:00"
        end_datetime=None,    # e.g. "2026-04-20 00:00"
        t_start=None,         # legacy: simulation start time [h]
        t_end=None,           # legacy: simulation end time [h]
        dt=None,              # e.g. 0.25 - time step [h]
    ),

    # -- Voltage band limits --------------------------------------------------
    voltage=VoltageConfig(
        lower_warning=0.95,
        lower_violation=0.90,
        upper_warning=1.05,
        upper_violation=1.10,
    ),

    # -- Thermal loading limits -----------------------------------------------
    thermal=ThermalConfig(
        warning_pct=80.0,
        violation_pct=100.0,
    ),

    # -- N-1 analysis limits --------------------------------------------------
    n1=N1Config(
        max_loading_pct=100.0,
        min_voltage_pu=0.90,
        max_voltage_pu=1.10,
    ),

    # -- Report output --------------------------------------------------------
    report=ReportConfig(
        output_dir=r"C:\PF_Reports",
        company="Amprion GmbH",
        use_timestamp_subdir=True,
        quasi_dynamic_result_file="Quasi-Dynamic Simulation AC.ElmRes",
        intreport_name=None,  # e.g. "MyReport" to target a specific IntReport
    ),

    # -- Quasi-dynamic visualizations -----------------------------------------
    visualizations=[
        VizRequest(
            element_class="ElmLne",
            variable="c:loading",
            label="Lines - Loading",
            unit="%",
            warn_hi=80.0,
            violation_hi=100.0,
            heatmap=True,
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmTr2",
            variable="c:loading",
            label="Transformers - Loading",
            unit="%",
            warn_hi=80.0,
            violation_hi=100.0,
            heatmap=True,
            max_elements=50,
        ),
        VizRequest(
            element_class="ElmTerm",
            variable="m:u",
            label="Nodes - Voltage",
            unit="p.u.",
            warn_lo=0.95,
            violation_lo=0.90,
            warn_hi=1.05,
            violation_hi=1.10,
            heatmap=True,
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:i1:bus1",
            label="Lines - Current",
            unit="kA",
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:P:bus1",
            label="Lines - Active Power",
            unit="MW",
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:Q:bus1",
            label="Lines - Reactive Power",
            unit="Mvar",
            max_elements=200,
        ),
    ],
)

# Optional JSON config override — path to a PFReportConfig JSON file.
# When set, CONFIG above is replaced by the file contents.
CONFIG_JSON_PATH = ""  # e.g. r"C:\PF_Tools\my_config.json"

# Execution mode — controls which report files are generated.
# HTML_ONLY = single main report (all tabs: Overview, Statistics, QDS, Tables, Details)
# FULL      = main report + executive summary PDF page + QDS detail + LF comparison
EXECUTION_MODE = ExecutionMode.HTML_ONLY


# ============================================================================
# Helper — pure function, no stored PF references
# ============================================================================

def _find_intreport_for_script(app, script, preferred_name=None):
    """Resolve an IntReport object for table writing, if available.

    Strategy:
        1) if preferred_name is set, use matching IntReport in active study case
        2) walk parent chain from current script and use first IntReport
        3) fallback: first IntReport in active study case
    """
    reports = []
    try:
        sc = app.GetActiveStudyCase()
        if sc:
            reports = sc.GetContents("*.IntReport") or []
    except Exception:
        reports = []

    if preferred_name:
        for report in reports:
            try:
                if getattr(report, "loc_name", "") == preferred_name:
                    return report
            except Exception:
                continue
        app.PrintWarn(
            f"Configured IntReport '{preferred_name}' not found in active study case."
        )

    try:
        obj = script
        for _ in range(20):
            if not obj:
                break
            if obj.GetClassName() == "IntReport":
                return obj
            obj = obj.GetParent()
    except Exception:
        pass

    return reports[0] if reports else None


# ============================================================================
# main() — obtains a FRESH app reference on every call.
# ALL code that uses 'app' must live here, never at module level.
# ============================================================================

def main():
    # Force Python to release any stale COM wrappers from the previous run before
    # PowerFactory's internal cleanup runs.  Without this, the old app reference
    # held by the logging handler (and any other cached objects) is still alive when
    # PF invalidates it, which triggers "already deleted" on the second run.
    import gc
    gc.collect()

    # Fresh reference every time — avoids "already deleted" on repeated runs
    app    = powerfactory.GetApplication()
    script = app.GetCurrentScript()

    # Redirect Python logging → PowerFactory output window
    from pfreporting.logger import attach_powerfactory_handler
    attach_powerfactory_handler(app)

    # Resolve config (JSON override takes precedence if path is set)
    config = CONFIG
    if CONFIG_JSON_PATH:
        from pathlib import Path
        config = PFReportConfig.model_validate_json(
            Path(CONFIG_JSON_PATH).read_text(encoding="utf-8")
        )
        app.PrintInfo(f"Configuration loaded from: {CONFIG_JSON_PATH}")

    # Locate IntReport for QDS table writing (optional)
    pf_report = _find_intreport_for_script(app, script, config.report.intreport_name)
    if pf_report is not None:
        app.PrintInfo(
            f"IntReport detected: {getattr(pf_report, 'loc_name', '?')} "
            "— QDS tables will be written."
        )
    else:
        app.PrintWarn(
            "No IntReport found. QDS will run, but IntReport tables will not be written."
        )

    # Run full workflow — returns dict[str, Path] keyed by report type
    outputs = run_full_workflow(
        app=app,
        config=config,
        pf_report=pf_report,
        mode=EXECUTION_MODE,
        # data_before=None,  # supply a ReportData snapshot for LF comparison report
    )

    # Print a clickable link for each generated file
    _labels = {
        "main":                "Main Report",
        "executive_summary":   "Executive Summary",
        "qds_detail":          "QDS Detail",
        "loadflow_comparison": "LF Comparison",
    }
    app.PrintPlain("")
    app.PrintPlain("=" * 60)
    for key, dest in outputs.items():
        label    = _labels.get(key, key)
        file_url = "file:///" + str(dest).replace("\\", "/")
        try:
            # PrintHtml available in PowerFactory 2022+
            app.PrintHtml(f'<a href="{file_url}">&#128196; {label}: {dest}</a>')
        except Exception:
            app.PrintPlain(f"{label}: {dest}")
            app.PrintPlain(f"  Open: {file_url}")
    app.PrintPlain("=" * 60)


# ============================================================================
# Entry point — PowerFactory executes the module body each time the script
# is triggered, so calling main() here is equivalent to running it directly.
# ============================================================================
main()
