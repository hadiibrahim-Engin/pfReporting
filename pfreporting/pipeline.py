"""Workflow orchestration for pfreporting.

Coordinates PowerFactory data access, analysis, and report generation
without exposing PowerFactory objects to the report layer.
"""
from __future__ import annotations

import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any

from pfreporting.__version__ import __version__
from pfreporting.analysis import AnalysisEngine
from pfreporting.config import PFReportConfig
from pfreporting.logger import configure_log_level, get_logger, log_step_header
from pfreporting.models import LoadFlowResult, QDSStep, TimeSeriesData
from pfreporting.reader import PowerFactoryReader
from pfreporting.report.builder import ReportData
from pfreporting.report.generator import HTMLReportGenerator, MultiPageReportGenerator

log = get_logger()


class ExecutionMode(Enum):
    """Controls which report files are generated."""
    FULL              = auto()
    CALCULATIONS_ONLY = auto()
    TABLES_ONLY       = auto()
    HTML_ONLY         = auto()
    SUMMARY_ONLY      = auto()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_full_workflow(
    app: Any,
    config: PFReportConfig | None = None,
    pf_report: Any = None,
    output_path: str | Path | None = None,
    mode: ExecutionMode = ExecutionMode.HTML_ONLY,
    data_before: "ReportData | None" = None,
) -> "dict[str, Path]":
    """Execute the full de-energization assessment and write HTML output(s).

    Returns a dict of ``{report_key: Path}`` for each file written.
    """
    if config is None:
        config = PFReportConfig()
    configure_log_level(config.report.log_level)

    log.info("")
    log.info("=" * 60)
    log.info("  De-Energization Assessment  v%s", __version__)
    log.info("=" * 60)

    data, warnings = _run_data_phase(app, config, pf_report)
    data.warnings.extend(warnings)

    return _render_phase(data, config, mode, data_before, output_path)


def run_report(
    app: Any,
    config: PFReportConfig | None = None,
    output_path: str | Path | None = None,
) -> Path:
    """Convenience wrapper: read PF results, analyse, write one HTML report."""
    if config is None:
        config = PFReportConfig()
    configure_log_level(config.report.log_level)

    reader    = PowerFactoryReader(app, config)
    engine    = AnalysisEngine(config)
    generator = HTMLReportGenerator(config)

    log.info("Starting de-energization assessment (v%s) …", __version__)
    data = ReportData.build(reader, engine, config)
    html = generator.generate(data)

    dest = _resolve_output_path(data, config, output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html, encoding="utf-8")
    log.info("Report saved: %s", dest)
    return dest


# ---------------------------------------------------------------------------
# Phase 1 — data collection
# ---------------------------------------------------------------------------

def _run_data_phase(
    app: Any,
    config: PFReportConfig,
    pf_report: Any,
) -> tuple[ReportData, list[str]]:
    """Run QDS simulation and static analyses; return assembled ReportData."""
    from pfreporting.db_writer import PFTableWriter

    reader = PowerFactoryReader(app, config)
    engine = AnalysisEngine(config)
    writer = PFTableWriter(app, config)
    calc   = config.calc
    warnings: list[str] = []

    steps_planned = [
        (calc.run_qds,  "QDS Simulation"),
        (True,          "Static Results & Analysis"),
    ]
    total_steps   = sum(1 for enabled, _ in steps_planned if enabled)
    step_counter  = [0]

    def next_step(title: str) -> None:
        step_counter[0] += 1
        log_step_header(title, step_counter[0], total_steps)

    # -- Step 1: QDS simulation ----------------------------------------
    ts_raw: TimeSeriesData | None  = None
    ts_data: TimeSeriesData | None = None

    if calc.run_qds:
        next_step("QDS Simulation" + (" & Database Write" if pf_report else ""))
        try:
            elmres = writer.run_qds()
            if pf_report is not None:
                ts_raw  = writer.write_all(pf_report, elmres, clear_existing=True)
                ts_data = engine.filter_critical_series(ts_raw, config.visualizations)
                n_series = sum(len(s) for s in ts_data.sections.values())
                log.info("QDS complete — %d series in %d chart sections.",
                         n_series, len(ts_data.sections))
            else:
                log.info("QDS complete (no IntReport provided; using ElmRes directly).")
            elmres.Release()
        except Exception as exc:
            log.warning("QDS step failed: %s", exc)
            warnings.append(f"QDS step failed: {exc}")
            ts_raw = ts_data = None
    else:
        log.info("QDS step skipped (calc.run_qds=False).")

    # -- Step 2: Static results & analysis -----------------------------
    next_step("Static Results & Analysis")

    info    = reader.get_project_info()
    qds_info = reader.get_qds_info()
    switched = reader.get_switched_elements()

    if calc.run_loadflow:
        lf = reader.get_loadflow_results()
    else:
        log.info("Load flow skipped (calc.run_loadflow=False).")
        lf = _empty_loadflow()

    voltage = engine.analyze_voltages(reader.get_voltage_results()) if calc.run_voltage else []
    if not calc.run_voltage:
        log.info("Voltage analysis skipped.")

    loading = engine.analyze_thermal(reader.get_loading_results()) if calc.run_thermal else []
    if not calc.run_thermal:
        log.info("Thermal analysis skipped.")

    n1 = engine.analyze_n1(reader.get_n1_results()) if calc.run_n1 else []
    if not calc.run_n1:
        log.info("N-1 analysis skipped.")

    overall = engine.get_overall_status(voltage, loading, n1)
    log.info("Analysis complete — Status: %s, Violations: %d",
             overall.status.upper(), overall.total_violations)

    # Fall back to direct ElmRes read if QDS writer path was skipped/failed
    if ts_data is None and calc.run_qds:
        try:
            log.info("Reading time series directly from ElmRes …")
            elmres  = reader.load_elmres()
            ts_raw  = reader.get_time_series(elmres, config.visualizations)
            ts_data = engine.filter_critical_series(ts_raw, config.visualizations)
            elmres.Release()
        except Exception as exc:
            log.warning("Time series not available: %s", exc)
            warnings.append(f"Time series not available: {exc}")
            ts_raw = ts_data = TimeSeriesData(time=[])

    if ts_data is None:
        ts_raw = ts_data = TimeSeriesData(time=[])

    # Derive per-step convergence flags from time-series availability
    if ts_data and not ts_data.is_empty():
        source      = ts_raw if ts_raw and not ts_raw.is_empty() else ts_data
        lf.qds_steps = _derive_qds_steps(source)

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
    return data, warnings


