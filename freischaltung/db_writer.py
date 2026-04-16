"""
PFTableWriter – Schreibt ElmRes-Zeitreihen in PowerFactory IntReport-Tabellen.

Tabellennamenskonvention (pro VizRequest):
    Haupttabelle:  {chart_id}_TS
    Metatabelle:   {chart_id}_TS_Meta

Struktur Haupttabelle:
    time          [double]  – Zeit [h]
    time_string   [string]  – Zeit als formatierter String
    {elem_1}      [double]  – Zeitreihe Element 1
    {elem_2}      [double]  – Zeitreihe Element 2   (bis max_elements)
    …

Struktur Metatabelle (immer Zeile 0):
    {elem_1}_desc        [string]  – Beschreibung (lang)
    {elem_1}_short_desc  [string]  – Beschreibung (kurz)
    {elem_1}_unit        [string]  – Einheit
    …

Verwendung:
    writer  = PFTableWriter(app, config)
    elmres  = writer.run_qds()          # QDS ausführen + ElmRes laden
    ts_data = writer.write_all(report, elmres)
    elmres.Release()
"""
from __future__ import annotations

import logging
from typing import Any

from freischaltung.config import FreischaltungConfig, VizRequest
from freischaltung.exceptions import ReaderError
from freischaltung.models import TimeSeries, TimeSeriesData
from freischaltung.utils import sanitize_name

log = logging.getLogger("freischaltung")

# IntReport-Feldtypen (PowerFactory-Konstanten)
_STRING  = 0
_INTEGER = 1
_DOUBLE  = 2
_OBJECT  = 3

# Metadaten-Suffixe
_SUFFIX_DESC       = "_desc"
_SUFFIX_SHORT_DESC = "_short_desc"
_SUFFIX_UNIT       = "_unit"


def table_name(chart_id: str) -> str:
    """Haupttabellenname für einen VizRequest."""
    return f"{chart_id}_TS"


def meta_table_name(chart_id: str) -> str:
    """Metatabellen-Name für einen VizRequest."""
    return f"{chart_id}_TS_Meta"


