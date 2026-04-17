"""
pfreporting – Automatic De-energization Assessment with PowerFactory.

Public API:
    run_full_workflow(app, config, pf_report)  – Recommended entry point:
        Step 1 – Run QDS + write results to IntReport tables
        Step 2 – Read static results, run N-1 analysis
        Step 3 – Generate and save HTML report

    run_report(app, config)   – Short form without DB step (reads directly from PF)
    PFReportConfig            – Configuration model
"""
from __future__ import annotations

import datetime
import logging
import os
from pathlib import Path
from typing import Any

from pfreporting.__version__ import __version__
from pfreporting.analysis import AnalysisEngine
from pfreporting.config import PFReportConfig
from pfreporting.logger import get_logger
from pfreporting.models import QDSStep, TimeSeriesData
from pfreporting.reader import PowerFactoryReader
from pfreporting.report.builder import ReportData
from pfreporting.report.generator import HTMLReportGenerator

__all__ = ["run_full_workflow", "run_report", "PFReportConfig", "__version__"]

log = get_logger()


def run_full_workflow(
    app: Any,
    config: PFReportConfig | None = None,
    pf_report: Any = None,
    output_path: str | Path | None = None,
) -> Path:
    """
    Complete two-phase workflow for the de-energization assessment.

    Step 1 – Database integration (IntReport)
        • Run QDS calculation (ComStatsim)
        • Read time series from ElmRes
        • Write results to PowerFactory IntReport tables
          (persistent storage in PF database model)

    Step 2 – Static results & N-1 analysis
        • Load flow calculation
        • Voltage band check for all nodes
        • Thermal loading of all elements
        • N-1 contingency analysis (automatic outage loop)

    Step 3 – HTML report
        • Aggregate all results
        • Threshold analysis & status assessment
        • Generate portable HTML report with embedded charts

    Parameters
    ----------
    app:         PowerFactory application object (powerfactory.GetApplication())
    config:      Configuration; default values if None
    pf_report:   IntReport object (script.GetParent()); if None, only Steps 2+3 run
    output_path: Optional output path; overrides ReportConfig.output_dir

    Returns
    -------
    Path  Path of the generated HTML file
    """
    if config is None:
        config = PFReportConfig()

    from pfreporting.analysis import AnalysisEngine
    from pfreporting.db_writer import PFTableWriter
    from pfreporting.reader import PowerFactoryReader
    from pfreporting.report.builder import ReportData
    from pfreporting.report.generator import HTMLReportGenerator

    reader    = PowerFactoryReader(app, config)
    engine    = AnalysisEngine(config)
    writer    = PFTableWriter(app, config)
    generator = HTMLReportGenerator(config)

    log.info("=" * 60)
    log.info("De-energization Assessment v%s – workflow started", __version__)
    log.info("=" * 60)

    # ── Step 1: QDS → IntReport tables ───────────────────────────────
    ts_data = None
    if pf_report is not None:
        log.info("[Step 1] QDS simulation & database write …")
        try:
            elmres = writer.run_qds()
            ts_data = writer.write_all(pf_report, elmres, clear_existing=True)
            elmres.Release()
            ts_data = engine.filter_critical_series(ts_data, config.visualizations)
            log.info(
                "[Step 1] Complete – %d critical time series in %d tables.",
                sum(len(s) for s in ts_data.sections.values()),
                len(ts_data.sections),
            )
        except Exception as exc:
            log.warning("[Step 1] Failed: %s", exc)
            ts_data = None
    else:
        log.info("[Step 1] No IntReport provided – DB step skipped.")

    # ── Step 2: Static results ────────────────────────────────────────
    log.info("[Step 2] Reading & analyzing static results …")
    info     = reader.get_project_info()
    qds_info = reader.get_qds_info()
    switched = reader.get_switched_elements()
    lf       = reader.get_loadflow_results()
    voltage  = engine.analyze_voltages(reader.get_voltage_results())
    loading  = engine.analyze_thermal(reader.get_loading_results())
    n1       = engine.analyze_n1(reader.get_n1_results())
    overall  = engine.get_overall_status(voltage, loading, n1)

    log.info(
        "[Step 2] Complete – Status: %s, Violations: %d",
        overall.status.upper(),
        overall.total_violations,
    )

    # If Step 1 was skipped: fetch time series directly from ElmRes
    if ts_data is None:
        try:
            log.info("[Step 2] Reading time series directly from ElmRes …")
            elmres  = reader.load_elmres()
            ts_raw  = reader.get_time_series(elmres, config.visualizations)
            ts_data = engine.filter_critical_series(ts_raw, config.visualizations)
            elmres.Release()
        except Exception as exc:
            log.warning("[Step 2] Time series not available: %s", exc)
            ts_data = TimeSeriesData(time=[])

    # Derive convergence per QDS time step from time series
    if not ts_data.is_empty():
        lf.qds_steps = _derive_qds_steps(ts_data)

    # ── Step 3: HTML report ───────────────────────────────────────────
    log.info("[Step 3] Generating HTML report …")
    data = ReportData(
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
    html = generator.generate(data)

    dest = _resolve_output_path(data, config, output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")

    log.info("[Step 3] Report saved: %s", dest)
    log.info("=" * 60)
    return dest


def run_report(
    app: Any,
    config: PFReportConfig | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """
    Read PowerFactory results, analyze them, and write an HTML report.

    Parameters
    ----------
    app:         PowerFactory application object (powerfactory.GetApplication())
    config:      Configuration; default thresholds if None
    output_path: Optional explicit output path; overrides ReportConfig

    Returns
    -------
    Path  Path of the generated HTML file
    """
    if config is None:
        config = PFReportConfig()

    reader = PowerFactoryReader(app, config)
    engine = AnalysisEngine(config)
    generator = HTMLReportGenerator(config)

    log.info("Starting de-energization assessment (v%s) …", __version__)

    data = ReportData.build(reader, engine, config)
    html = generator.generate(data)

    dest = _resolve_output_path(data, config, output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")

    log.info("Report saved: %s", dest)
    return dest


def _resolve_output_path(
    data: ReportData,
    config: PFReportConfig,
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
    return f"DeEnergizationAssessment_{safe_name}_{ts}.html"


def _derive_qds_steps(ts_data: TimeSeriesData) -> list[QDSStep]:
    """Convergence per QDS time step: not converged when all values are None."""
    all_series = [ts for sec in ts_data.sections.values() for ts in sec.values()]
    steps: list[QDSStep] = []
    for i, t in enumerate(ts_data.time):
        converged = any(
            i < len(s.values) and s.values[i] is not None
            for s in all_series
        ) if all_series else True
        steps.append(QDSStep(time_h=t, converged=converged))
    return steps
