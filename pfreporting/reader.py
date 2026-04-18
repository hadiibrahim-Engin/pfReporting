"""PowerFactory data extraction.

All public methods return pure Pydantic models -
no PowerFactory object leaves this file.
"""
from __future__ import annotations

import datetime
import getpass
import logging
import math
from typing import Any

from pfreporting.config import PFReportConfig, VizRequest
from pfreporting.exceptions import ReaderError
from pfreporting.logger import get_logger
from pfreporting.models import (
    LoadFlowResult,
    LoadingResult,
    N1Result,
    ProjectInfo,
    QDSInfo,
    SwitchedElement,
    TimeSeries,
    TimeSeriesData,
    VoltageResult,
)
from pfreporting.utils import resolve_qds_datetime_hours, sanitize_name

log = get_logger()


class PowerFactoryReader:
    """Encapsulates all access to the PowerFactory Python API."""

    def __init__(self, app: Any, config: PFReportConfig) -> None:
        """Bind PowerFactory API handles used by the reader.

        Args:
            app: PowerFactory application object.
            config: Runtime report configuration.
        """
        self._app = app
        self._cfg = config

    # -- Project metadata --------------------------------------------------

    def get_project_info(self) -> ProjectInfo:
        """Collect project metadata and execution context values.

        Returns:
            ``ProjectInfo`` with active project name, study case name, timestamp,
            and author/company values.
        """
        app = self._app
        project = app.GetActiveProject()
        sc = app.GetActiveStudyCase()
        now = datetime.datetime.now()
        return ProjectInfo(
            project=self._loc_name(project, "Unknown"),
            study_case=self._loc_name(sc, "Unknown"),
            date=now.strftime("%d.%m.%Y"),
            time=now.strftime("%H:%M"),
            datetime_full=now.strftime("%d.%m.%Y %H:%M:%S"),
            company=self._cfg.report.company,
            author=self._safe_getuser(),
        )

    # -- QDS simulation settings -------------------------------------------

    def get_qds_info(self) -> QDSInfo:
        """Read ComStatsim settings for the QDS info block.

        Config overrides (config.qds.t_start/t_end/dt) take precedence over
        the values stored inside PowerFactory when they are set.

        Returns:
            ``QDSInfo`` populated from PF and config overrides; defaults are
            returned if the command object is unavailable.
        """
        qds_cfg = self._cfg.qds
        try:
            qds = self._app.GetFromStudyCase("ComStatsim")
            if qds is None:
                return QDSInfo()
            pf_t_start = float(getattr(qds, "Tstart", 0) or 0)
            pf_t_end   = float(getattr(qds, "Tshow",  24) or 24)
            pf_dt      = float(getattr(qds, "dt",      1) or 1)

            t_start = qds_cfg.t_start if qds_cfg.t_start is not None else pf_t_start
            t_end   = qds_cfg.t_end   if qds_cfg.t_end   is not None else pf_t_end

            sc = self._app.GetActiveStudyCase()
            study_time_start_raw = getattr(sc, "iStudyTime", None) if sc else None
            dt_start_h, dt_end_h, dt_notes = resolve_qds_datetime_hours(
                qds_cfg.start_datetime,
                qds_cfg.end_datetime,
                study_time_start_raw,
            )
            for note in dt_notes:
                log.warning("QDS datetime override: %s", note)
            if dt_start_h is not None:
                t_start = dt_start_h
            if dt_end_h is not None:
                t_end = dt_end_h

            dt      = qds_cfg.dt      if qds_cfg.dt      is not None else pf_dt
            n_steps = max(0, round((t_end - t_start) / dt)) if dt > 0 else 0

            scenario = ""
            try:
                scen = self._app.GetActiveScenario()
                scenario = self._loc_name(scen, "")
            except Exception:
                pass

            study_time_start = ""
            try:
                sc = self._app.GetActiveStudyCase()
                st = getattr(sc, "iStudyTime", None)
                if st:
                    study_time_start = str(st)
            except Exception:
                pass

            return QDSInfo(
                t_start_h=t_start,
                t_end_h=t_end,
                dt_h=dt,
                n_steps=n_steps,
                result_file=self._cfg.report.quasi_dynamic_result_file,
                scenario=scenario,
                study_time_start=study_time_start,
            )
        except Exception as exc:
            log.warning("QDS settings not readable: %s", exc)
            return QDSInfo()

    # -- De-energized equipment --------------------------------------------

    def get_switched_elements(self) -> list[SwitchedElement]:
        """List de-energized network elements.

        Returns:
            All line and transformer objects currently flagged with
            ``outserv == 1``.
        """
        results: list[SwitchedElement] = []
        type_map = {
            "ElmLne": "Line",
            "ElmTr2": "Transformer (2W)",
            "ElmTr3": "Transformer (3W)",
        }
        for cls, label in type_map.items():
            for elem in self._calc_objects(f"*.{cls}"):
                if getattr(elem, "outserv", 0) == 1:
                    results.append(
                        SwitchedElement(
                            name=self._loc_name(elem),
                            type=label,
                        )
                    )
        log.info("De-energized equipment: %d", len(results))
        return results

    # -- Load flow results -------------------------------------------------

    def get_loadflow_results(self) -> LoadFlowResult:
        """Execute load flow and aggregate system-level metrics.

        Returns:
            ``LoadFlowResult`` with convergence state, active/reactive balances,
            losses, and power factor estimates.
        """
        app = self._app
        try:
            ldf = app.GetFromStudyCase("ComLdf")
            app.EchoOff()
            ldf.Execute()
            app.EchoOn()
        except Exception as exc:
            log.warning("Load flow calculation failed: %s", exc)

        converged = True
        iterations = 0
        try:
            ldf = app.GetFromStudyCase("ComLdf")
            converged = getattr(ldf, "iopt_notconv", 0) == 0
            iterations = int(getattr(ldf, "nrItNum", 0) or 0)
        except Exception:
            pass

        # Active power sums
        total_load = sum(
            getattr(e, "m:P:bus1", 0) or 0 for e in self._calc_objects("*.ElmLod")
        )
        total_gen = sum(
            getattr(e, "m:P:bus1", 0) or 0
            for cls in ("*.ElmSym", "*.ElmGenstat", "*.ElmPvsys", "*.ElmWind")
            for e in self._calc_objects(cls)
        )
        losses = round(total_gen - total_load, 2)

        # Reactive power sums
        total_load_q = sum(
            getattr(e, "m:Q:bus1", 0) or 0 for e in self._calc_objects("*.ElmLod")
        )
        total_gen_q = sum(
            getattr(e, "m:Q:bus1", 0) or 0
            for cls in ("*.ElmSym", "*.ElmGenstat", "*.ElmPvsys", "*.ElmWind")
            for e in self._calc_objects(cls)
        )
        losses_q = round(total_gen_q - total_load_q, 2)

        # Power factors
        s_load = math.sqrt(total_load ** 2 + total_load_q ** 2)
        s_gen  = math.sqrt(total_gen  ** 2 + total_gen_q  ** 2)
        load_pf = round(total_load / s_load, 3) if s_load > 0 else None
        gen_pf  = round(total_gen  / s_gen,  3) if s_gen  > 0 else None

        log.info(
            "Load flow: converged=%s  P_load=%.2f MW  Q_load=%.2f Mvar  "
            "P_gen=%.2f MW  Q_gen=%.2f Mvar  Losses=%.2f MW",
            converged,
            total_load, total_load_q,
            total_gen,  total_gen_q,
            losses,
        )
        return LoadFlowResult(
            converged=converged,
            status_text="Converged" if converged else "Not Converged",
            iterations=iterations,
            total_load_mw=round(total_load, 2),
            total_gen_mw=round(total_gen, 2),
            losses_mw=losses,
            total_load_mvar=round(total_load_q, 2),
            total_gen_mvar=round(total_gen_q, 2),
            losses_mvar=losses_q,
            load_power_factor=load_pf,
            gen_power_factor=gen_pf,
        )

    # -- Voltage results ---------------------------------------------------

    def get_voltage_results(self) -> list[VoltageResult]:
        """Read voltage values for all calc-relevant terminals.

        Returns:
            One ``VoltageResult`` per terminal with p.u., kV and deviation data.
        """
        results: list[VoltageResult] = []
        for bus in self._calc_objects("*.ElmTerm"):
            u_pu = getattr(bus, "m:u", None)
            if u_pu is None:
                continue
            u_nenn = float(getattr(bus, "uknom", 0) or 0)
            u_kv = round(u_pu * u_nenn, 2)
            dev = round((u_pu - 1.0) * 100, 2)
            results.append(
                VoltageResult(
                    node=self._loc_name(bus),
                    u_nenn_kv=round(u_nenn, 1),
                    u_kv=u_kv,
                    u_pu=round(u_pu, 4),
                    deviation_pct=dev,
                )
            )
        log.info("Voltage results: %d nodes", len(results))
        return results

    # -- Thermal loading ---------------------------------------------------

    def get_loading_results(self) -> list[LoadingResult]:
        """Read thermal loading values for line and transformer elements.

        Returns:
            Loading rows sorted by descending loading percentage.
        """
        results: list[LoadingResult] = []
        type_map = {
            "ElmLne": "Line",
            "ElmTr2": "Transformer (2W)",
            "ElmTr3": "Transformer (3W)",
        }
        for cls, label in type_map.items():
            for elem in self._calc_objects(f"*.{cls}"):
                loading = getattr(elem, "c:loading", None)
                if loading is None:
                    continue
                i_ka = float(getattr(elem, "m:i1:bus1", 0) or getattr(elem, "m:i1", 0) or 0)
                i_nenn = float(
                    getattr(elem, "Inom", 0)
                    or getattr(elem, "ratedCurrent", 0)
                    or 0
                )
                results.append(
                    LoadingResult(
                        name=self._loc_name(elem),
                        type=label,
                        loading_pct=round(float(loading), 1),
                        i_ka=round(i_ka, 3),
                        i_nenn_ka=round(i_nenn, 3),
                    )
                )
        results.sort(key=lambda r: r.loading_pct, reverse=True)
        log.info("Thermal loading: %d elements", len(results))
        return results

    # -- N-1 analysis ------------------------------------------------------

    def get_n1_results(self) -> list[N1Result]:
        """Run N-1 analysis using native PF support when possible.

        The reader first tries ``ComSimoutage`` for environments where PF
        provides a compatible result interface. If that path yields no parsed
        results, it falls back to a deterministic manual outage loop.

        Returns:
            Contingency result rows for all evaluated outage cases.
        """
        results = self._try_simoutage()
        if not results:
            results = self._manual_n1()
        log.info("N-1 analysis: %d cases", len(results))
        return results

    def _try_simoutage(self) -> list[N1Result]:
        """Attempt ``ComSimoutage`` execution for PF versions that support it.

        Returns:
            A parsed list of ``N1Result`` entries. The current implementation
            returns an empty list because output extraction is PF-version
            dependent and intentionally delegated to the manual fallback.
        """
        try:
            cmd = self._app.GetFromStudyCase("ComSimoutage")
            if cmd is None:
                return []
            self._app.EchoOff()
            cmd.Execute()
            self._app.EchoOn()
        except Exception:
            return []
        return []  # Result extraction depends heavily on PF version → fallback

    def _manual_n1(self) -> list[N1Result]:
        """Run a manual outage loop as a version-agnostic N-1 fallback.

        For each candidate branch element, the method switches the element out
        of service, runs load flow, captures post-contingency extrema, and then
        restores the element before proceeding.

        Returns:
            One ``N1Result`` per tested outage candidate.

        Raises:
            ReaderError: If no ``ComLdf`` command is available in the study case.
        """
        app = self._app
        ldf = app.GetFromStudyCase("ComLdf")
        if ldf is None:
            raise ReaderError("No ComLdf object found in study case")

        candidates = [
            (e, "Line") for e in self._calc_objects("*.ElmLne")
        ] + [
            (e, "Transformer (2W)") for e in self._calc_objects("*.ElmTr2")
        ]

        results: list[N1Result] = []
        for elem, etype in candidates:
            name = self._loc_name(elem)
            elem.outserv = 1
            try:
                app.EchoOff()
                ldf.Execute()
                app.EchoOn()
                converged = True
            except Exception:
                converged = False
                app.EchoOn()

            entry = N1Result(
                outage_element=name,
                type=etype,
                converged=converged,
                max_loading_pct=0.0,
                max_loading_element="-",
                min_voltage_pu=0.0,
                min_voltage_node="-",
                max_voltage_pu=0.0,
                max_voltage_node="-",
            )

            if converged:
                self._fill_n1_postcontingency(entry)

            elem.outserv = 0
            results.append(entry)

        # Restore normal operation
        try:
            app.EchoOff()
            ldf.Execute()
            app.EchoOn()
        except Exception:
            pass

        return results

    def _fill_n1_postcontingency(self, entry: N1Result) -> None:
        """Fill one contingency entry using post-contingency PF states.

        Args:
            entry: Mutable N-1 entry to enrich with extrema and violations.

        The method computes the global maximum loading across lines and two-
        winding transformers, then evaluates minimum and maximum bus voltages.
        Violations are appended according to ``config.n1`` thresholds.
        """
        n1_cfg = self._cfg.n1
        max_load, max_load_elem = 0.0, "-"
        for cls in ("*.ElmLne", "*.ElmTr2"):
            for branch in self._calc_objects(cls):
                loading = float(getattr(branch, "c:loading", 0) or 0)
                if loading > max_load:
                    max_load = loading
                    max_load_elem = self._loc_name(branch)

        min_v, min_v_node = 1.0, "-"
        max_v, max_v_node = 0.0, "-"
        for bus in self._calc_objects("*.ElmTerm"):
            u = getattr(bus, "m:u", None)
            if u is None:
                continue
            bname = self._loc_name(bus)
            if u < min_v:
                min_v, min_v_node = u, bname
            if u > max_v:
                max_v, max_v_node = u, bname

        entry.max_loading_pct = round(max_load, 1)
        entry.max_loading_element = max_load_elem
        entry.min_voltage_pu = round(min_v, 4)
        entry.min_voltage_node = min_v_node
        entry.max_voltage_pu = round(max_v, 4)
        entry.max_voltage_node = max_v_node

        if max_load > n1_cfg.max_loading_pct:
            entry.violations.append(f"Overload: {max_load_elem} at {max_load:.1f}%")
        if min_v < n1_cfg.min_voltage_pu:
            entry.violations.append(
                f"Undervoltage: {min_v_node} at {min_v:.4f} p.u."
            )
        if max_v > n1_cfg.max_voltage_pu:
            entry.violations.append(
                f"Overvoltage: {max_v_node} at {max_v:.4f} p.u."
            )

    # -- Time series (quasi-dynamic) ---------------------------------------

    def load_elmres(self, name: str | None = None):
        """Load an ElmRes result object from the active study case.

        Args:
            name: Optional explicit ElmRes object name.

        Returns:
            The loaded ElmRes object.

        Raises:
            ReaderError: If no study case or result object is available.
        """
        sc = self._app.GetActiveStudyCase()
        if not sc:
            raise ReaderError("No active study case")
        res_name = name or self._cfg.report.quasi_dynamic_result_file
        res_list = sc.GetContents(res_name) or sc.GetContents("*.ElmRes")
        if not res_list:
            raise ReaderError("No ElmRes object found. Run simulation first.")
        elmres = res_list[0]
        elmres.Load()
        log.info("ElmRes loaded: %s", self._loc_name(elmres))
        return elmres

    def get_time_series(
        self, elmres: Any, viz_requests: list[VizRequest]
    ) -> TimeSeriesData:
        """Extract configured time-series sections from an ElmRes object.

        Args:
            elmres: Loaded PowerFactory result object.
            viz_requests: Requested element-class/variable pairs that define
                output sections and per-section element caps.

        Returns:
            ``TimeSeriesData`` with ``time`` values and chart sections keyed by
            ``VizRequest.chart_id``.

        Notes:
            Series names are sanitized and made unique per chart section by
            appending ``_2``, ``_3``, ... when collisions occur.
        """
        nrows: int = elmres.GetNumberOfRows()
        ncols: int = elmres.GetNumberOfColumns()
        time_col = self._find_time_col(elmres)

        time_vals = [self._get_val(elmres, r, time_col) or float(r) for r in range(nrows)]

        # Index: (element_class, variable) → VizRequest
        req_index: dict[tuple[str, str], VizRequest] = {
            (vr.element_class, vr.variable): vr for vr in viz_requests
        }
        # Counter per chart_id
        count_per_chart: dict[str, int] = {vr.chart_id: 0 for vr in viz_requests}
        sections: dict[str, dict[str, TimeSeries]] = {}
        seen_names: dict[str, set[str]] = {}

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
            if key not in req_index:
                continue
            vr = req_index[key]
            chart_id = vr.chart_id

            if count_per_chart.get(chart_id, 0) >= vr.max_elements:
                continue

            base_name = sanitize_name(self._loc_name(obj))
            if chart_id not in seen_names:
                seen_names[chart_id] = set()
            unique_name = base_name
            k = 2
            while unique_name in seen_names[chart_id]:
                unique_name = f"{base_name}_{k}"
                k += 1
            seen_names[chart_id].add(unique_name)

            values = [self._get_val(elmres, r, col) for r in range(nrows)]
            try:
                unit = elmres.GetUnit(col)
            except Exception:
                unit = vr.unit

            ts = TimeSeries(
                element_class=cls_name,
                variable=var,
                label=vr.label,
                unit=unit or vr.unit,
                values=values,
            )
            if chart_id not in sections:
                sections[chart_id] = {}
            sections[chart_id][unique_name] = ts
            count_per_chart[chart_id] = count_per_chart.get(chart_id, 0) + 1

        total_series = sum(len(s) for s in sections.values())
        log.info(
            "Time series extracted: %d sections, %d series, %d time steps",
            len(sections),
            total_series,
            nrows,
        )
        return TimeSeriesData(time=time_vals, sections=sections)

    # -- Helper methods ----------------------------------------------------

    def _calc_objects(self, pattern: str) -> list[Any]:
        """Return calc-relevant PF objects for one wildcard pattern.

        Args:
            pattern: PowerFactory wildcard pattern like ``*.ElmTerm``.

        Returns:
            Matching objects, or an empty list on API failures.

        Example patterns include ``*.ElmTerm`` and ``*.ElmLne``.
        Any API error is converted into an empty list to keep workflows robust.
        """
        try:
            return self._app.GetCalcRelevantObjects(pattern) or []
        except Exception:
            return []

    @staticmethod
    def _loc_name(obj: Any, fallback: str = "?") -> str:
        """Return ``loc_name`` from a PF object with a fallback value.

        Args:
            obj: PF object that may carry a ``loc_name`` attribute.
            fallback: Value used when no name can be resolved.

        Returns:
            Object display name or ``fallback``.
        """
        if obj is None:
            return fallback
        return getattr(obj, "loc_name", None) or fallback

    @staticmethod
    def _safe_getuser() -> str:
        """Return current OS username.

        Returns:
            Username string, or ``"Unknown"`` if lookup fails.
        """
        try:
            return getpass.getuser()
        except Exception:
            return "Unknown"

    @staticmethod
    def _find_time_col(elmres: Any) -> int:
        """Locate time column index in an ElmRes object.

        Args:
            elmres: Loaded ElmRes object.

        Returns:
            Time column index, or ``0`` if none of the known aliases exists.
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
        """Read one scalar value from an ElmRes cell.

        Args:
            elmres: Loaded ElmRes object.
            row: Row index.
            col: Column index.

        Returns:
            Float value or ``None`` when PF reports NaN/missing/error.
        """
        try:
            _, val = elmres.GetValue(row, col)
            if val is not None and self._app.IsNAN(val):
                return None
            return float(val) if val is not None else None
        except Exception:
            return None
