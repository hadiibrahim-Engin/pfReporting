"""
PFTableReader – Liest Zeitreihen aus PowerFactory IntReport-Tabellen zurück.

Liest genau die Tabellenstruktur, die PFTableWriter erstellt hat:
    {chart_id}_TS       – Haupttabelle
    {chart_id}_TS_Meta  – Metatabelle

Verwendung:
    reader  = PFTableReader(app, config)
    ts_data = reader.read_all(report)
"""
from __future__ import annotations

import logging
from typing import Any

from freischaltung.config import FreischaltungConfig, VizRequest
from freischaltung.db_writer import _SUFFIX_UNIT, meta_table_name, table_name
from freischaltung.models import TimeSeries, TimeSeriesData

log = logging.getLogger("freischaltung")


class PFTableReader:
    """
    Liest persistierte IntReport-Tabellen zurück und baut TimeSeriesData auf.

    Nützlich, wenn Step 1 (Schreiben) und Step 2 (Report-Generierung)
    in getrennten PowerFactory-Sitzungen ausgeführt werden.
    """

    def __init__(self, app: Any, config: FreischaltungConfig) -> None:
        self._app = app
        self._cfg = config

    # ── Öffentliche API ───────────────────────────────────────────────────

    def read_all(self, report: Any) -> TimeSeriesData:
        """
        Liest alle in der Konfiguration vorgesehenen VizRequest-Tabellen.

        Parameters
        ----------
        report:  IntReport-Objekt (aus script.GetParent())

        Returns
        -------
        TimeSeriesData  mit einem Abschnitt pro vorhandener Tabelle
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
            "IntReport gelesen: %d Abschnitte, %d Zeitschritte",
            len(sections),
            len(time_values),
        )
        return TimeSeriesData(time=time_values, sections=sections)

    # ── Pro VizRequest ────────────────────────────────────────────────────

    def _read_viz_request(
        self, report: Any, vr: VizRequest
    ) -> tuple[list[float], dict[str, TimeSeries]] | None:
        """Liest Haupt- und Metatabelle für eine VizRequest-Konfiguration."""
        cid      = vr.chart_id
        tbl_main = table_name(cid)
        tbl_meta = meta_table_name(cid)

        try:
            nrows = report.GetNumberOfRows(tbl_main)
        except Exception:
            log.debug("Tabelle nicht gefunden: %s – übersprungen.", tbl_main)
            return None

        if nrows == 0:
            return None

        # ── Feldnamen lesen ───────────────────────────────────────────
        col_names = self._get_field_names(report, tbl_main, nrows, vr)
        if not col_names:
            return None

        # ── Einheiten aus Metatabelle ─────────────────────────────────
        units: dict[str, str] = {}
        try:
            for cn in col_names:
                units[cn] = self._safe_get_val(report, tbl_meta, cn + _SUFFIX_UNIT, 0) or vr.unit
        except Exception:
            units = {cn: vr.unit for cn in col_names}

        # ── Zeitvektor lesen ──────────────────────────────────────────
        time_values: list[float] = []
        for row in range(nrows):
            t = self._safe_get_val(report, tbl_main, "time", row)
            time_values.append(float(t) if t is not None else float(row))

        # ── Zeitreihen lesen ──────────────────────────────────────────
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
        log.debug("Tabelle gelesen: %s (%d Zeilen, %d Serien)", tbl_main, nrows, len(section))
        return time_values, section

    # ── Feldnamen ermitteln ───────────────────────────────────────────────

    def _get_field_names(
        self, report: Any, tbl: str, nrows: int, vr: VizRequest
    ) -> list[str]:
        """
        Versucht die Feldnamen über die PF-API zu lesen.
        Fallback: Alle Felder außer 'time' und 'time_string' als Elementnamen.
        """
        try:
            # PowerFactory ≥ 2024 stellt GetFieldNames bereit
            all_fields = report.GetFieldNames(tbl)
            return [f for f in all_fields if f not in ("time", "time_string")]
        except Exception:
            pass

        # Fallback: alle Felder systematisch ermitteln
        return self._probe_field_names(report, tbl, nrows)

    def _probe_field_names(self, report: Any, tbl: str, nrows: int) -> list[str]:
        """
        Liest so lange Feldnamen, bis GetValue für eine Zeile scheitert.
        Nicht robust, aber besser als gar nichts wenn GetFieldNames fehlt.
        """
        # Nicht implementierbar ohne bekannte Feldnamen → leere Liste
        # In der Praxis sollte GetFieldNames immer verfügbar sein.
        log.warning(
            "GetFieldNames nicht verfügbar für Tabelle '%s'. "
            "Zeitreihen können nicht gelesen werden. "
            "Direkt-Workflow (write_all → TimeSeriesData) verwenden.",
            tbl,
        )
        return []

    # ── Hilfsmethoden ─────────────────────────────────────────────────────

    @staticmethod
    def _safe_get_val(report: Any, tbl: str, field: str, row: int) -> Any:
        try:
            return report.GetValue(tbl, field, row)
        except Exception:
            return None
