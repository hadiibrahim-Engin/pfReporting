"""
PFTableWriter — writes ElmRes time series into PowerFactory IntReport tables.

Table naming convention (per VizRequest):
    Main table : {chart_id}_TS
    Meta table : {chart_id}_TS_Meta

Main table structure:
    time          [double] — simulation time [h]
    time_string   [string] — formatted time string
    {elem_1..N}   [double] — one column per element (up to max_elements)

Meta table structure (always row 0):
    {elem}_desc        [string]
    {elem}_short_desc  [string]
    {elem}_unit        [string]
"""
from __future__ import annotations

import json
from typing import Any

from pfreporting.config import PFReportConfig, VizRequest
from pfreporting.elmres import ElmResHelper
from pfreporting.exceptions import ReaderError
from pfreporting.logger import get_logger
from pfreporting.models import TimeSeries, TimeSeriesData
from pfreporting.utils import resolve_qds_datetime_hours
from pfreporting import pf_attrs as pfa

log = get_logger()

# IntReport field-type constants
_STRING  = 0
_DOUBLE  = 2

_SUFFIX_DESC       = "_desc"
_SUFFIX_SHORT_DESC = "_short_desc"
_SUFFIX_UNIT       = "_unit"
_META_COLUMNS_FIELD = "__columns__"


def table_name(chart_id: str) -> str:
    return f"{chart_id}_TS"


def meta_table_name(chart_id: str) -> str:
    return f"{chart_id}_TS_Meta"


