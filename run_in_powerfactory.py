"""
run_in_powerfactory.py
======================
PowerFactory IntScript – Hauptskript für die Freischaltungsbewertung.

Ausführung:
    Dieses Skript als IntScript INNERHALB eines IntReport-Objekts in
    PowerFactory anlegen und über "Skript ausführen" starten.

    Das IntReport-Objekt dient als persistenter Datenspeicher für alle
    Zeitreihen-Tabellen (Schritt 1).

Voraussetzung – Paket verfügbar machen (eine von drei Optionen):
    Option A  Als installiertes Paket in der PF-venv:
              In der PF-venv:  uv pip install -e <Pfad>
    Option B  Pfad manuell eintragen (PKG_PATH unten):
              sys.path.insert(0, r"C:\\PF_Tools\\freischaltung_report")
    Option C  Im selben Verzeichnis wie das Skript liegen (kein sys.path nötig)

Ablauf:
    [Schritt 1]  QDS-Simulation ausführen (ComStatsim)
                 Zeitreihen aus ElmRes lesen
                 Ergebnisse in IntReport-Tabellen schreiben (PF-Datenbank)

    [Schritt 2]  Lastfluss + Spannungsband + Auslastung + N-1 analysieren

    [Schritt 3]  Portablen HTML-Report mit eingebetteten Plots erzeugen
"""
import sys
import os

# ── Option B: Paketpfad manuell setzen (leer lassen wenn installiert) ────────
PKG_PATH = ""   # z.B. r"C:\PF_Tools\freischaltung_report"
if PKG_PATH and PKG_PATH not in sys.path:
    sys.path.insert(0, PKG_PATH)

# Verzeichnis dieses Skripts immer hinzufügen (Option C)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# ── PowerFactory API ──────────────────────────────────────────────────────────
import powerfactory  # type: ignore

app    = powerfactory.GetApplication()
script = app.GetCurrentScript()
print  = app.PrintPlain   # Shorthand wie im Referenzskript

# ── Logging → PF-Ausgabe umleiten ─────────────────────────────────────────────
from freischaltung.logger import attach_powerfactory_handler
attach_powerfactory_handler(print)

# ── IntReport holen ────────────────────────────────────────────────────────────
# Das Skript muss direkt in einem IntReport-Objekt liegen!
report = script.GetParent()
if not report or report.GetClassName() != "IntReport":
    raise RuntimeError(
        "Dieses Skript muss innerhalb eines IntReport-Objekts ausgeführt werden.\n"
        "Lege das Skript als IntScript im gewünschten IntReport an."
    )

# ── Konfiguration ──────────────────────────────────────────────────────────────
from freischaltung.config import (
    FreischaltungConfig,
    N1Config,
    ReportConfig,
    ThermalConfig,
    VoltageConfig,
    VizRequest,
)

CONFIG = FreischaltungConfig(
    # ── Grenzwerte Spannungsband ──────────────────────────────────────────────
    voltage=VoltageConfig(
        lower_warning=0.95,    # Warnzone Unterspannung [p.u.]
        lower_violation=0.90,  # Verletzungszone Unterspannung [p.u.]
        upper_warning=1.05,    # Warnzone Überspannung [p.u.]
        upper_violation=1.10,  # Verletzungszone Überspannung [p.u.]
    ),
    # ── Grenzwerte Thermische Auslastung ──────────────────────────────────────
    thermal=ThermalConfig(
        warning_pct=80.0,      # Warngrenze [%]
        violation_pct=100.0,   # Verletzungsgrenze [%]
    ),
    # ── Grenzwerte N-1-Analyse ────────────────────────────────────────────────
    n1=N1Config(
        max_loading_pct=100.0, # Max. Auslastung N-1 [%]
        min_voltage_pu=0.90,   # Min. Spannung N-1 [p.u.]
        max_voltage_pu=1.10,   # Max. Spannung N-1 [p.u.]
    ),
    # ── Report-Ausgabe ────────────────────────────────────────────────────────
    report=ReportConfig(
        output_dir=r"C:\PF_Reports",
        company="Amprion GmbH",
        use_timestamp_subdir=True,
        quasi_dynamic_result_file="Quasi-Dynamic Simulation AC.ElmRes",
    ),
    # ── Quasi-Dynamische Visualisierungen ─────────────────────────────────────
    # Jeder Eintrag = ein Chart-Abschnitt im Report + eine Datenbanktabelle.
    # element_class: PowerFactory-Klassenname  (z.B. ElmLne, ElmTr2, ElmTerm)
    # variable:      PF-Ergebnisvariable       (z.B. c:loading, m:u, m:i1:bus1)
    # heatmap=True:  Zusätzliche Heatmap (Elemente × Zeit) anzeigen
    visualizations=[
        VizRequest(
            element_class="ElmLne",
            variable="c:loading",
            label="Leitungen – Auslastung",
            unit="%",
            warn_hi=80.0,
            violation_hi=100.0,
            heatmap=True,
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmTr2",
            variable="c:loading",
            label="Transformatoren – Auslastung",
            unit="%",
            warn_hi=80.0,
            violation_hi=100.0,
            heatmap=False,
            max_elements=50,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:i1:bus1",
            label="Leitungen – Strom",
            unit="kA",
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:P:bus1",
            label="Leitungen – Wirkleistung",
            unit="MW",
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:Q:bus1",
            label="Leitungen – Blindleistung",
            unit="Mvar",
            max_elements=200,
        ),
    ],
)

# ── Optionaler JSON-Config-Override ───────────────────────────────────────────
# Pfad zu einer JSON-Datei (FreischaltungConfig.model_dump_json()):
CONFIG_JSON_PATH = ""  # z.B. r"C:\PF_Tools\meine_config.json"
if CONFIG_JSON_PATH:
    from pathlib import Path
    CONFIG = FreischaltungConfig.model_validate_json(
        Path(CONFIG_JSON_PATH).read_text(encoding="utf-8")
    )
    print(f"Konfiguration geladen: {CONFIG_JSON_PATH}")

# ── Workflow starten ───────────────────────────────────────────────────────────
from freischaltung import run_full_workflow

dest = run_full_workflow(
    app=app,
    config=CONFIG,
    pf_report=report,   # IntReport für DB-Integration (Schritt 1)
)
print(f"")
print(f"====================================================")
print(f"Report gespeichert: {dest}")
print(f"====================================================")
