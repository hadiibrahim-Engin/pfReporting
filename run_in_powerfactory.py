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

Workflow:
    [Step 1]  Run QDS simulation (ComStatsim)
              Read time series from ElmRes
              Optionally write results to IntReport tables (PF database)

    [Step 2]  Load flow + voltage band + thermal loading + N-1 analysis
              (each calculation can be toggled via CalculationOptions)

    [Step 3]  Generate portable HTML report with embedded plots
              Clickable link to the report is printed in the PF output window.
"""
import sys
import os

# -- Option B: set package path manually (leave empty if installed) ------------
PKG_PATH = ""   # e.g. r"C:\PF_Tools\pfReporting"
if PKG_PATH and PKG_PATH not in sys.path:
    sys.path.insert(0, PKG_PATH)

# Always add the directory of this script (Option C)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# -- PowerFactory API ----------------------------------------------------------
import powerfactory  # type: ignore

app    = powerfactory.GetApplication()
script = app.GetCurrentScript()


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
        for _ in range(20):  # prevent infinite loops on broken object graphs
            if not obj:
                break
            if obj.GetClassName() == "IntReport":
                return obj
            obj = obj.GetParent()
    except Exception:
        pass

    if reports:
        return reports[0]

    return None

# -- Redirect logging → PF output ---------------------------------------------
from pfreporting.logger import attach_powerfactory_handler
attach_powerfactory_handler(app)

# -- Configuration -------------------------------------------------------------
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

CONFIG = PFReportConfig(
    # -- Which calculations to run ---------------------------------------------
    # Set any flag to False to skip that calculation and hide it from the report.
    calc=CalculationOptions(
        run_qds=True,       # Quasi-dynamic simulation + time series charts
        run_loadflow=True,  # Static load flow (P, Q, losses, power factor)
        run_voltage=True,   # Voltage band check for all nodes
        run_thermal=True,   # Thermal loading of all lines and transformers
        run_n1=True,        # N-1 contingency analysis (outage loop)
    ),

    # -- QDS time range (optional overrides) -----------------------------------
    # Leave as None to use whatever is configured inside PowerFactory.
    # Prefer full datetime overrides (start_datetime/end_datetime).
    # Legacy hour-based overrides (t_start/t_end) are still supported.
    # Note: PF attributes (Tstart, Tshow, dt) may differ by PF version.
    qds=QDSConfig(
        start_datetime=None,  # e.g. "2026-04-19 00:00"
        end_datetime=None,    # e.g. "2026-04-20 00:00"
        t_start=None,         # legacy: simulation start time [h]
        t_end=None,           # legacy: simulation end time [h]
        dt=None,              # e.g. 0.25 - time step [h]
    ),

    # -- Voltage band limits ---------------------------------------------------
    voltage=VoltageConfig(
        lower_warning=0.95,    # undervoltage warning zone [p.u.]
        lower_violation=0.90,  # undervoltage violation zone [p.u.]
        upper_warning=1.05,    # overvoltage warning zone [p.u.]
        upper_violation=1.10,  # overvoltage violation zone [p.u.]
    ),

    # -- Thermal loading limits ------------------------------------------------
    thermal=ThermalConfig(
        warning_pct=80.0,      # warning threshold [%]
        violation_pct=100.0,   # violation threshold [%]
    ),

    # -- N-1 analysis limits ---------------------------------------------------
    n1=N1Config(
        max_loading_pct=100.0, # max. loading N-1 [%]
        min_voltage_pu=0.90,   # min. voltage N-1 [p.u.]
        max_voltage_pu=1.10,   # max. voltage N-1 [p.u.]
    ),

    # -- Report output ---------------------------------------------------------
    report=ReportConfig(
        output_dir=r"C:\PF_Reports",
        company="Amprion GmbH",
        use_timestamp_subdir=True,
        quasi_dynamic_result_file="Quasi-Dynamic Simulation AC.ElmRes",
        intreport_name=None,  # e.g. "MyReport" to target a specific IntReport
    ),

    # -- Quasi-dynamic visualizations ------------------------------------------
    # Each entry = one chart section in the report.
    # element_class: PowerFactory class name  (e.g. ElmLne, ElmTr2, ElmTerm)
    # variable:      PF result variable       (e.g. c:loading, m:u, m:i1:bus1)
    # heatmap=True:  Show additional heatmap (elements × time)
    # warn_hi/lo, violation_hi/lo: Threshold lines on chart + filter criterion.
    #   VizRequests without any threshold always show ALL elements.
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

# -- Optional JSON config override ---------------------------------------------
# Path to a JSON file (PFReportConfig.model_dump_json()):
CONFIG_JSON_PATH = ""  # e.g. r"C:\PF_Tools\my_config.json"
if CONFIG_JSON_PATH:
    from pathlib import Path
    CONFIG = PFReportConfig.model_validate_json(
        Path(CONFIG_JSON_PATH).read_text(encoding="utf-8")
    )
    app.PrintInfo(f"Configuration loaded: {CONFIG_JSON_PATH}")

# -- Start workflow ------------------------------------------------------------
from pfreporting import run_full_workflow

pf_report = _find_intreport_for_script(app, script, CONFIG.report.intreport_name)
if pf_report is not None:
    app.PrintInfo(
        f"IntReport detected: {getattr(pf_report, 'loc_name', '?')} - QDS tables will be written."
    )
else:
    app.PrintWarn(
        "No IntReport found. QDS will run, but IntReport tables will not be written."
    )

dest = run_full_workflow(
    app=app,
    config=CONFIG,
    pf_report=pf_report,  # QDS always runs; IntReport write is used when available
)

# -- Print clickable link in PF output window ----------------------------------
file_url = "file:///" + str(dest).replace("\\", "/")
try:
    # PrintHtml is available in PowerFactory 2022 and later
    app.PrintHtml(
        f'<a href="{file_url}">&#128196; Report: {dest}</a>'
    )
except Exception:
    # Fallback for older PowerFactory versions
    app.PrintPlain("")
    app.PrintPlain("====================================================")
    app.PrintPlain(f"Report saved: {dest}")
    app.PrintPlain(f"Open in browser: {file_url}")
    app.PrintPlain("====================================================")
