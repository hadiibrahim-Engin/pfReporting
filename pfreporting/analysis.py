"""Threshold analysis – assigns a status to all results."""
from __future__ import annotations

from pfreporting.config import PFReportConfig, VizRequest
from pfreporting.models import (
    LoadingResult,
    N1Result,
    OverallStatus,
    Status,
    StatusCounts,
    TimeSeries,
    TimeSeriesData,
    VoltageResult,
)


class AnalysisEngine:
    def __init__(self, config: PFReportConfig) -> None:
        self.cfg = config

    # ── Voltage band ──────────────────────────────────────────────────────

    def analyze_voltages(self, results: list[VoltageResult]) -> list[VoltageResult]:
        v = self.cfg.voltage
        for r in results:
            u = r.u_pu
            if u <= v.lower_violation or u >= v.upper_violation:
                r.status = "violation"
            elif u <= v.lower_warning or u >= v.upper_warning:
                r.status = "warning"
            else:
                r.status = "ok"
        return results

    # ── Thermal loading ───────────────────────────────────────────────────

    def analyze_thermal(self, results: list[LoadingResult]) -> list[LoadingResult]:
        t = self.cfg.thermal
        for r in results:
            if r.loading_pct >= t.violation_pct:
                r.status = "violation"
            elif r.loading_pct >= t.warning_pct:
                r.status = "warning"
            else:
                r.status = "ok"
        return results

    # ── N-1 security ──────────────────────────────────────────────────────

    def analyze_n1(self, results: list[N1Result]) -> list[N1Result]:
        for r in results:
            if not r.converged or r.violations:
                r.status = "violation"
            else:
                r.status = "ok"
        return results

    # ── Overall status ────────────────────────────────────────────────────

    def get_overall_status(
        self,
        voltage: list[VoltageResult],
        loading: list[LoadingResult],
        n1: list[N1Result],
    ) -> OverallStatus:
        def counts(items) -> StatusCounts:
            return StatusCounts(
                ok=sum(1 for x in items if x.status == "ok"),
                warning=sum(1 for x in items if x.status == "warning"),
                violation=sum(1 for x in items if x.status == "violation"),
            )

        vc = counts(voltage)
        tc = counts(loading)
        nc = counts(n1)

        total_viol = vc.violation + tc.violation + nc.violation
        total_warn = vc.warning + tc.warning

        if total_viol > 0:
            overall: Status = "violation"
        elif total_warn > 0:
            overall = "warning"
        else:
            overall = "ok"

        status = OverallStatus(
            status=overall,
            total_nodes=len(voltage),
            total_elements=len(loading),
            total_n1=len(n1),
            total_violations=total_viol,
            voltage_violations=vc.violation,
            voltage_warnings=vc.warning,
            thermal_violations=tc.violation,
            thermal_warnings=tc.warning,
            n1_violations=nc.violation,
            counts={
                "voltage": vc,
                "thermal": tc,
                "n1": nc,
            },
        )
        status.summary_text = self.build_summary_text(status)
        return status

    # ── Summary ───────────────────────────────────────────────────────────

    def build_summary_text(self, status: OverallStatus) -> str:
        if status.status == "ok":
            return (
                "De-energization is <strong>permissible</strong>. "
                "No system security violations detected."
            )
        parts: list[str] = []
        if status.voltage_violations:
            parts.append(f" - {status.voltage_violations} voltage band violation(s)")
        if status.thermal_violations:
            parts.append(f" - {status.thermal_violations} thermal overload(s)")
        if status.n1_violations:
            parts.append(f" - {status.n1_violations} (N-1) security violation(s)")
        base = (
            "De-energization is <strong>NOT permissible</strong>. "
            "System security violations are present."
        )
        return base + "<br>" + "<br>".join(parts)

    # ── Filter time series ────────────────────────────────────────────────

    def filter_critical_series(
        self,
        ts_raw: TimeSeriesData,
        viz_requests: list[VizRequest],
    ) -> TimeSeriesData:
        """Keep only time series that exceed a warning threshold at least once."""
        viz_by_id = {vr.chart_id: vr for vr in viz_requests}
        filtered_sections: dict[str, dict[str, TimeSeries]] = {}

        for chart_id, series_map in ts_raw.sections.items():
            vr = viz_by_id.get(chart_id)
            critical: dict[str, TimeSeries] = {}
            for name, ts in series_map.items():
                if vr is None or self._is_critical(ts.values, vr):
                    critical[name] = ts
            if critical:
                filtered_sections[chart_id] = critical

        return TimeSeriesData(time=ts_raw.time, sections=filtered_sections)

    def _is_critical(self, values: list[float | None], vr: VizRequest) -> bool:
        for v in values:
            if v is None:
                continue
            if vr.warn_hi is not None and v >= vr.warn_hi:
                return True
            if vr.warn_lo is not None and v <= vr.warn_lo:
                return True
        return False