class PFTableWriter:
    """
    Schreibt ElmRes-Zeitreihen in PowerFactory IntReport-Tabellen.

    Folgt exakt der Struktur des Referenzskripts, generalisiert
    für beliebige Kombinationen aus Elementklasse + Ergebnisvariable.
    """

    def __init__(self, app: Any, config: FreischaltungConfig) -> None:
        self._app = app
        self._cfg = config

    # ── Öffentliche API ───────────────────────────────────────────────────

    def run_qds(self):
        """
        Führt die QDS-Berechnung (ComStatsim) aus und gibt das geladene
        ElmRes-Objekt zurück.  Wirft ReaderError wenn kein ElmRes gefunden.
        """
        app = self._app
        try:
            qds = app.GetFromStudyCase("ComStatsim")
            if qds:
                log.info("QDS-Berechnung (ComStatsim) wird ausgeführt …")
                app.EchoOff()
                qds.Execute()
                app.EchoOn()
                log.info("QDS-Berechnung abgeschlossen.")
        except Exception as exc:
            app.EchoOn()
            log.warning("ComStatsim nicht gefunden oder fehlgeschlagen: %s", exc)

        return self._load_elmres()

    def write_all(
        self,
        report: Any,
        elmres: Any,
        clear_existing: bool = True,
    ) -> TimeSeriesData:
        """
        Schreibt alle konfigurierten VizRequests in IntReport-Tabellen.

        Parameters
        ----------
        report:         IntReport-Objekt (aus script.GetParent())
        elmres:         Geladenes ElmRes-Objekt
        clear_existing: Wenn True, wird report.Reset() aufgerufen (löscht alle
                        bestehenden Tabellen im IntReport)

        Returns
        -------
        TimeSeriesData  – Direkt nutzbar für den HTML-Generator (kein Re-Read nötig)
        """
        if clear_existing:
            report.Reset()
            log.info("IntReport zurückgesetzt (alle Tabellen gelöscht).")

        nrows: int = elmres.GetNumberOfRows()
        ncols: int = elmres.GetNumberOfColumns()
        time_col = self._find_time_col(elmres)

        log.info("ElmRes: %d Zeitschritte, %d Spalten", nrows, ncols)

        # Zeitvektor aufbauen
        time_values = self._read_time_vector(elmres, nrows, time_col)

        # Alle Spalten nach VizRequest indizieren
        col_index = self._index_columns(elmres, ncols)

        # Pro VizRequest: Tabellen schreiben
        all_sections: dict[str, dict[str, TimeSeries]] = {}

        for vr in self._cfg.visualizations:
            key = (vr.element_class, vr.variable)
            cols = col_index.get(key, [])[:vr.max_elements]

            if not cols:
                log.debug(
                    "Keine Spalten für %s / %s – übersprungen.", vr.element_class, vr.variable
                )
                continue

            section = self._write_viz_request(report, elmres, vr, cols, time_values, nrows)
            all_sections[vr.chart_id] = section
            log.info(
                "Tabelle geschrieben: %s (%d Elemente)",
                table_name(vr.chart_id),
                len(section),
            )

        return TimeSeriesData(time=time_values, sections=all_sections)

    # ── Pro VizRequest ────────────────────────────────────────────────────

    def _write_viz_request(
        self,
        report: Any,
        elmres: Any,
        vr: VizRequest,
        columns: list[tuple[str, int, Any]],  # (col_name, col_idx, obj)
        time_values: list[float],
        nrows: int,
    ) -> dict[str, TimeSeries]:
        """Schreibt Haupt- + Metatabelle für eine VizRequest-Konfiguration."""
        cid      = vr.chart_id
        tbl_main = table_name(cid)
        tbl_meta = meta_table_name(cid)

        # ── Haupttabelle erstellen ─────────────────────────────────────
        report.CreateTable(tbl_main)
        report.CreateField(tbl_main, "time",        _DOUBLE)
        report.CreateField(tbl_main, "time_string", _STRING)
        for col_name, _, _ in columns:
            report.CreateField(tbl_main, col_name, _DOUBLE)

        # ── Metatabelle erstellen ─────────────────────────────────────
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

        # ── Haupttabelle befüllen ─────────────────────────────────────
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

        # ── Metatabelle befüllen (Zeile 0) ────────────────────────────
        for col_name, _, _ in columns:
            m = meta_records[col_name]
            report.SetValue(tbl_meta, col_name + _SUFFIX_DESC,       0, m["desc"])
            report.SetValue(tbl_meta, col_name + _SUFFIX_SHORT_DESC, 0, m["short_desc"])
            report.SetValue(tbl_meta, col_name + _SUFFIX_UNIT,       0, m["unit"])

        # ── TimeSeriesData-Abschnitt zurückgeben ──────────────────────
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

    # ── ElmRes-Zugriff ────────────────────────────────────────────────────

    def _load_elmres(self):
        sc = self._app.GetActiveStudyCase()
        if not sc:
            raise ReaderError("Kein aktiver Studienfall gefunden.")
        res_name = self._cfg.report.quasi_dynamic_result_file
        res_list = sc.GetContents(res_name) or sc.GetContents("*.ElmRes")
        if not res_list:
            raise ReaderError(
                "Kein ElmRes-Objekt gefunden – Simulation zuerst ausführen."
            )
        elmres = res_list[0]
        elmres.Load()
        log.info("ElmRes geladen: %s", getattr(elmres, "loc_name", "?"))
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
        Gibt ein Dict zurück: (element_class, variable) → [(col_name, col_idx, obj), …].
        Namen werden bereinigt und eindeutig gemacht.
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

            # Eindeutigen Namen erzeugen
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
