"""PowerFactory data extraction.

All public methods return pure Pydantic models —
no PowerFactory object leaves this file.
"""
from __future__ import annotations

import datetime
import getpass
import math
from typing import Any

from pfreporting import pf_attrs as pfa
from pfreporting.config import PFReportConfig, VizRequest
from pfreporting.elmres import ElmResHelper
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
        self._app = app
        self._cfg = config

    # -- Project metadata --------------------------------------------------

    def get_project_info(self) -> ProjectInfo:
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
        qds_cfg = self._cfg.qds
        try:
            qds = self._app.GetFromStudyCase("ComStatsim")
            if qds is None:
                return QDSInfo()

            pf_t_start = float(getattr(qds, pfa.QDS_T_START, 0) or 0)
            pf_t_end   = float(getattr(qds, pfa.QDS_T_END,   24) or 24)
            pf_dt      = float(getattr(qds, pfa.QDS_DT,       1) or 1)

            t_start = qds_cfg.t_start if qds_cfg.t_start is not None else pf_t_start
            t_end   = qds_cfg.t_end   if qds_cfg.t_end   is not None else pf_t_end

            sc = self._app.GetActiveStudyCase()
            study_time_start_raw = getattr(sc, pfa.STUDY_TIME, None) if sc else None
            dt_start_h, dt_end_h, dt_notes = resolve_qds_datetime_hours(
                qds_cfg.start_datetime, qds_cfg.end_datetime, study_time_start_raw,
            )
            for note in dt_notes:
                log.warning("QDS datetime override: %s", note)
            if dt_start_h is not None:
                t_start = dt_start_h
            if dt_end_h is not None:
                t_end = dt_end_h

            dt      = qds_cfg.dt if qds_cfg.dt is not None else pf_dt
            n_steps = max(0, round((t_end - t_start) / dt)) if dt > 0 else 0

            scenario = ""
            try:
                scen = self._app.GetActiveScenario()
                scenario = self._loc_name(scen, "")
            except Exception:
                pass

            study_time_start = ""
            try:
                sc2 = self._app.GetActiveStudyCase()
                st = getattr(sc2, pfa.STUDY_TIME, None)
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
        results: list[SwitchedElement] = []
        type_map = {
            "ElmLne": "Line",
            "ElmTr2": "Transformer (2W)",
            "ElmTr3": "Transformer (3W)",
        }
        for cls, label in type_map.items():
            for elem in self._calc_objects(f"*.{cls}"):
                if getattr(elem, pfa.OUT_OF_SERVICE, 0) == 1:
                    results.append(SwitchedElement(name=self._loc_name(elem), type=label))
        log.info("De-energized equipment: %d", len(results))
        return results

    # -- Load flow results -------------------------------------------------

    def get_loadflow_results(self) -> LoadFlowResult:
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
            converged  = getattr(ldf, pfa.LDF_NOT_CONV, 0) == 0
            iterations = int(getattr(ldf, pfa.LDF_ITER_CNT, 0) or 0)
        except Exception:
            pass

        # Fetch each element class once; reuse for both P and Q sums.
        loads = self._calc_objects("*.ElmLod")
        gen_classes = ["*.ElmSym", "*.ElmGenstat", "*.ElmPvsys", "*.ElmWind"]
        gens = [e for cls in gen_classes for e in self._calc_objects(cls)]

        total_load   = sum(getattr(e, pfa.P_BUS1_MW,   0) or 0 for e in loads)
        total_gen    = sum(getattr(e, pfa.P_BUS1_MW,   0) or 0 for e in gens)
        total_load_q = sum(getattr(e, pfa.Q_BUS1_MVAR, 0) or 0 for e in loads)
        total_gen_q  = sum(getattr(e, pfa.Q_BUS1_MVAR, 0) or 0 for e in gens)

        losses   = round(total_gen   - total_load,   2)
        losses_q = round(total_gen_q - total_load_q, 2)

        s_load = math.sqrt(total_load ** 2 + total_load_q ** 2)
        s_gen  = math.sqrt(total_gen  ** 2 + total_gen_q  ** 2)
        load_pf = round(total_load / s_load, 3) if s_load > 0 else None
        gen_pf  = round(total_gen  / s_gen,  3) if s_gen  > 0 else None

        log.info(
            "Load flow: converged=%s  P_load=%.2f MW  P_gen=%.2f MW  Losses=%.2f MW",
            converged, total_load, total_gen, losses,
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
        results: list[VoltageResult] = []
        for bus in self._calc_objects("*.ElmTerm"):
            u_pu = getattr(bus, pfa.U_PU, None)
            if u_pu is None:
                continue
            u_nenn = float(getattr(bus, pfa.NOM_VOLTAGE_KV, 0) or 0)
            u_kv = round(u_pu * u_nenn, 2)
            dev  = round((u_pu - 1.0) * 100, 2)
            results.append(VoltageResult(
                node=self._loc_name(bus),
                u_nenn_kv=round(u_nenn, 1),
                u_kv=u_kv,
                u_pu=round(u_pu, 4),
                deviation_pct=dev,
            ))
        log.info("Voltage results: %d nodes", len(results))
        return results

    # -- Thermal loading ---------------------------------------------------

    def get_loading_results(self) -> list[LoadingResult]:
        results: list[LoadingResult] = []
        type_map = {
            "ElmLne": "Line",
            "ElmTr2": "Transformer (2W)",
            "ElmTr3": "Transformer (3W)",
        }
        for cls, label in type_map.items():
            for elem in self._calc_objects(f"*.{cls}"):
                loading = getattr(elem, pfa.LOADING_PCT, None)
                if loading is None:
                    continue
                i_ka   = float(getattr(elem, pfa.I_BUS1_KA, 0) or getattr(elem, pfa.I_KA, 0) or 0)
                i_nenn = float(getattr(elem, pfa.I_NOM_KA, 0) or getattr(elem, pfa.I_NOM_ALT_KA, 0) or 0)
                results.append(LoadingResult(
                    name=self._loc_name(elem),
                    type=label,
                    loading_pct=round(float(loading), 1),
                    i_ka=round(i_ka, 3),
                    i_nenn_ka=round(i_nenn, 3),
                ))
        results.sort(key=lambda r: r.loading_pct, reverse=True)
        log.info("Thermal loading: %d elements", len(results))
        return results

    # -- N-1 analysis ------------------------------------------------------

    def get_n1_results(self) -> list[N1Result]:
        results = self._try_simoutage()
        if not results:
            results = self._manual_n1()
        log.info("N-1 analysis: %d cases", len(results))
        return results

    def _try_simoutage(self) -> list[N1Result]:
        try:
            cmd = self._app.GetFromStudyCase("ComSimoutage")
            if cmd is None:
                return []
            self._app.EchoOff()
            cmd.Execute()
            self._app.EchoOn()
        except Exception:
            return []
        return []  # Result extraction is PF-version dependent → fallback

    def _manual_n1(self) -> list[N1Result]:
        app = self._app
        ldf = app.GetFromStudyCase("ComLdf")
        if ldf is None:
            raise ReaderError("No ComLdf object found in study case")

        # Fetch element lists once; reuse across all outage iterations.
        lines  = self._calc_objects("*.ElmLne")
        tr2s   = self._calc_objects("*.ElmTr2")
        buses  = self._calc_objects("*.ElmTerm")
        branches = lines + tr2s
        candidates = [(e, "Line") for e in lines] + [(e, "Transformer (2W)") for e in tr2s]

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
                outage_element=name, type=etype, converged=converged,
                max_loading_pct=0.0, max_loading_element="-",
                min_voltage_pu=0.0, min_voltage_node="-",
                max_voltage_pu=0.0, max_voltage_node="-",
            )
            if converged:
                self._fill_n1_postcontingency(entry, branches, buses)

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

    def _fill_n1_postcontingency(
        self,
        entry: N1Result,
        branches: list[Any],
        buses: list[Any],
    ) -> None:
        n1_cfg = self._cfg.n1
        max_load, max_load_elem = 0.0, "-"
        for branch in branches:
            loading = float(getattr(branch, pfa.LOADING_PCT, 0) or 0)
            if loading > max_load:
                max_load     = loading
                max_load_elem = self._loc_name(branch)

        min_v, min_v_node = 1.0, "-"
        max_v, max_v_node = 0.0, "-"
        for bus in buses:
            u = getattr(bus, pfa.U_PU, None)
            if u is None:
                continue
            bname = self._loc_name(bus)
            if u < min_v:
                min_v, min_v_node = u, bname
            if u > max_v:
                max_v, max_v_node = u, bname

        entry.max_loading_pct     = round(max_load, 1)
        entry.max_loading_element = max_load_elem
        entry.min_voltage_pu      = round(min_v, 4)
        entry.min_voltage_node    = min_v_node
        entry.max_voltage_pu      = round(max_v, 4)
        entry.max_voltage_node    = max_v_node

        if max_load > n1_cfg.max_loading_pct:
            entry.violations.append(f"Overload: {max_load_elem} at {max_load:.1f}%")
        if min_v < n1_cfg.min_voltage_pu:
            entry.violations.append(f"Undervoltage: {min_v_node} at {min_v:.4f} p.u.")
        if max_v > n1_cfg.max_voltage_pu:
            entry.violations.append(f"Overvoltage: {max_v_node} at {max_v:.4f} p.u.")

    # -- Time series (quasi-dynamic) ---------------------------------------

    def load_elmres(self, name: str | None = None) -> Any:
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

        Uses ElmResHelper.get_column() which attempts a single-call batch read
        (PF 2020+) before falling back to row-by-row GetValue.
        """
        helper = ElmResHelper(self._app, elmres)

        time_col  = helper.find_time_col()
        time_vals = helper.get_column(time_col)
        # Fall back to row indices for any None time values
        time_vals = [
            v if v is not None else float(i)
            for i, v in enumerate(time_vals)
        ]

        req_index: dict[tuple[str, str], VizRequest] = {
            (vr.element_class, vr.variable): vr for vr in viz_requests
        }
        count_per_chart: dict[str, int] = {vr.chart_id: 0 for vr in viz_requests}
        sections: dict[str, dict[str, TimeSeries]] = {}
        seen_names: dict[str, set[str]] = {}

        for col in range(helper.ncols):
            obj = helper.get_object(col)
            if obj is None:
                continue
            try:
                cls_name = obj.GetClassName()
            except Exception:
                continue
            var = helper.get_variable(col)

            key = (cls_name, var)
            if key not in req_index:
                continue
            vr = req_index[key]
            chart_id = vr.chart_id

            if count_per_chart.get(chart_id, 0) >= vr.max_elements:
                continue

            base_name   = sanitize_name(self._loc_name(obj))
            seen_names.setdefault(chart_id, set())
            unique_name = base_name
            k = 2
            while unique_name in seen_names[chart_id]:
                unique_name = f"{base_name}_{k}"
                k += 1
            seen_names[chart_id].add(unique_name)

            values = helper.get_column(col)
            unit   = helper.get_unit(col) or vr.unit

            sections.setdefault(chart_id, {})[unique_name] = TimeSeries(
                element_class=cls_name,
                variable=var,
                label=vr.label,
                unit=unit,
                values=values,
            )
            count_per_chart[chart_id] = count_per_chart.get(chart_id, 0) + 1

        total_series = sum(len(s) for s in sections.values())
        log.info(
            "Time series extracted: %d sections, %d series, %d time steps",
            len(sections), total_series, len(time_vals),
        )
        return TimeSeriesData(time=time_vals, sections=sections)

    # -- Helpers -----------------------------------------------------------

    def _calc_objects(self, pattern: str) -> list[Any]:
        try:
            return self._app.GetCalcRelevantObjects(pattern) or []
        except Exception:
            return []

    @staticmethod
    def _loc_name(obj: Any, fallback: str = "?") -> str:
        if obj is None:
            return fallback
        return getattr(obj, "loc_name", None) or fallback

    @staticmethod
    def _safe_getuser() -> str:
        try:
            return getpass.getuser()
        except Exception:
            return "Unknown"
