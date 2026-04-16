"""ReportData – sammelt alle Ergebnisse aus Reader + AnalysisEngine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from freischaltung.models import (
    LoadFlowResult,
    LoadingResult,
    N1Result,
    OverallStatus,
    ProjectInfo,
    SwitchedElement,
    TimeSeriesData,
    VoltageResult,
)

if TYPE_CHECKING:
    from freischaltung.analysis import AnalysisEngine
    from freischaltung.config import FreischaltungConfig
    from freischaltung.reader import PowerFactoryReader


@dataclass
class ReportData:
    """Vollständige Datenbasis für einen HTML-Report."""

    info: ProjectInfo
    switched: list[SwitchedElement]
    lf: LoadFlowResult
    voltage: list[VoltageResult]
    loading: list[LoadingResult]
    n1: list[N1Result]
    overall: OverallStatus
    ts_data: TimeSeriesData = field(default_factory=lambda: TimeSeriesData(time=[]))

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def build(
        cls,
        reader: "PowerFactoryReader",
        engine: "AnalysisEngine",
        config: "FreischaltungConfig",
    ) -> "ReportData":
        """Orchestriert alle Reader- und Analyseschritte."""
        import logging

        log = logging.getLogger("freischaltung")

        log.info("Lese Projektinformationen …")
        info = reader.get_project_info()

        log.info("Lese freigeschaltete Betriebsmittel …")
        switched = reader.get_switched_elements()

        log.info("Führe Lastflussberechnung durch …")
        lf = reader.get_loadflow_results()

        log.info("Lese Spannungsergebnisse …")
        voltage = engine.analyze_voltages(reader.get_voltage_results())

        log.info("Lese thermische Auslastung …")
        loading = engine.analyze_thermal(reader.get_loading_results())

        log.info("Führe N-1-Analyse durch …")
        n1 = engine.analyze_n1(reader.get_n1_results())

        overall = engine.get_overall_status(voltage, loading, n1)

        # Zeitreihen – optional
        ts_data = TimeSeriesData(time=[])
        try:
            log.info("Lade quasi-dynamische Zeitreihen …")
            elmres = reader.load_elmres()
            ts_raw = reader.get_time_series(elmres, config.visualizations)
            ts_data = engine.filter_critical_series(ts_raw, config.visualizations)
            elmres.Release()
        except Exception as exc:
            log.warning("Zeitreihen nicht verfügbar: %s", exc)

        return cls(
            info=info,
            switched=switched,
            lf=lf,
            voltage=voltage,
            loading=loading,
            n1=n1,
            overall=overall,
            ts_data=ts_data,
        )
