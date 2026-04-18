"""
PFTableWriter - Writes ElmRes time series into PowerFactory IntReport tables.

Table naming convention (per VizRequest):
    Main table:  {chart_id}_TS
    Meta table:  {chart_id}_TS_Meta

Main table structure:
    time          [double]  - Time [h]
    time_string   [string]  - Time as formatted string
    {elem_1}      [double]  - Time series element 1
    {elem_2}      [double]  - Time series element 2   (up to max_elements)
    …

Meta table structure (always row 0):
    {elem_1}_desc        [string]  - Description (long)
    {elem_1}_short_desc  [string]  - Description (short)
    {elem_1}_unit        [string]  - Unit
    …

Usage:
    writer  = PFTableWriter(app, config)
    elmres  = writer.run_qds()          # run QDS + load ElmRes
    ts_data = writer.write_all(report, elmres)
    elmres.Release()
"""
from __future__ import annotations

import logging
from typing import Any

from pfreporting.config import PFReportConfig, VizRequest
from pfreporting.exceptions import ReaderError
from pfreporting.logger import get_logger
from pfreporting.models import TimeSeries, TimeSeriesData
from pfreporting.utils import resolve_qds_datetime_hours, sanitize_name

log = get_logger()

# IntReport field types (PowerFactory constants)
_STRING  = 0
_INTEGER = 1
_DOUBLE  = 2
_OBJECT  = 3

# Metadata suffixes
_SUFFIX_DESC       = "_desc"
_SUFFIX_SHORT_DESC = "_short_desc"
_SUFFIX_UNIT       = "_unit"


def table_name(chart_id: str) -> str:
    """Return IntReport main table name for one chart section.

    Args:
        chart_id: Visualization chart id.

    Returns:
        Main table name with ``_TS`` suffix.
    """
    return f"{chart_id}_TS"


def meta_table_name(chart_id: str) -> str:
    """Return IntReport metadata table name for one chart section.

    Args:
        chart_id: Visualization chart id.

    Returns:
        Metadata table name with ``_TS_Meta`` suffix.
    """
    return f"{chart_id}_TS_Meta"