class PFTableWriter:
    """Writes ElmRes time series into PowerFactory IntReport tables."""

    def __init__(self, app: Any, config: PFReportConfig) -> None:
        self._app = app
        self._cfg = config

    # -- Public API --------------------------------------------------------

    def run_qds(self) -> Any:
        """Execute ComStatsim and return the loaded ElmRes object."""
        app = self._app
        qds_cfg = self._cfg.qds
        try:
            qds = app.GetFromStudyCase("ComStatsim")
            if qds:
                sc = app.GetActiveStudyCase()
                study_time_start_raw = getattr(sc, pfa.STUDY_TIME, None) if sc else None

                dt_start_h, dt_end_h, dt_notes = resolve_qds_datetime_hours(
                    qds_cfg.start_datetime, qds_cfg.end_datetime, study_time_start_raw,
                )
                for note in dt_notes:
                    log.warning("QDS datetime override: %s", note)

                eff_t_start = qds_cfg.t_start
                eff_t_end   = qds_cfg.t_end
                if dt_start_h is not None:
                    if qds_cfg.t_start is not None:
                        log.info("QDS t_start ignored because start_datetime is set.")
                    eff_t_start = dt_start_h
                    log.info("QDS start_datetime '%s' → Tstart=%.6f h",
                             qds_cfg.start_datetime, eff_t_start)
                if dt_end_h is not None:
                    if qds_cfg.t_end is not None:
                        log.info("QDS t_end ignored because end_datetime is set.")
                    eff_t_end = dt_end_h
                    log.info("QDS end_datetime '%s' → Tshow=%.6f h",
                             qds_cfg.end_datetime, eff_t_end)

                if eff_t_start is not None:
                    qds.Tstart = eff_t_start
                if eff_t_end is not None:
                    qds.Tshow = eff_t_end
                if qds_cfg.dt is not None:
                    qds.dt = qds_cfg.dt

                log.info("Running QDS calculation (ComStatsim) …")
                app.EchoOff()
                qds.Execute()
                app.EchoOn()
                log.info("QDS calculation complete.")
        except Exception as exc:
            app.EchoOn()
            log.warning("ComStatsim not found or failed: %s", exc)

        return self._load_elmres()

    def write_all(
        self,
        report: Any,
        elmres: Any,
        clear_existing: bool = True,
    ) -> TimeSeriesData:
        """Write all configured VizRequests into IntReport tables.

        Returns a TimeSeriesData mirroring what was written, ready for the
        HTML generator.
        """
        if clear_existing:
            report.Reset()
            log.info("IntReport reset (all tables deleted).")

        helper = ElmResHelper(self._app, elmres)
        nrows  = helper.nrows
        log.info("ElmRes: %d time steps, %d columns", nrows, helper.ncols)

        time_values = helper.get_column(helper.find_time_col())
        time_values = [v if v is not None else float(i) for i, v in enumerate(time_values)]

        # Build column index once — shared across all VizRequests
        col_index = helper.build_column_index()
        self._log_index_summary(col_index)
        self._log_vizrequest_validation(col_index)

        all_sections: dict[str, dict[str, TimeSeries]] = {}
        for vr in self._cfg.visualizations:
            key  = (vr.element_class, vr.variable)
            cols = col_index.get(key, [])[:vr.max_elements]
            if not cols:
                log.warning(
                    "No ElmRes columns for %s/%s (chart_id=%s) — skipped.",
                    vr.element_class, vr.variable, vr.chart_id,
                )
                continue
            section = self._write_viz_request(report, helper, vr, cols, time_values)
            all_sections[vr.chart_id] = section
            log.info("Table written: %s (%d elements)", table_name(vr.chart_id), len(section))

        if not all_sections:
            log.warning(
                "No IntReport tables created. Check element_class/variable pairs."
            )

        return TimeSeriesData(time=time_values, sections=all_sections)

    # -- Per VizRequest ----------------------------------------------------

    def _write_viz_request(
        self,
        report: Any,
        helper: ElmResHelper,
        vr: VizRequest,
        columns: list[tuple[str, int, Any]],
        time_values: list[float],
    ) -> dict[str, TimeSeries]:
        cid      = vr.chart_id
        tbl_main = table_name(cid)
        tbl_meta = meta_table_name(cid)

        # -- Create tables --------------------------------------------------
        report.CreateTable(tbl_main)
        report.CreateField(tbl_main, "time",        _DOUBLE)
        report.CreateField(tbl_main, "time_string", _STRING)
        for col_name, _, _ in columns:
            report.CreateField(tbl_main, col_name, _DOUBLE)

        report.CreateTable(tbl_meta)
        report.CreateField(tbl_meta, _META_COLUMNS_FIELD, _STRING)

        meta_records: dict[str, dict] = {}
        for col_name, col_idx, _ in columns:
            desc_l = helper.get_description(col_idx, 0) or vr.variable
            desc_s = helper.get_description(col_idx, 1) or vr.variable
            unit   = helper.get_unit(col_idx) or vr.unit
            report.CreateField(tbl_meta, col_name + _SUFFIX_DESC,       _STRING)
            report.CreateField(tbl_meta, col_name + _SUFFIX_SHORT_DESC, _STRING)
            report.CreateField(tbl_meta, col_name + _SUFFIX_UNIT,       _STRING)
            meta_records[col_name] = {"desc": desc_l, "short_desc": desc_s, "unit": unit}

        # -- Read all column data upfront (one batch read per column) -------
        col_data: dict[str, list[float | None]] = {
            col_name: helper.get_column(col_idx)
            for col_name, col_idx, _ in columns
        }

        # -- Populate main table --------------------------------------------
        for row, t in enumerate(time_values):
            report.SetValue(tbl_main, "time",        row, t)
            report.SetValue(tbl_main, "time_string", row, f"{t:.6f}")
            for col_name, _, _ in columns:
                val = col_data[col_name][row] if row < len(col_data[col_name]) else None
                if val is not None:
                    report.SetValue(tbl_main, col_name, row, float(val))

        # -- Populate meta table (row 0) ------------------------------------
        report.SetValue(
            tbl_meta, _META_COLUMNS_FIELD, 0,
            json.dumps([col_name for col_name, _, _ in columns]),
        )
        for col_name, _, _ in columns:
            m = meta_records[col_name]
            report.SetValue(tbl_meta, col_name + _SUFFIX_DESC,       0, m["desc"])
            report.SetValue(tbl_meta, col_name + _SUFFIX_SHORT_DESC, 0, m["short_desc"])
            report.SetValue(tbl_meta, col_name + _SUFFIX_UNIT,       0, m["unit"])

        # -- Build TimeSeries return value ----------------------------------
        unit_first = next(
            (meta_records[cn]["unit"] for cn, _, _ in columns if cn in meta_records),
            vr.unit,
        )
        return {
            col_name: TimeSeries(
                element_class=vr.element_class,
                variable=vr.variable,
                label=vr.label,
                unit=unit_first,
                values=col_data[col_name],
            )
            for col_name, _, _ in columns
        }

    # -- ElmRes helpers ----------------------------------------------------

    def _load_elmres(self) -> Any:
        sc = self._app.GetActiveStudyCase()
        if not sc:
            raise ReaderError("No active study case found.")
        res_name = self._cfg.report.quasi_dynamic_result_file
        res_list = sc.GetContents(res_name) or sc.GetContents("*.ElmRes")
        if not res_list:
            raise ReaderError("No ElmRes object found — run simulation first.")
        elmres = res_list[0]
        elmres.Load()
        log.info("ElmRes loaded: %s", getattr(elmres, "loc_name", "?"))
        return elmres

    # -- Logging helpers ---------------------------------------------------

    def _log_index_summary(
        self, col_index: dict[tuple[str, str], list]
    ) -> None:
        keys = sorted(col_index.keys())
        if not keys:
            log.warning("ElmRes index is empty — no object/variable channels detected.")
            return
        preview = ", ".join(f"{c}/{v}" for c, v in keys[:10])
        suffix  = " …" if len(keys) > 10 else ""
        log.info("ElmRes channels: %d pairs: %s%s", len(keys), preview, suffix)

    def _log_vizrequest_validation(
        self, col_index: dict[tuple[str, str], list]
    ) -> None:
        missing = [
            vr for vr in self._cfg.visualizations
            if (vr.element_class, vr.variable) not in col_index
        ]
        if not missing:
            log.info("VizRequest validation: all %d matched.", len(self._cfg.visualizations))
            return
        preview = ", ".join(
            f"{vr.element_class}/{vr.variable}({vr.chart_id})"
            for vr in missing[:6]
        )
        suffix = " …" if len(missing) > 6 else ""
        log.warning(
            "VizRequest mismatches: %d/%d not found: %s%s",
            len(missing), len(self._cfg.visualizations), preview, suffix,
        )
