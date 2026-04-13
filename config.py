"""
config.py — Central configuration for the contingency reporting pipeline.

All paths, thresholds, and PowerFactory settings are defined here.
Import this module everywhere; never hard-code these values elsewhere.
"""

from pathlib import Path

# ── Project root ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR     = ROOT / "data"
OUTPUT_DIR   = ROOT / "output"
TEMPLATE_DIR = ROOT / "templates"

DB_PATH      = DATA_DIR   / "contingency.db"
HTML_OUTPUT  = OUTPUT_DIR / "Outage_Report.html"
PDF_OUTPUT   = OUTPUT_DIR / "Outage_Report.pdf"
TEMPLATE     = TEMPLATE_DIR / "outage_report.html"

# Create dirs on import so callers don't have to
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# ── PowerFactory settings ─────────────────────────────────────────────────────
PF_PROJECT_NAME   = "Mein_Netz_Projekt"      # Override via CLI --project
PF_USERNAME       = ""                        # Leave empty for current Windows user
PF_LANGUAGE       = 1                         # 0 = German, 1 = English (affects GetAttr keys)

# ── Analysis thresholds ───────────────────────────────────────────────────────
LOADING_WARNING_PCT  = 80.0    # Start of amber zone
LOADING_CRITICAL_PCT = 100.0   # Red zone (thermal limit)
VOLTAGE_MIN_PU       = 0.95    # Lower voltage bound (pu)
VOLTAGE_MAX_PU       = 1.05    # Upper voltage bound (pu)

# ── Reporting ─────────────────────────────────────────────────────────────────
TOP_N_CONTINGENCIES  = 10      # How many top contingencies to show in ranked table
TOP_N_VIOLATIONS     = 20      # How many loading violations in bar chart
ROWS_PER_PAGE_HTML   = 50      # Appendix pagination

# ── Report metadata (overridden by CLI args) ──────────────────────────────────
DEFAULT_SCENARIO     = "Normalbetrieb"
DEFAULT_COMPANY      = "EnergieNetz AG"
DEFAULT_DEPARTMENT   = "Abteilung Netzplanung"
DEFAULT_VERSION      = "1.0"
DEFAULT_NORMS        = [
    "VDE-AR-N 4120",
    "DIN EN 50160",
    "ENTSO-E (N-1)-Kriterium",
    "TAB Mittelspannung 2022",
]

# ── DB settings ───────────────────────────────────────────────────────────────
DB_BATCH_SIZE        = 500     # Rows per transaction in db_writer
DB_VERSION           = 1       # user_version pragma (schema migrations)
