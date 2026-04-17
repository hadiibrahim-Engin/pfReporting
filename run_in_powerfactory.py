"""
run_in_powerfactory.py
======================
PowerFactory IntScript – main script for De-Energization Assessment.

Execution:
    Create this script as an IntScript INSIDE an IntReport object in
    PowerFactory and run it via "Execute Script".

    The IntReport object serves as persistent storage for all
    time-series tables (Step 1).

Prerequisites – making the package available (one of three options):
    Option A  As an installed package in the PF venv:
              In the PF venv:  uv pip install -e <path>
    Option B  Set the path manually (PKG_PATH below):
              sys.path.insert(0, r"C:\\PF_Tools\\pfReporting")
    Option C  Place in the same directory as the script (no sys.path needed)

Workflow:
    [Step 1]  Run QDS simulation (ComStatsim)
              Read time series from ElmRes
              Write results to IntReport tables (PF database)

    [Step 2]  Load flow + voltage band + thermal loading + N-1 analysis

    [Step 3]  Generate portable HTML report with embedded plots
"""
import sys
import os

# ── Option B: set package path manually (leave empty if installed) ────────────
PKG_PATH = ""   # e.g. r"C:\PF_Tools\pfReporting"
if PKG_PATH and PKG_PATH not in sys.path:
    sys.path.insert(0, PKG_PATH)

# Always add the directory of this script (Option C)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# ── PowerFactory API ──────────────────────────────────────────────────────────
import powerfactory  # type: ignore

app    = powerfactory.GetApplication()
script = app.GetCurrentScript()
print  = app.PrintPlain   # shorthand like in reference scripts

# ── Redirect logging → PF output ─────────────────────────────────────────────
from pfreporting.logger import attach_powerfactory_handler
attach_powerfactory_handler(print)

# ── Get IntReport ─────────────────────────────────────────────────────────────
# This script must run directly inside an IntReport object!
report = script.GetParent()
if not report or report.GetClassName() != "IntReport":
    raise RuntimeError(
        "This script must be executed inside an IntReport object.\n"
        "Create the script as an IntScript within the desired IntReport."
    )

# ── Configuration ─────────────────────────────────────────────────────────────
from pfreporting.config import (
    PFReportConfig,
    N1Config,
    ReportConfig,
    ThermalConfig,
    VoltageConfig,
    VizRequest,
)

CONFIG = PFReportConfig(
    # ── Voltage band limits ───────────────────────────────────────────────────
    voltage=VoltageConfig(
        lower_warning=0.95,    # undervoltage warning zone [p.u.]
        lower_violation=0.90,  # undervoltage violation zone [p.u.]
        upper_warning=1.05,    # overvoltage warning zone [p.u.]
        upper_violation=1.10,  # overvoltage violation zone [p.u.]
    ),
    # ── Thermal loading limits ────────────────────────────────────────────────
    thermal=ThermalConfig(
        warning_pct=80.0,      # warning threshold [%]
        violation_pct=100.0,   # violation threshold [%]
    ),
    # ── N-1 analysis limits ───────────────────────────────────────────────────
    n1=N1Config(
        max_loading_pct=100.0, # max. loading N-1 [%]
        min_voltage_pu=0.90,   # min. voltage N-1 [p.u.]
        max_voltage_pu=1.10,   # max. voltage N-1 [p.u.]
    ),
    # ── Report output ─────────────────────────────────────────────────────────
    report=ReportConfig(
        output_dir=r"C:\PF_Reports",
        company="Amprion GmbH",
        use_timestamp_subdir=True,
        quasi_dynamic_result_file="Quasi-Dynamic Simulation AC.ElmRes",
    ),
    # ── Quasi-dynamic visualizations ──────────────────────────────────────────
    # Each entry = one chart section in the report + one database table.
    # element_class: PowerFactory class name  (e.g. ElmLne, ElmTr2, ElmTerm)
    # variable:      PF result variable       (e.g. c:loading, m:u, m:i1:bus1)
    # heatmap=True:  Show additional heatmap (elements × time)
    visualizations=[
        VizRequest(
            element_class="ElmLne",
            variable="c:loading",
            label="Lines – Loading",
            unit="%",
            warn_hi=80.0,
            violation_hi=100.0,
            heatmap=True,
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmTr2",
            variable="c:loading",
            label="Transformers – Loading",
            unit="%",
            warn_hi=80.0,
            violation_hi=100.0,
            heatmap=False,
            max_elements=50,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:i1:bus1",
            label="Lines – Current",
            unit="kA",
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:P:bus1",
            label="Lines – Active Power",
            unit="MW",
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:Q:bus1",
            label="Lines – Reactive Power",
            unit="Mvar",
            max_elements=200,
        ),
    ],
)

# ── Optional JSON config override ─────────────────────────────────────────────
# Path to a JSON file (PFReportConfig.model_dump_json()):
CONFIG_JSON_PATH = ""  # e.g. r"C:\PF_Tools\my_config.json"
if CONFIG_JSON_PATH:
    from pathlib import Path
    CONFIG = PFReportConfig.model_validate_json(
        Path(CONFIG_JSON_PATH).read_text(encoding="utf-8")
    )
    print(f"Configuration loaded: {CONFIG_JSON_PATH}")

# ── Start workflow ────────────────────────────────────────────────────────────
from pfreporting import run_full_workflow

dest = run_full_workflow(
    app=app,
    config=CONFIG,
    pf_report=report,   # IntReport for DB integration (Step 1)
)
print(f"")
print(f"====================================================")
print(f"Report saved: {dest}")
print(f"====================================================")
