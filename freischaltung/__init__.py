"""
freischaltung – Automatische Freischaltungsbewertung mit PowerFactory.

Öffentliche API:
    run_full_workflow(app, config, pf_report)  – Empfohlener Einstieg:
        Schritt 1 – QDS ausführen + Ergebnisse in IntReport-Tabellen schreiben
        Schritt 2 – Statische Ergebnisse lesen, N-1 analysieren
        Schritt 3 – HTML-Report generieren und speichern

    run_report(app, config)   – Kurzform ohne DB-Schritt (liest direkt aus PF)
    FreischaltungConfig       – Konfigurationsmodell
"""
from __future__ import annotations

import datetime
import logging
import os
from pathlib import Path
from typing import Any

from freischaltung.__version__ import __version__
from freischaltung.analysis import AnalysisEngine
from freischaltung.config import FreischaltungConfig
from freischaltung.logger import get_logger
from freischaltung.reader import PowerFactoryReader
from freischaltung.report.builder import ReportData
from freischaltung.report.generator import HTMLReportGenerator

__all__ = ["run_full_workflow", "run_report", "FreischaltungConfig", "__version__"]

log = get_logger()


def run_full_workflow(
    app: Any,
    config: FreischaltungConfig | None = None,
    pf_report: Any = None,
    output_path: str | Path | None = None,
) -> Path:
    """
    Vollständiger Zwei-Phasen-Workflow für die Freischaltungsbewertung.

    Schritt 1 – Datenbank-Integration (IntReport)
        • QDS-Berechnung ausführen (ComStatsim)
        • Zeitreihen aus ElmRes lesen
        • Ergebnisse in PowerFactory IntReport-Tabellen schreiben
          (persistente Speicherung im PF-Datenbankmodell)

    Schritt 2 – Statische Ergebnisse & N-1-Analyse
        • Lastflussberechnung
        • Spannungsbandprüfung aller Knoten
        • Thermische Auslastung aller Betriebsmittel
        • N-1-Kontingenzanalyse (automatische Schleifen-Schaltung)

    Schritt 3 – HTML-Report
        • Alle Ergebnisse zusammenführen
        • Grenzwertanalyse & Statusbewertung
        • Portablen HTML-Report mit eingebetteten Charts erzeugen

    Parameters
    ----------
    app:         PowerFactory-Anwendungsobjekt (powerfactory.GetApplication())
    config:      Konfiguration; Standardwerte wenn None
    pf_report:   IntReport-Objekt (script.GetParent()); wenn None wird ein
                 vorhandenes IntReport gesucht oder nur Schritt 2+3 ausgeführt
    output_path: Optionaler Ausgabepfad; überschreibt ReportConfig.output_dir

    Returns
    -------
    Path  Pfad der erzeugten HTML-Datei
    """
    if config is None:
        config = FreischaltungConfig()

    from freischaltung.analysis import AnalysisEngine
    from freischaltung.db_writer import PFTableWriter
    from freischaltung.reader import PowerFactoryReader
    from freischaltung.report.builder import ReportData
    from freischaltung.report.generator import HTMLReportGenerator

    reader    = PowerFactoryReader(app, config)
    engine    = AnalysisEngine(config)
    writer    = PFTableWriter(app, config)
    generator = HTMLReportGenerator(config)

    log.info("=" * 60)
    log.info("Freischaltungsbewertung v%s – Workflow gestartet", __version__)
    log.info("=" * 60)

    # ── Schritt 1: QDS → IntReport-Tabellen ──────────────────────────────
    ts_data = None
    if pf_report is not None:
        log.info("[Schritt 1] QDS-Simulation & Datenbankschreiben …")
        try:
            elmres = writer.run_qds()
            ts_data = writer.write_all(pf_report, elmres, clear_existing=True)
            elmres.Release()
            ts_data = engine.filter_critical_series(ts_data, config.visualizations)
            log.info(
                "[Schritt 1] Abgeschlossen – %d kritische Zeitreihen in %d Tabellen.",
                sum(len(s) for s in ts_data.sections.values()),
                len(ts_data.sections),
            )
        except Exception as exc:
            log.warning("[Schritt 1] Fehlgeschlagen: %s", exc)
            ts_data = None
    else:
        log.info("[Schritt 1] Kein IntReport übergeben – DB-Schritt übersprungen.")

    # ── Schritt 2: Statische Ergebnisse ──────────────────────────────────
    log.info("[Schritt 2] Statische Ergebnisse lesen & analysieren …")
    info     = reader.get_project_info()
    switched = reader.get_switched_elements()
    lf       = reader.get_loadflow_results()
    voltage  = engine.analyze_voltages(reader.get_voltage_results())
    loading  = engine.analyze_thermal(reader.get_loading_results())
    n1       = engine.analyze_n1(reader.get_n1_results())
    overall  = engine.get_overall_status(voltage, loading, n1)

    log.info(
        "[Schritt 2] Abgeschlossen – Status: %s, Verletzungen: %d",
        overall.status.upper(),
        overall.total_violations,
    )

    # Falls Schritt 1 ausgelassen: Zeitreihen direkt aus ElmRes holen
    if ts_data is None:
        try:
            log.info("[Schritt 2] Lese Zeitreihen direkt aus ElmRes …")
            elmres  = reader.load_elmres()
            ts_raw  = reader.get_time_series(elmres, config.visualizations)
            ts_data = engine.filter_critical_series(ts_raw, config.visualizations)
            elmres.Release()
        except Exception as exc:
            log.warning("[Schritt 2] Zeitreihen nicht verfügbar: %s", exc)
            from freischaltung.models import TimeSeriesData
            ts_data = TimeSeriesData(time=[])

    # ── Schritt 3: HTML-Report ────────────────────────────────────────────
    log.info("[Schritt 3] HTML-Report wird erzeugt …")
    from freischaltung.models import ProjectInfo
    data = ReportData(
        info=info,
        switched=switched,
        lf=lf,
        voltage=voltage,
        loading=loading,
        n1=n1,
        overall=overall,
        ts_data=ts_data,
    )
    html = generator.generate(data)

    dest = _resolve_output_path(data, config, output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")

    log.info("[Schritt 3] Report gespeichert: %s", dest)
    log.info("=" * 60)
    return dest


def run_report(
    app: Any,
    config: FreischaltungConfig | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """
    Liest PowerFactory-Ergebnisse, analysiert sie und schreibt einen HTML-Report.

    Parameters
    ----------
    app:         PowerFactory-Anwendungsobjekt (powerfactory.GetApplication())
    config:      Konfiguration; Standard-Grenzwerte wenn None
    output_path: Optionaler expliziter Ausgabepfad; überschreibt ReportConfig

    Returns
    -------
    Path  Pfad der erzeugten HTML-Datei
    """
    if config is None:
        config = FreischaltungConfig()

    reader = PowerFactoryReader(app, config)
    engine = AnalysisEngine(config)
    generator = HTMLReportGenerator(config)

    log.info("Starte Freischaltungsbewertung (v%s) …", __version__)

    data = ReportData.build(reader, engine, config)
    html = generator.generate(data)

    dest = _resolve_output_path(data, config, output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")

    log.info("Report gespeichert: %s", dest)
    return dest


def _resolve_output_path(
    data: ReportData,
    config: FreischaltungConfig,
    override: str | Path | None,
) -> Path:
    if override:
        p = Path(override)
        return p if p.suffix == ".html" else p / _default_filename(data)

    base = Path(config.report.output_dir)
    if config.report.use_timestamp_subdir:
        subdir = f"{datetime.date.today().isoformat()}_{data.info.project}"
        base = base / subdir
    return base / _default_filename(data)


def _default_filename(data: ReportData) -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = data.info.project.replace(" ", "_")[:40]
    return f"Freischaltungsbewertung_{safe_name}_{ts}.html"
