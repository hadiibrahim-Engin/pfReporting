"""
PFTableWriter – Writes ElmRes time series into PowerFactory IntReport tables.

Table naming convention (per VizRequest):
    Main table:  {chart_id}_TS
    Meta table:  {chart_id}_TS_Meta

Main table structure:
    time          [double]  – Time [h]
    time_string   [string]  – Time as formatted string
    {elem_1}      [double]  – Time series element 1
    {elem_2}      [double]  – Time series element 2   (up to max_elements)
    …

Meta table structure (always row 0):
    {elem_1}_desc        [string]  – Description (long)
    {elem_1}_short_desc  [string]  – Description (short)
    {elem_1}_unit        [string]  – Unit
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
from pfreporting.models import TimeSeries, TimeSeriesData
from pfreporting.utils import sanitize_name

log = logging.getLogger("pfreporting")

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
    """Main table name for a VizRequest."""
    return f"{chart_id}_TS"


def meta_table_name(chart_id: str) -> str:
    """Meta table name for a VizRequest."""
    return f"{chart_id}_TS_Meta"


class PFTableWriter:
    """
    Writes ElmRes time series into PowerFactory IntReport tables.

    Follows exactly the structure of the reference script, generalized
    for arbitrary combinations of element class + result variable.
    """

    def __init__(self, app: Any, config: PFReportConfig) -> None:
        self._app = app
        self._cfg = config

    # ── Public API ────────────────────────────────────────────────────────

    def run_qds(self):
        """
        Execute the QDS calculation (ComStatsim) and return the loaded
        ElmRes object. Raises ReaderError if no ElmRes is found.
        """
        app = self._app
        try:
            qds = app.GetFromStudyCase("ComStatsim")
            if qds:
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
        Write all configured VizRequests into IntReport tables.

        Parameters
        ----------
        report:         IntReport object (from script.GetParent())
        elmres:         Loaded ElmRes object
        clear_existing: If True, report.Reset() is called (deletes all
                        existing tables in the IntReport)

        Returns
        -------
        TimeSeriesData  – Directly usable by the HTML generator (no re-read needed)
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

        # Per VizRequest: write tables
        all_sections: dict[str, dict[str, TimeSeries]] = {}

        for vr in self._cfg.visualizations:
            key = (vr.element_class, vr.variable)
            cols = col_index.get(key, [])[:vr.max_elements]

            if not cols:
                log.debug(
                    "No columns for %s / %s – skipped.", vr.element_class, vr.variable
                )
                continue

            section = self._write_viz_request(report, elmres, vr, cols, time_values, nrows)
            all_sections[vr.chart_id] = section
            log.info(
                "Table written: %s (%d elements)",
                table_name(vr.chart_id),
                len(section),
            )

        return TimeSeriesData(time=time_values, sections=all_sections)

    # ── Per VizRequest ────────────────────────────────────────────────────

    def _write_viz_request(
        self,
        report: Any,
        elmres: Any,
        vr: VizRequest,
        columns: list[tuple[str, int, Any]],  # (col_name, col_idx, obj)
        time_values: list[float],
        nrows: int,
    ) -> dict[str, TimeSeries]:
        """Write main + meta table for a VizRequest configuration."""
        cid      = vr.chart_id
        tbl_main = table_name(cid)
        tbl_meta = meta_table_name(cid)

        # ── Create main table ──────────────────────────────────────────
        report.CreateTable(tbl_main)
        report.CreateField(tbl_main, "time",        _DOUBLE)
        report.CreateField(tbl_main, "time_string", _STRING)
        for col_name, _, _ in columns:
            report.CreateField(tbl_main, col_name, _DOUBLE)

        # ── Create meta table ──────────────────────────────────────────
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

        # ── Populate main table ────────────────────────────────────────
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

        # ── Populate meta table (row 0) ────────────────────────────────
        for col_name, _, _ in columns:
            m = meta_records[col_name]
            report.SetValue(tbl_meta, col_name + _SUFFIX_DESC,       0, m["desc"])
            report.SetValue(tbl_meta, col_name + _SUFFIX_SHORT_DESC, 0, m["short_desc"])
            report.SetValue(tbl_meta, col_name + _SUFFIX_UNIT,       0, m["unit"])

        # ── Return TimeSeriesData section ──────────────────────────────
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

    # ── ElmRes access ─────────────────────────────────────────────────────

    def _load_elmres(self):
        sc = self._app.GetActiveStudyCase()
        if not sc:
            raise ReaderError("No active study case found.")
        res_name = self._cfg.report.quasi_dynamic_result_file
        res_list = sc.GetContents(res_name) or sc.GetContents("*.ElmRes")
        if not res_list:
            raise ReaderError(
                "No ElmRes object found – run simulation first."
            )
        elmres = res_list[0]
        elmres.Load()
        log.info("ElmRes loaded: %s", getattr(elmres, "loc_name", "?"))
        return elmres

    def _read_time_vector(self, elmres: Any, nrows: int, time_col: int) -> list[float]:
        values: list[float] = []
        for row in range(nrows):
            val = self._get_val(elmres, row, time_col)
            values.append(val if val is not None else float(row))
        return values

    def _index_columns(
        self, elmres: Any, ncols: int
    ) -> dict[tuple[str, str], list[tuple[str, int, Any]]]:
        """
        Return a dict: (element_class, variable) → [(col_name, col_idx, obj), …].
        Names are sanitized and made unique.
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
        for cand in ("t", "time", "Time", "TIME"):
            try:
                idx = elmres.FindColumn(cand)
                if isinstance(idx, int) and idx >= 0:
                    return idx
            except Exception:
                pass
        return 0

    def _get_val(self, elmres: Any, row: int, col: int) -> float | None:
        try:
            _, val = elmres.GetValue(row, col)
            if val is not None and self._app.IsNAN(val):
                return None
            return float(val) if val is not None else None
        except Exception:
            return None

    @staticmethod
    def _safe_get(obj: Any, method_name: str, *args) -> str:
        try:
            return str(getattr(obj, method_name)(*args) or "")
        except Exception:
            return ""
