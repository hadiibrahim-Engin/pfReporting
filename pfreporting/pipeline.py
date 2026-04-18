"""
Workflow orchestration for pfreporting.

This module coordinates PowerFactory data access, analysis, and report generation
without exposing PowerFactory objects to the report layer.
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from pfreporting.__version__ import __version__
from pfreporting.analysis import AnalysisEngine
from pfreporting.config import PFReportConfig
from pfreporting.logger import configure_log_level, get_logger, log_step_header
from pfreporting.models import QDSStep, TimeSeriesData
from pfreporting.reader import PowerFactoryReader
from pfreporting.report.builder import ReportData
from pfreporting.report.generator import HTMLReportGenerator

log = get_logger()


def run_full_workflow(
    app: Any,
    config: PFReportConfig | None = None,
    pf_report: Any = None,
    output_path: str | Path | None = None,
) -> Path:
    """
    Complete two-phase workflow for the de-energization assessment.

    Step 1 - QDS simulation (optional, if pf_report is provided)
        • Run QDS calculation (ComStatsim)
        • Read time series from ElmRes
        • Write results to PowerFactory IntReport tables

    Step 2 - Static results & N-1 analysis
        • Load flow calculation (if calc.run_loadflow)
        • Voltage band check (if calc.run_voltage)
        • Thermal loading (if calc.run_thermal)
        • N-1 contingency analysis (if calc.run_n1)

    Step 3 - HTML report
        • Aggregate all results
        • Threshold analysis & status assessment
        • Generate portable HTML report with embedded charts
    """
    if config is None:
        config = PFReportConfig()

    configure_log_level(config.report.log_level)

    from pfreporting.db_writer import PFTableWriter

    reader = PowerFactoryReader(app, config)
    engine = AnalysisEngine(config)
    writer = PFTableWriter(app, config)
    generator = HTMLReportGenerator(config)
    calc = config.calc

    warnings: list[str] = []

    # Determine how many major steps will run (for progress display)
    _steps_planned = [
        (calc.run_qds, "QDS Simulation"),
        (True, "Static Results & Analysis"),
        (True, "HTML Report Generation"),
    ]
    total_steps = sum(1 for enabled, _ in _steps_planned if enabled)
    step_counter = [0]

    def next_step(title: str) -> None:
        step_counter[0] += 1
        log_step_header(title, step_counter[0], total_steps)

    log.info("")
    log.info("=" * 60)
    log.info("  De-Energization Assessment  v%s", __version__)
    log.info("=" * 60)

    # -- Step 1: QDS simulation (optional IntReport write) -----------------
    ts_raw: TimeSeriesData | None = None
    ts_data: TimeSeriesData | None = None
    if calc.run_qds:
        if pf_report is not None:
            next_step("QDS Simulation & Database Write")
        else:
            next_step("QDS Simulation")
        try:
            elmres = writer.run_qds()
            if pf_report is not None:
                ts_raw = writer.write_all(pf_report, elmres, clear_existing=True)
                ts_data = engine.filter_critical_series(ts_raw, config.visualizations)
                n_series = sum(len(s) for s in ts_data.sections.values())
                log.info(
                    "QDS complete - %d series in %d chart sections.",
                    n_series,
                    len(ts_data.sections),
                )
            else:
                log.info("QDS complete (no IntReport provided; using ElmRes directly).")
            elmres.Release()
        except Exception as exc:
            log.warning("QDS step failed: %s", exc)
            warnings.append(f"QDS step failed: {exc}")
            ts_raw = ts_data = None
    else:
        log.info("QDS step skipped (calc.run_qds=False).")

    # -- Step 2: Static results --------------------------------------------
    next_step("Static Results & Analysis")

    info = reader.get_project_info()
    qds_info = reader.get_qds_info()
    switched = reader.get_switched_elements()

    lf = reader.get_loadflow_results() if calc.run_loadflow else _empty_loadflow()
    if not calc.run_loadflow:
        log.info("Load flow skipped (calc.run_loadflow=False).")

    voltage = engine.analyze_voltages(reader.get_voltage_results()) if calc.run_voltage else []
    if not calc.run_voltage:
        log.info("Voltage analysis skipped (calc.run_voltage=False).")

    loading = engine.analyze_thermal(reader.get_loading_results()) if calc.run_thermal else []
    if not calc.run_thermal:
        log.info("Thermal analysis skipped (calc.run_thermal=False).")

    n1 = engine.analyze_n1(reader.get_n1_results()) if calc.run_n1 else []
    if not calc.run_n1:
        log.info("N-1 analysis skipped (calc.run_n1=False).")

    overall = engine.get_overall_status(voltage, loading, n1)
    log.info(
        "Analysis complete - Status: %s, Violations: %d",
        overall.status.upper(),
        overall.total_violations,
    )

    # If QDS step was skipped or failed: read time series directly from ElmRes
    if ts_data is None and calc.run_qds:
        try:
            log.info("Reading time series directly from ElmRes …")
            elmres = reader.load_elmres()
            ts_raw = reader.get_time_series(elmres, config.visualizations)
            ts_data = engine.filter_critical_series(ts_raw, config.visualizations)
            elmres.Release()
        except Exception as exc:
            log.warning("Time series not available: %s", exc)
            warnings.append(f"Time series not available: {exc}")
            ts_raw = ts_data = TimeSeriesData(time=[])
    elif ts_data is None:
        ts_raw = ts_data = TimeSeriesData(time=[])

    # Derive convergence per QDS time step from time series data
    if ts_data and not ts_data.is_empty():
        source = ts_raw if ts_raw and not ts_raw.is_empty() else ts_data
        lf.qds_steps = _derive_qds_steps(source)

    # -- Step 3: HTML report -----------------------------------------------
    next_step("HTML Report Generation")
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
        ts_raw=ts_raw or TimeSeriesData(time=[]),
        warnings=warnings,
    )
    html = generator.generate(data)

    dest = _resolve_output_path(data, config, output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")

    log.info("Report saved: %s", dest)
    log.info("")
    log.info("=" * 60)
    log.info("  DONE")
    log.info("=" * 60)
    return dest


def run_report(
    app: Any,
    config: PFReportConfig | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """
    Read PowerFactory results, analyze them, and write an HTML report.
    """
    if config is None:
        config = PFReportConfig()

    configure_log_level(config.report.log_level)

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
    """Resolve final HTML file destination path."""
    if override:
        p = Path(override)
        return p if p.suffix == ".html" else p / _default_filename(data)

    base = Path(config.report.output_dir)
    if config.report.use_timestamp_subdir:
        subdir = f"{datetime.date.today().isoformat()}_{data.info.project}"
        base = base / subdir
    return base / _default_filename(data)


def _default_filename(data: ReportData) -> str:
    """Build timestamped report filename."""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = data.info.project.replace(" ", "_")[:40]
    return f"DeEnergizationAssessment_{safe_name}_{ts}.html"


def _derive_qds_steps(ts_data: TimeSeriesData) -> list[QDSStep]:
    """Derive per-step QDS convergence flags from time-series availability."""
    all_series = [ts for sec in ts_data.sections.values() for ts in sec.values()]
    steps: list[QDSStep] = []
    for i, t in enumerate(ts_data.time):
        converged = (
            any(
                i < len(s.values) and s.values[i] is not None
                for s in all_series
            )
            if all_series
            else True
        )
        steps.append(QDSStep(time_h=t, converged=converged))
    return steps


def _empty_loadflow():
    """Return a placeholder LoadFlowResult when load flow is skipped."""
    from pfreporting.models import LoadFlowResult

    return LoadFlowResult(
        converged=False,
        status_text="Not calculated",
        iterations=0,
        total_load_mw=0.0,
        total_gen_mw=0.0,
        losses_mw=0.0,
    )
