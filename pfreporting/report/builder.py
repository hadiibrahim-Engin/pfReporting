"""ReportData – aggregates all results from Reader + AnalysisEngine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pfreporting.models import (
    LoadFlowResult,
    LoadingResult,
    N1Result,
    OverallStatus,
    ProjectInfo,
    QDSInfo,
    SwitchedElement,
    TimeSeriesData,
    VoltageResult,
)

if TYPE_CHECKING:
    from pfreporting.analysis import AnalysisEngine
    from pfreporting.config import PFReportConfig
    from pfreporting.reader import PowerFactoryReader


@dataclass
class ReportData:
    """Complete data set for an HTML report."""

    info: ProjectInfo
    switched: list[SwitchedElement]
    lf: LoadFlowResult
    voltage: list[VoltageResult]
    loading: list[LoadingResult]
    n1: list[N1Result]
    overall: OverallStatus
    ts_data: TimeSeriesData = field(default_factory=lambda: TimeSeriesData(time=[]))
    qds_info: QDSInfo | None = None

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def build(
        cls,
        reader: "PowerFactoryReader",
        engine: "AnalysisEngine",
        config: "PFReportConfig",
    ) -> "ReportData":
        """Orchestrate all reader and analysis steps."""
        import logging

        log = logging.getLogger("pfreporting")

        log.info("Reading project information …")
        info = reader.get_project_info()
        qds_info = reader.get_qds_info()

        log.info("Reading de-energized equipment …")
        switched = reader.get_switched_elements()

        log.info("Running load flow calculation …")
        lf = reader.get_loadflow_results()

        log.info("Reading voltage results …")
        voltage = engine.analyze_voltages(reader.get_voltage_results())

        log.info("Reading thermal loading …")
        loading = engine.analyze_thermal(reader.get_loading_results())

        log.info("Running N-1 analysis …")
        n1 = engine.analyze_n1(reader.get_n1_results())

        overall = engine.get_overall_status(voltage, loading, n1)

        # Time series – optional
        ts_data = TimeSeriesData(time=[])
        try:
            log.info("Loading quasi-dynamic time series …")
            elmres = reader.load_elmres()
            ts_raw = reader.get_time_series(elmres, config.visualizations)
            ts_data = engine.filter_critical_series(ts_raw, config.visualizations)
            elmres.Release()
        except Exception as exc:
            log.warning("Time series not available: %s", exc)

        return cls(
            info=info,
            qds_info=qds_info,
            switched=switched,
            lf=lf,
            voltage=voltage,
            loading=loading,
            n1=n1,
            overall=overall,
            ts_data=ts_data,
        )