class PFTableWriter:
    """
    Writes ElmRes time series into PowerFactory IntReport tables.

    Follows exactly the structure of the reference script, generalized
    for arbitrary combinations of element class + result variable.
    """

    def __init__(self, app: Any, config: PFReportConfig) -> None:
        """Initialize IntReport writer dependencies.

        Args:
            app: PowerFactory application object.
            config: Report configuration with visualization requests.
        """
        self._app = app
        self._cfg = config

    # -- Public API --------------------------------------------------------

    def run_qds(self):
        """
        Execute ``ComStatsim`` and return the loaded ElmRes object.

        If ``config.qds.t_start``, ``t_end`` or ``dt`` are set, those values
        are applied to the PF command object before execution.

        Returns:
            Loaded ElmRes object produced by the QDS run.

        Raises:
            ReaderError: If no suitable ElmRes object can be found afterward.

        Notes:
            PF attribute names (``Tstart``, ``Tshow``, ``dt``) may differ across
            PowerFactory versions.
        """
        app = self._app
        qds_cfg = self._cfg.qds
        try:
            qds = app.GetFromStudyCase("ComStatsim")
            if qds:
                sc = app.GetActiveStudyCase()
                study_time_start_raw = getattr(sc, "iStudyTime", None) if sc else None

                dt_start_h, dt_end_h, dt_notes = resolve_qds_datetime_hours(
                    qds_cfg.start_datetime,
                    qds_cfg.end_datetime,
                    study_time_start_raw,
                )
                for note in dt_notes:
                    log.warning("QDS datetime override: %s", note)

                eff_t_start = qds_cfg.t_start
                eff_t_end = qds_cfg.t_end
                if dt_start_h is not None:
                    if qds_cfg.t_start is not None:
                        log.info("QDS t_start ignored because start_datetime is set.")
                    eff_t_start = dt_start_h
                    log.info(
                        "QDS start_datetime '%s' mapped to Tstart=%.6f h",
                        qds_cfg.start_datetime,
                        eff_t_start,
                    )
                if dt_end_h is not None:
                    if qds_cfg.t_end is not None:
                        log.info("QDS t_end ignored because end_datetime is set.")
                    eff_t_end = dt_end_h
                    log.info(
                        "QDS end_datetime '%s' mapped to Tshow=%.6f h",
                        qds_cfg.end_datetime,
                        eff_t_end,
                    )

                # Apply time range overrides from config (if set)
                if eff_t_start is not None:
                    qds.Tstart = eff_t_start
                    log.info("QDS t_start overridden to %.6f h", eff_t_start)
                if eff_t_end is not None:
                    qds.Tshow = eff_t_end
                    log.info("QDS t_end overridden to %.6f h", eff_t_end)
                if qds_cfg.dt is not None:
                    qds.dt = qds_cfg.dt
                    log.info("QDS dt overridden to %.4f h", qds_cfg.dt)

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
        """
        Write all configured visualization requests into IntReport tables.

        Parameters
        ----------
        report:         IntReport object (from script.GetParent())
        elmres:         Loaded ElmRes object
        clear_existing: If True, report.Reset() is called (deletes all
                        existing tables in the IntReport)

        Returns
        -------
        TimeSeriesData that mirrors what was written to IntReport tables and
        can be passed directly to the HTML generator.

        Notes:
            With ``clear_existing=True``, ``report.Reset()`` removes all tables
            currently stored in the target IntReport.
        """
        if clear_existing:
            report.Reset()
            log.info("IntReport reset (all tables deleted).")

        nrows: int = elmres.GetNumberOfRows()
        ncols: int = elmres.GetNumberOfColumns()
        time_col = self._find_time_col(elmres)

        log.info("ElmRes: %d time steps, %d columns", nrows, ncols)

        # Build time vector
        time_values = self._read_time_vector(elmres, nrows, time_col)

        # Index all columns by VizRequest
        col_index = self._index_columns(elmres, ncols)
        self._log_elmres_index_summary(col_index)
        self._log_vizrequest_validation(col_index)

        # Per VizRequest: write tables
        all_sections: dict[str, dict[str, TimeSeries]] = {}

        for vr in self._cfg.visualizations:
            key = (vr.element_class, vr.variable)
            cols = col_index.get(key, [])[:vr.max_elements]

            if not cols:
                log.warning(
                    "No ElmRes columns for %s / %s (chart_id=%s) - section skipped.",
                    vr.element_class,
                    vr.variable,
                    vr.chart_id,
                )
                continue

            section = self._write_viz_request(report, elmres, vr, cols, time_values, nrows)
            all_sections[vr.chart_id] = section
            log.info(
                "Table written: %s (%d elements)",
                table_name(vr.chart_id),
                len(section),
            )

        if not all_sections:
            log.warning(
                "No IntReport tables were created from configured VizRequests. "
                "Check element_class/variable pairs against available ElmRes columns."
            )

        return TimeSeriesData(time=time_values, sections=all_sections)

    def _log_elmres_index_summary(
        self, col_index: dict[tuple[str, str], list[tuple[str, int, Any]]]
    ) -> None:
        """Log compact summary of available ElmRes (class, variable) channels."""
        keys = sorted(col_index.keys())
        if not keys:
            log.warning("ElmRes index is empty - no object/variable channels detected.")
            return

        preview_count = 10
        preview = ", ".join(f"{cls}/{var}" for cls, var in keys[:preview_count])
        suffix = " ..." if len(keys) > preview_count else ""
        log.info(
            "ElmRes channels available: %d (class/variable pairs): %s%s",
            len(keys),
            preview,
            suffix,
        )

    def _log_vizrequest_validation(
        self, col_index: dict[tuple[str, str], list[tuple[str, int, Any]]]
    ) -> None:
        """Validate configured VizRequests against indexed ElmRes channels."""
        missing = [
            vr
            for vr in self._cfg.visualizations
            if (vr.element_class, vr.variable) not in col_index
        ]
        if not missing:
            log.info(
                "VizRequest validation: all %d requests matched ElmRes.",
                len(self._cfg.visualizations),
            )
            return

        preview_count = 6
        preview = ", ".join(
            f"{vr.element_class}/{vr.variable}({vr.chart_id})"
            for vr in missing[:preview_count]
        )
        suffix = " ..." if len(missing) > preview_count else ""
        log.warning(
            "VizRequest mismatches: %d/%d not found in ElmRes: %s%s",
            len(missing),
            len(self._cfg.visualizations),
            preview,
            suffix,
        )

    # -- Per VizRequest ----------------------------------------------------

    def _write_viz_request(
        self,
        report: Any,
        elmres: Any,
        vr: VizRequest,
        columns: list[tuple[str, int, Any]],  # (col_name, col_idx, obj)
        time_values: list[float],
        nrows: int,
    ) -> dict[str, TimeSeries]:
        """Write one visualization section into main and metadata tables.

        Args:
            report: IntReport object to write into.
            elmres: Loaded ElmRes object.
            vr: Visualization request for section metadata and limits.
            columns: Selected columns as ``(name, index, object)`` tuples.
            time_values: Time axis values for all rows.
            nrows: Number of time steps to write.

        Returns:
            ``dict[element_name, TimeSeries]`` for the written section.

        Main table schema:
            - ``time``: numeric simulation time value
            - ``time_string``: formatted time string
            - one numeric field per selected element series

        Meta table schema (row 0):
            - ``<field>_desc`` and ``<field>_short_desc``
            - ``<field>_unit``
        """
        cid      = vr.chart_id
        tbl_main = table_name(cid)
        tbl_meta = meta_table_name(cid)

        # -- Create main table ------------------------------------------
        report.CreateTable(tbl_main)
        report.CreateField(tbl_main, "time",        _DOUBLE)
        report.CreateField(tbl_main, "time_string", _STRING)
        for col_name, _, _ in columns:
            report.CreateField(tbl_main, col_name, _DOUBLE)

        # -- Create meta table ------------------------------------------
        report.CreateTable(tbl_meta)
        meta_records: dict[str, dict] = {}
        for col_name, col_idx, _ in columns:
            desc_l  = self._safe_get(elmres, "GetDescription", col_idx, 0) or vr.variable
            desc_s  = self._safe_get(elmres, "GetDescription", col_idx, 1) or vr.variable
            unit    = self._safe_get(elmres, "GetUnit",        col_idx)    or vr.unit

            report.CreateField(tbl_meta, col_name + _SUFFIX_DESC,       _STRING)
            report.CreateField(tbl_meta, col_name + _SUFFIX_SHORT_DESC, _STRING)
            report.CreateField(tbl_meta, col_name + _SUFFIX_UNIT,       _STRING)

            meta_records[col_name] = {"desc": desc_l, "short_desc": desc_s, "unit": unit}

        # -- Populate main table ----------------------------------------
        ts_map: dict[str, list[float | None]] = {cn: [] for cn, _, _ in columns}

        for row in range(nrows):
            t = time_values[row]
            report.SetValue(tbl_main, "time", row, t)
            report.SetValue(tbl_main, "time_string", row, f"{t:.6f}")

            for col_name, col_idx, _ in columns:
                val = self._get_val(elmres, row, col_idx)
                if val is not None:
                    report.SetValue(tbl_main, col_name, row, float(val))
                ts_map[col_name].append(val)

        # -- Populate meta table (row 0) --------------------------------
        for col_name, _, _ in columns:
            m = meta_records[col_name]
            report.SetValue(tbl_meta, col_name + _SUFFIX_DESC,       0, m["desc"])
            report.SetValue(tbl_meta, col_name + _SUFFIX_SHORT_DESC, 0, m["short_desc"])
            report.SetValue(tbl_meta, col_name + _SUFFIX_UNIT,       0, m["unit"])

        # -- Return TimeSeriesData section ------------------------------
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
                values=ts_map[col_name],
            )
            for col_name, _, _ in columns
        }

    # -- ElmRes access -----------------------------------------------------

    def _load_elmres(self):
        """Load configured ElmRes object from active study case.

        Returns:
            Loaded ElmRes object.

        Raises:
            ReaderError: If no study case or matching result file is available.
        """
        sc = self._app.GetActiveStudyCase()
        if not sc:
            raise ReaderError("No active study case found.")
        res_name = self._cfg.report.quasi_dynamic_result_file
        res_list = sc.GetContents(res_name) or sc.GetContents("*.ElmRes")
        if not res_list:
            raise ReaderError(
                "No ElmRes object found - run simulation first."
            )
        elmres = res_list[0]
        elmres.Load()
        log.info("ElmRes loaded: %s", getattr(elmres, "loc_name", "?"))
        return elmres

    def _read_time_vector(self, elmres: Any, nrows: int, time_col: int) -> list[float]:
        """Read the simulation time column with row-index fallback.

        Args:
            elmres: Loaded ElmRes object.
            nrows: Number of rows to read.
            time_col: Resolved time column index.

        Returns:
            Time vector with ``nrows`` entries.

        If a time value cannot be read for a row, that row index is used as a
        stable monotonic substitute.
        """
        values: list[float] = []
        for row in range(nrows):
            val = self._get_val(elmres, row, time_col)
            values.append(val if val is not None else float(row))
        return values

    def _index_columns(
        self, elmres: Any, ncols: int
    ) -> dict[tuple[str, str], list[tuple[str, int, Any]]]:
        """
        Build an ElmRes column index grouped by ``(element_class, variable)``.

        Args:
            elmres: Loaded ElmRes object.
            ncols: Number of ElmRes columns.

        Returns:
            Mapping of ``(class_name, variable)`` to tuples of
            ``(column_name, column_index, pf_object)``.

        Notes:
            Column names are sanitized and deduplicated per key by appending
            ``_2``, ``_3``, ... as required.
        """
        index: dict[tuple[str, str], list] = {}
        seen: dict[tuple[str, str], set[str]] = {}

        for col in range(ncols):
            try:
                obj = elmres.GetObject(col)
                if obj is None:
                    continue
                cls_name: str = obj.GetClassName()
                var: str = elmres.GetVariable(col)
            except Exception:
                continue

            key = (cls_name, var)
            if key not in index:
                index[key] = []
                seen[key] = set()

            # Generate unique name
            try:
                base = getattr(obj, "loc_name", None) or f"{cls_name}_{col}"
            except Exception:
                base = f"{cls_name}_{col}"

            col_name = sanitize_name(base)
            k = 2
            while col_name in seen[key]:
                col_name = f"{sanitize_name(base)}_{k}"
                k += 1
            seen[key].add(col_name)

            index[key].append((col_name, col, obj))

        return index

    @staticmethod
    def _find_time_col(elmres: Any) -> int:
        """Locate a time column by common field names.

        Args:
            elmres: Loaded ElmRes object.

        Returns:
            Column index for time values.

        Returns column index 0 when no known time variable is found.
        """
        for cand in ("t", "time", "Time", "TIME"):
            try:
                idx = elmres.FindColumn(cand)
                if isinstance(idx, int) and idx >= 0:
                    return idx
            except Exception:
                pass
        return 0

    def _get_val(self, elmres: Any, row: int, col: int) -> float | None:
        """Read one scalar ElmRes value safely.

        Args:
            elmres: Loaded ElmRes object.
            row: Row index.
            col: Column index.

        Returns:
            Float value or ``None`` for NaN/missing/error.
        """
        try:
            _, val = elmres.GetValue(row, col)
            if val is not None and self._app.IsNAN(val):
                return None
            return float(val) if val is not None else None
        except Exception:
            return None

    @staticmethod
    def _safe_get(obj: Any, method_name: str, *args) -> str:
        """Call PF accessor and stringify result safely.

        Args:
            obj: Object exposing the method.
            method_name: Accessor method name.
            *args: Positional arguments forwarded to the accessor.

        Returns:
            String result, or an empty string on error.
        """
        try:
            return str(getattr(obj, method_name)(*args) or "")
        except Exception:
            return ""


