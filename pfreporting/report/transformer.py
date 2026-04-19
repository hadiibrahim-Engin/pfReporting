"""ReportDataTransformer — shapes ReportData into template-ready payloads.

Extracted from HTMLReportGenerator so the same logic can be reused by the
standalone renderers without importing the full generator.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from pfreporting.config import PFReportConfig, VizRequest
from pfreporting.report.builder import ReportData

if TYPE_CHECKING:
    pass


class ReportDataTransformer:
    """Converts a ReportData into dicts/lists consumed by Jinja2 templates."""

    def __init__(self, config: PFReportConfig) -> None:
        self.config = config

    # -- Chart data (time-series line charts) ------------------------------

    def build_chart_data(self, data: ReportData) -> list[dict]:
        """Build the ``window.__chartData`` payload for Chart.js."""
        if data.ts_data.is_empty():
            return []

        time_labels = [float(t) if isinstance(t, float) else t for t in data.ts_data.time]
        sample_idx  = self._downsample_indices(time_labels, self.config.report.max_points)
        if sample_idx is not None:
            time_labels = [time_labels[i] for i in sample_idx]

        result: list[dict] = []
        for vr in self.config.visualizations:
            section = data.ts_data.sections.get(vr.chart_id)
            if not section:
                continue

            series_list = []
            for name, ts in section.items():
                values = [float(v) if v is not None else None for v in ts.values]
                if sample_idx is not None:
                    values = [values[i] if i < len(values) else None for i in sample_idx]
                series_list.append({"name": name, "values": values})

            result.append({
                "id":              f"chart-{vr.chart_id}",
                "label":           vr.label,
                "unit":            vr.unit,
                "variable":        vr.variable,
                "value_precision": 8 if vr.variable == "c:loading" else 4,
                "warn_hi":         vr.warn_hi,
                "violation_hi":    vr.violation_hi,
                "warn_lo":         vr.warn_lo,
                "violation_lo":    vr.violation_lo,
                "time":            time_labels,
                "series":          series_list,
            })

        return result

    # -- Heatmap data ------------------------------------------------------

    def build_heatmap_data(self, data: ReportData) -> dict[str, dict]:
        """Build generic heatmap payloads keyed by chart_id."""
        result: dict[str, dict] = {}
        src = data.ts_raw if not data.ts_raw.is_empty() else data.ts_data
        if src.is_empty():
            return result

        for vr in self.config.visualizations:
            if not vr.heatmap:
                continue
            section = src.sections.get(vr.chart_id)
            if not section:
                continue
            rows = [
                {
                    "name": name,
                    "values": [float(v) if v is not None else None for v in ts.values],
                }
                for name, ts in section.items()
                if not vr.heatmap_elements or name in vr.heatmap_elements
            ]
            result[vr.chart_id] = {
                "time": [float(t) if isinstance(t, float) else t for t in src.time],
                "rows": rows,
                "unit": vr.unit,
            }

        return result

    def build_thermal_hm_data(self, data: ReportData) -> dict | None:
        """Build thermal loading heatmap payload for section-level rendering."""
        src = data.ts_raw if not data.ts_raw.is_empty() else data.ts_data
        if src.is_empty():
            return None

        hm_vr     = self._get_loading_hm_vr()
        whitelist  = hm_vr.heatmap_elements if hm_vr else None
        status_map = {r.name: r.status for r in data.loading}
        time       = [float(t) for t in src.time]
        seen: set[str] = set()
        rows: list[dict] = []

        for section in src.sections.values():
            for name, ts in section.items():
                if ts.variable != "c:loading" or name in seen:
                    continue
                if whitelist and name not in whitelist:
                    continue
                seen.add(name)
                rows.append({
                    "name":   name,
                    "values": [float(v) if v is not None else None for v in ts.values],
                    "status": status_map.get(name, "ok"),
                })

        if not rows:
            return None
        return {
            "time":         time,
            "rows":         rows,
            "unit":         "%",
            "warn_hi":      self.config.thermal.warning_pct,
            "violation_hi": self.config.thermal.violation_pct,
        }

    def build_voltage_hm_data(self, data: ReportData) -> dict | None:
        """Build bus-voltage heatmap payload for section-level rendering."""
        src = data.ts_raw if not data.ts_raw.is_empty() else data.ts_data
        if src.is_empty():
            return None

        hm_vr     = self._get_voltage_hm_vr()
        whitelist  = hm_vr.heatmap_elements if hm_vr else None
        status_map = {r.node: r.status for r in data.voltage}
        time       = [float(t) for t in src.time]
        seen: set[str] = set()
        rows: list[dict] = []

        for section in src.sections.values():
            for name, ts in section.items():
                if ts.element_class != "ElmTerm" or name in seen:
                    continue
                if whitelist and name not in whitelist:
                    continue
                seen.add(name)
                rows.append({
                    "name":   name,
                    "values": [float(v) if v is not None else None for v in ts.values],
                    "status": status_map.get(name, "ok"),
                })

        if not rows:
            return None
        return {
            "time":         time,
            "rows":         rows,
            "unit":         "p.u.",
            "warn_lo":      self.config.voltage.lower_warning,
            "violation_lo": self.config.voltage.lower_violation,
            "warn_hi":      self.config.voltage.upper_warning,
            "violation_hi": self.config.voltage.upper_violation,
        }

    # -- Traffic-light verdict ---------------------------------------------

    @staticmethod
    def build_ampel(data: ReportData) -> dict:
        """Compute traffic-light verdict and summary findings list."""
        volt_viol  = [r for r in data.voltage if r.status == "violation"]
        volt_warn  = [r for r in data.voltage if r.status == "warning"]
        therm_viol = [r for r in data.loading if r.status == "violation"]
        therm_warn = [r for r in data.loading if r.status == "warning"]
        n1_viol    = [r for r in data.n1      if r.status == "violation"]

        if volt_viol or therm_viol or n1_viol:
            color   = "red"
            verdict = "DE-ENERGIZATION NOT FEASIBLE"
        elif volt_warn or therm_warn:
            color   = "amber"
            verdict = "DE-ENERGIZATION FEASIBLE WITH RESERVATIONS"
        else:
            color   = "green"
            verdict = "DE-ENERGIZATION FEASIBLE"

        findings: list[str] = []
        if volt_viol:
            worst = min(volt_viol, key=lambda r: r.u_pu)
            findings.append(
                f"{len(volt_viol)} bus voltage violation(s) — worst: "
                f"{worst.node} ({worst.u_pu:.4f} p.u.)"
            )
        if therm_viol:
            worst_t = max(therm_viol, key=lambda r: r.loading_pct)
            findings.append(
                f"{len(therm_viol)} thermal overload(s) — worst: "
                f"{worst_t.name} ({worst_t.loading_pct:.1f}%)"
            )
        if n1_viol:
            findings.append(f"{len(n1_viol)} N-1 contingency violation(s)")
        if volt_warn and not volt_viol:
            findings.append(f"{len(volt_warn)} bus voltage warning(s)")
        if therm_warn and not therm_viol:
            findings.append(f"{len(therm_warn)} thermal warning(s)")
        if not findings:
            findings.append("All elements within normal operating limits.")

        return {"color": color, "verdict": verdict, "findings": findings}

    # -- Statistics --------------------------------------------------------

    @staticmethod
    def build_statistics(data: ReportData) -> dict:
        """Compute distribution buckets and high-level report statistics."""
        volt_buckets: dict[str, int] = {
            "<0.90": 0, "0.90-0.95": 0, "0.95-1.05": 0, "1.05-1.10": 0, ">1.10": 0,
        }
        for r in data.voltage:
            v = r.u_pu
            if   v < 0.90:  volt_buckets["<0.90"]     += 1
            elif v < 0.95:  volt_buckets["0.90-0.95"] += 1
            elif v <= 1.05: volt_buckets["0.95-1.05"] += 1
            elif v <= 1.10: volt_buckets["1.05-1.10"] += 1
            else:           volt_buckets[">1.10"]      += 1

        load_buckets: dict[str, int] = {
            "0-25%": 0, "25-50%": 0, "50-80%": 0, "80-100%": 0, ">100%": 0,
        }
        for r in data.loading:
            p = r.loading_pct
            if   p < 25:   load_buckets["0-25%"]   += 1
            elif p < 50:   load_buckets["25-50%"]  += 1
            elif p < 80:   load_buckets["50-80%"]  += 1
            elif p <= 100: load_buckets["80-100%"] += 1
            else:          load_buckets[">100%"]    += 1

        n1_total    = len(data.n1)
        n1_violated = sum(1 for r in data.n1 if r.status == "violation")

        return {
            "volt_buckets": volt_buckets,
            "load_buckets": load_buckets,
            "n1_total":     n1_total,
            "n1_violated":  n1_violated,
            "worst_n1":     max(data.n1, key=lambda r: r.max_loading_pct, default=None),
            "volt_worst":   min(data.voltage, key=lambda r: r.u_pu, default=None),
            "load_worst":   max(data.loading, key=lambda r: r.loading_pct, default=None),
            "power_balance": {
                "load_mw":   data.lf.total_load_mw,
                "gen_mw":    data.lf.total_gen_mw,
                "losses_mw": data.lf.losses_mw,
                "load_mvar": data.lf.total_load_mvar,
                "gen_mvar":  data.lf.total_gen_mvar,
            },
        }

    # -- Internal helpers --------------------------------------------------

    def _get_loading_hm_vr(self) -> VizRequest | None:
        return next(
            (vr for vr in self.config.visualizations
             if vr.variable == "c:loading" and vr.heatmap),
            None,
        )

    def _get_voltage_hm_vr(self) -> VizRequest | None:
        return next(
            (vr for vr in self.config.visualizations
             if vr.element_class == "ElmTerm" and vr.variable == "m:u" and vr.heatmap),
            None,
        )

    @staticmethod
    def _downsample_indices(
        time_labels: list[float | str], max_points: int | None
    ) -> list[int] | None:
        """Return evenly spaced indices for downsampling, or None when unused."""
        if not max_points or len(time_labels) <= max_points:
            return None
        count = len(time_labels)
        step  = max(1, math.floor(count / max_points))
        idx   = list(range(0, count, step))
        if idx[-1] != count - 1:
            idx.append(count - 1)
        if len(idx) > max_points:
            idx = idx[: max_points - 1] + [count - 1]
        return idx
