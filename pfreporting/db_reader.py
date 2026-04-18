"""
PFTableReader - Reads time series back from PowerFactory IntReport tables.

Reads exactly the table structure that PFTableWriter created:
    {chart_id}_TS       - Main table
    {chart_id}_TS_Meta  - Meta table

Usage:
    reader  = PFTableReader(app, config)
    ts_data = reader.read_all(report)
"""
from __future__ import annotations

import logging
from typing import Any

from pfreporting.config import PFReportConfig, VizRequest
from pfreporting.db_writer import _SUFFIX_UNIT, meta_table_name, table_name
from pfreporting.models import TimeSeries, TimeSeriesData

log = logging.getLogger("pfreporting")


class PFTableReader:
    """
    Reads persisted IntReport tables back and builds TimeSeriesData.

    Useful when Step 1 (writing) and Step 2 (report generation)
    are executed in separate PowerFactory sessions.
    """

    def __init__(self, app: Any, config: PFReportConfig) -> None:
        """Initialize IntReport reader dependencies.

        Args:
            app: PowerFactory application object.
            config: Report configuration with visualization requests.
        """
        self._app = app
        self._cfg = config

    # -- Public API --------------------------------------------------------

    def read_all(self, report: Any) -> TimeSeriesData:
        """
        Read all VizRequest tables defined in the configuration.

        Parameters
        ----------
        report:  IntReport object (from script.GetParent())

        Returns
        -------
        TimeSeriesData with one section per existing table
        """
        time_values: list[float] = []
        sections: dict[str, dict[str, TimeSeries]] = {}

        for vr in self._cfg.visualizations:
            result = self._read_viz_request(report, vr)
            if result is None:
                continue
            t, section = result
            if not time_values and t:
                time_values = t
            sections[vr.chart_id] = section

        log.info(
            "IntReport read: %d sections, %d time steps",
            len(sections),
            len(time_values),
        )
        return TimeSeriesData(time=time_values, sections=sections)

    # -- Per VizRequest ----------------------------------------------------

    def _read_viz_request(
        self, report: Any, vr: VizRequest
    ) -> tuple[list[float], dict[str, TimeSeries]] | None:
        """Read one visualization section from IntReport tables.

        Args:
            report: IntReport object.
            vr: Visualization request defining table names and metadata.

        Returns:
            ``(time_values, section_map)`` when table data is available,
            otherwise ``None``.
        """
        cid      = vr.chart_id
        tbl_main = table_name(cid)
        tbl_meta = meta_table_name(cid)

        try:
            nrows = report.GetNumberOfRows(tbl_main)
        except Exception:
            log.debug("Table not found: %s - skipped.", tbl_main)
            return None

        if nrows == 0:
            return None

        # -- Read field names -------------------------------------------
        col_names = self._get_field_names(report, tbl_main, nrows, vr)
        if not col_names:
            return None

        # -- Units from meta table --------------------------------------
        units: dict[str, str] = {}
        try:
            for cn in col_names:
                units[cn] = self._safe_get_val(report, tbl_meta, cn + _SUFFIX_UNIT, 0) or vr.unit
        except Exception:
            units = {cn: vr.unit for cn in col_names}

        # -- Read time vector -------------------------------------------
        time_values: list[float] = []
        for row in range(nrows):
            t = self._safe_get_val(report, tbl_main, "time", row)
            time_values.append(float(t) if t is not None else float(row))

        # -- Read time series -------------------------------------------
        ts_map: dict[str, list[float | None]] = {cn: [] for cn in col_names}
        for row in range(nrows):
            for cn in col_names:
                val = self._safe_get_val(report, tbl_main, cn, row)
                ts_map[cn].append(float(val) if val is not None else None)

        section = {
            cn: TimeSeries(
                element_class=vr.element_class,
                variable=vr.variable,
                label=vr.label,
                unit=units.get(cn, vr.unit),
                values=ts_map[cn],
            )
            for cn in col_names
        }
        log.debug("Table read: %s (%d rows, %d series)", tbl_main, nrows, len(section))
        return time_values, section

    # -- Determine field names ---------------------------------------------

    def _get_field_names(
        self, report: Any, tbl: str, nrows: int, vr: VizRequest
    ) -> list[str]:
        """
        Read available field names for one IntReport time-series table.

        Args:
            report: IntReport object.
            tbl: Main table name.
            nrows: Number of rows in the table (reserved for compatibility).
            vr: Visualization request (reserved for compatibility).

        Returns:
            Data-field names excluding ``time`` and ``time_string``.

        PowerFactory versions that expose ``GetFieldNames`` return a full list
        that is filtered to remove ``time`` and ``time_string``.
        """
        try:
            # PowerFactory >= 2024 provides GetFieldNames
            all_fields = report.GetFieldNames(tbl)
            return [f for f in all_fields if f not in ("time", "time_string")]
        except Exception:
            pass

        return self._probe_field_names(report, tbl, nrows)

    def _probe_field_names(self, report: Any, tbl: str, nrows: int) -> list[str]:
        """
        Fallback when PF does not expose ``GetFieldNames``.

        Args:
            report: IntReport object.
            tbl: Main table name.
            nrows: Number of rows (reserved for compatibility).

        Returns:
            Empty list, because reliable probing is not supported.

        IntReport does not provide a reliable reverse lookup for unknown field
        names in older APIs, so this fallback intentionally returns no columns.
        Use the direct workflow (write and consume ``TimeSeriesData`` in one
        session) when this warning occurs.
        """
        log.warning(
            "GetFieldNames not available for table '%s'. "
            "Time series cannot be read. "
            "Use direct workflow (write_all -> TimeSeriesData).",
            tbl,
        )
        return []

    # -- Helper methods ----------------------------------------------------

    @staticmethod
    def _safe_get_val(report: Any, tbl: str, field: str, row: int) -> Any:
        """Read one IntReport cell safely.

        Args:
            report: IntReport object.
            tbl: Table name.
            field: Field/column name.
            row: Row index.

        Returns:
            Cell value or ``None`` when access fails.
        """
        try:
            return report.GetValue(tbl, field, row)
        except Exception:
            return None