class PFTimeSeriesWriter:
    """
    High-level wrapper: writes ElmRes time series to an IntReport — one table
    per VizRequest. Generalizes the ScriptedLineTimeSeries pattern to all
    configured element classes.

    Usage (after QDS has run):
        writer = PFTimeSeriesWriter(app, pf_report, config)
        writer.write_all(config.report.quasi_dynamic_result_file)
    """

    def __init__(self, app: Any, report_obj: Any, config: PFReportConfig) -> None:
        """Initialize high-level writer wrapper dependencies.

        Args:
            app: PowerFactory application object.
            report_obj: IntReport object receiving output tables.
            config: Report configuration.
        """
        self._app = app
        self._report = report_obj
        self._cfg = config
        self._log = get_logger()

    def write_all(self, elmres_name: str) -> None:
        """Load named ElmRes and persist all configured time-series sections.

        Args:
            elmres_name: Preferred ElmRes object name in active study case.
        """
        sc = self._app.GetActiveStudyCase()
        if not sc:
            self._log.warning("PFTimeSeriesWriter: no active study case — skipping.")
            return

        res_list = sc.GetContents(elmres_name) or sc.GetContents("*.ElmRes")
        if not res_list:
            self._log.warning(
                "PFTimeSeriesWriter: ElmRes '%s' not found — skipping.", elmres_name
            )
            return

        elmres = res_list[0]
        try:
            elmres.Load()
        except Exception as exc:
            self._log.warning("PFTimeSeriesWriter: could not load ElmRes: %s", exc)
            return

        self._log.info(
            "PFTimeSeriesWriter: writing %d VizRequests to IntReport …",
            len(self._cfg.visualizations),
        )

        # Reuse the full PFTableWriter logic
        writer = PFTableWriter(self._app, self._cfg)
        try:
            writer.write_all(self._report, elmres, clear_existing=False)
        finally:
            try:
                elmres.Release()
            except Exception:
                pass