# ---------------------------------------------------------------------------
# Phase 2 — report rendering
# ---------------------------------------------------------------------------

_RENDER_DISPATCH: dict[ExecutionMode, tuple[bool, bool, bool, bool]] = {
    #                                     main  exec  qds   lf
    ExecutionMode.FULL:              (True,  True,  True,  True),
    ExecutionMode.HTML_ONLY:         (True,  False, False, False),
    ExecutionMode.TABLES_ONLY:       (True,  False, False, False),
    ExecutionMode.SUMMARY_ONLY:      (False, True,  False, False),
    ExecutionMode.CALCULATIONS_ONLY: (False, False, False, False),
}


def _render_phase(
    data: ReportData,
    config: PFReportConfig,
    mode: ExecutionMode,
    data_before: ReportData | None,
    output_path: str | Path | None,
) -> dict[str, Path]:
    """Render and write HTML output files based on execution mode."""
    log_step_header("Report Generation")
    render_main, render_exec, render_qds, render_lf = _RENDER_DISPATCH.get(
        mode, (True, False, False, False)
    )
    outputs: dict[str, Path] = {}

    if render_main:
        if config.report.output_format == "multi":
            folder = MultiPageReportGenerator(config).generate(data)
            log.info("Main report folder saved: %s", folder)
            outputs["main"] = folder
        else:
            html = HTMLReportGenerator(config).generate(data)
            dest = _resolve_output_path(data, config, output_path, suffix="")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(html, encoding="utf-8")
            log.info("Main report saved: %s", dest)
            outputs["main"] = dest

    if render_exec:
        from pfreporting.report.renderers import ExecSummaryRenderer
        html = ExecSummaryRenderer(config).render(data)
        dest = _resolve_output_path(data, config, output_path, suffix="_ExecSummary")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        log.info("Executive summary saved: %s", dest)
        outputs["executive_summary"] = dest

    if render_qds and config.calc.run_qds and not data.ts_data.is_empty():
        from pfreporting.report.renderers import QDSDetailRenderer
        html = QDSDetailRenderer(config).render(data)
        dest = _resolve_output_path(data, config, output_path, suffix="_QDSDetail")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        log.info("QDS detail report saved: %s", dest)
        outputs["qds_detail"] = dest

    if render_lf and data_before is not None:
        from pfreporting.report.renderers import LoadFlowComparisonRenderer
        html = LoadFlowComparisonRenderer(config).render(data, data_before)
        dest = _resolve_output_path(data, config, output_path, suffix="_LFComparison")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        log.info("Load-flow comparison saved: %s", dest)
        outputs["loadflow_comparison"] = dest

    log.info("")
    log.info("=" * 60)
    log.info("  DONE")
    log.info("=" * 60)
    return outputs


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _resolve_output_path(
    data: ReportData,
    config: PFReportConfig,
    override: str | Path | None,
    suffix: str = "",
) -> Path:
    if override:
        p = Path(override)
        if p.suffix == ".html":
            return p.with_name(p.stem + suffix + ".html")
        return p / _default_filename(data, suffix)
    base = Path(config.report.output_dir)
    if config.report.use_timestamp_subdir:
        base = base / f"{datetime.date.today().isoformat()}_{data.info.project}"
    return base / _default_filename(data, suffix)


def _default_filename(data: ReportData, suffix: str = "") -> str:
    ts        = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = data.info.project.replace(" ", "_")[:40]
    return f"DeEnergizationAssessment_{safe_name}_{ts}{suffix}.html"


def _derive_qds_steps(ts_data: TimeSeriesData) -> list[QDSStep]:
    all_series = [ts for sec in ts_data.sections.values() for ts in sec.values()]
    return [
        QDSStep(
            time_h=t,
            converged=(
                any(i < len(s.values) and s.values[i] is not None for s in all_series)
                if all_series else True
            ),
        )
        for i, t in enumerate(ts_data.time)
    ]


def _empty_loadflow() -> LoadFlowResult:
    return LoadFlowResult(
        converged=False,
        status_text="Not calculated",
        iterations=0,
        total_load_mw=0.0,
        total_gen_mw=0.0,
        losses_mw=0.0,
    )
