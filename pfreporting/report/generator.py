"""HTML report generator - converts ReportData into a portable HTML file."""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from importlib import resources
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from pfreporting.config import PFReportConfig
from pfreporting.exceptions import ReportError
from pfreporting.logger import get_logger
from pfreporting.report.builder import ReportData

log = get_logger()

# Assets directory of this file
_ASSETS_DIR = Path(__file__).parent / "assets"


class HTMLReportGenerator:
    """Generate a fully portable (offline-capable) HTML report."""

    def __init__(self, config: PFReportConfig) -> None:
        """Prepare template environment and inline assets.

        Args:
            config: Report configuration used for rendering and threshold lines.
        """
        self.config = config
        self._env = Environment(
            loader=PackageLoader("pfreporting.report", "templates"),
            autoescape=select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._css = self._read_asset("style.css")
        self._scripts = self._read_asset("scripts.js")
        self._vendor = {
            "chart":  self._read_asset("vendor/chart.min.js"),
            "hammer": self._read_asset("vendor/hammer.min.js"),
            "zoom":   self._read_asset("vendor/chartjs-plugin-zoom.min.js"),
        }

    # -- Public API --------------------------------------------------------

    def generate(self, data: ReportData) -> str:
        """Render the complete HTML report.

        Args:
            data: Fully assembled report data model.

        Returns:
            HTML document as a string.

        Raises:
            ReportError: If template loading or rendering fails.
        """
        try:
            template = self._env.get_template("report.html.j2")
        except Exception as exc:
            raise ReportError(f"Template load error: {exc}") from exc

        chart_data = self._build_chart_data(data)
        heatmap_data = self._build_heatmap_data(data)

        thermal_hm = self._build_thermal_hm_data(data)
        voltage_hm = self._build_voltage_hm_data(data)

        ampel = self._build_ampel(data)
        stats = self._build_statistics(data)

        # Top violations for quick-view panel in summary
        top_voltage_violations = sorted(
            [r for r in data.voltage if r.status == "violation"],
            key=lambda r: r.u_pu,  # ascending → worst undervoltage first
        )
        top_loading_violations = sorted(
            [r for r in data.loading if r.status == "violation"],
            key=lambda r: r.loading_pct,
            reverse=True,  # descending → worst overload first
        )

        # Voltage grouped by nominal voltage level
        voltage_by_level: dict[float, list] = defaultdict(list)
        for r in data.voltage:
            voltage_by_level[round(r.u_nenn_kv, 1)].append(r)
        voltage_by_level_sorted = dict(sorted(voltage_by_level.items()))

        try:
            html = template.render(
                info=data.info,
                qds_info=data.qds_info,
                overall=data.overall,
                switched=data.switched,
                lf=data.lf,
                voltage=data.voltage,
                loading=data.loading,
                n1=data.n1,
                ts_data=data.ts_data,
                viz_requests=self.config.visualizations,
                heatmap_data=heatmap_data,
                thermal_hm_data=thermal_hm,
                voltage_hm_data=voltage_hm,
                vcfg=self.config.voltage,
                tcfg=self.config.thermal,
                n1cfg=self.config.n1,
                calc_options=self.config.calc,
                top_voltage_violations=top_voltage_violations,
                top_loading_violations=top_loading_violations,
                voltage_by_level=voltage_by_level_sorted,
                ampel=ampel,
                stats=stats,
                css=self._css,
                scripts=self._scripts,
                vendor_js=self._vendor,
                chart_data_json=json.dumps(chart_data, ensure_ascii=False),
            )
        except Exception as exc:
            raise ReportError(f"Template render error: {exc}") from exc

        log.info("HTML report generated (%d characters)", len(html))
        return html

    # -- Chart data --------------------------------------------------------

    def _build_chart_data(self, data: ReportData) -> list[dict]:
        """Build ``window.__chartData`` payload consumed by ``scripts.js``.

        Args:
            data: Report dataset with filtered time-series sections.

        Returns:
            List of chart configuration dictionaries.

        Each returned item contains:
            - ``id``: DOM chart container id
            - ``label`` / ``unit``: display metadata
            - threshold fields (``warn_*`` and ``violation_*``)
            - ``time``: x-axis labels
            - ``series``: list of ``{"name": str, "values": list}``
        """
        if data.ts_data.is_empty():
            return []

        result: list[dict] = []
        time_labels = [
            round(t, 3) if isinstance(t, float) else t
            for t in data.ts_data.time
        ]

        for vr in self.config.visualizations:
            cid = vr.chart_id
            section = data.ts_data.sections.get(cid)
            if not section:
                continue

            series_list = [
                {
                    "name": name,
                    "values": [
                        round(v, 4) if v is not None else None
                        for v in ts.values
                    ],
                }
                for name, ts in section.items()
            ]

            result.append({
                "id":           f"chart-{cid}",
                "label":        vr.label,
                "unit":         vr.unit,
                "warn_hi":      vr.warn_hi,
                "violation_hi": vr.violation_hi,
                "warn_lo":      vr.warn_lo,
                "violation_lo": vr.violation_lo,
                "time":         time_labels,
                "series":       series_list,
            })

        return result

    def _build_heatmap_data(self, data: ReportData) -> dict[str, dict]:
        """Build generic heatmap payloads keyed by visualization chart id.

        Args:
            data: Report dataset with raw and filtered time series.

        Returns:
            ``dict[chart_id, heatmap_payload]`` for enabled heatmap requests.

        The method prefers unfiltered ``ts_raw`` so heatmaps can show complete
        distributions even when chart series were reduced to critical subsets.
        """
        result: dict[str, dict] = {}
        src = data.ts_raw if not data.ts_raw.is_empty() else data.ts_data
        if src.is_empty():
            return result

        for vr in self.config.visualizations:
            if not vr.heatmap:
                continue
            cid = vr.chart_id
            section = src.sections.get(cid)
            if not section:
                continue

            rows = [
                {
                    "name": name,
                    "values": [
                        round(v, 2) if v is not None else None
                        for v in ts.values
                    ],
                }
                for name, ts in section.items()
                if not vr.heatmap_elements or name in vr.heatmap_elements
            ]
            result[cid] = {
                "time": [round(t, 2) if isinstance(t, float) else t for t in src.time],
                "rows": rows,
                "unit": vr.unit,
            }

        return result

    def _get_loading_hm_vr(self) -> "VizRequest | None":
        """Return loading heatmap visualization request if configured.

        Returns:
            First matching ``VizRequest`` or ``None``.
        """
        from pfreporting.config import VizRequest  # noqa: F401 (type hint only)
        return next(
            (vr for vr in self.config.visualizations if vr.variable == "c:loading" and vr.heatmap),
            None,
        )

    def _get_voltage_hm_vr(self) -> "VizRequest | None":
        """Return voltage heatmap visualization request if configured.

        Returns:
            First matching ``VizRequest`` or ``None``.
        """
        return next(
            (vr for vr in self.config.visualizations
             if vr.element_class == "ElmTerm" and vr.variable == "m:u" and vr.heatmap),
            None,
        )

    def _build_thermal_hm_data(self, data: ReportData) -> dict | None:
        """Build thermal loading heatmap data for section-level rendering.

        Args:
            data: Report dataset with loading and time-series values.

        Returns:
            Heatmap payload for thermal section, or ``None`` if unavailable.

        Selection rules:
            - include only series where ``variable == 'c:loading'``
            - keep at most one row per element name
            - optionally apply ``heatmap_elements`` whitelist
        """
        src = data.ts_raw if not data.ts_raw.is_empty() else data.ts_data
        if src.is_empty():
            return None
        hm_vr = self._get_loading_hm_vr()
        whitelist = hm_vr.heatmap_elements if hm_vr else None
        status_map = {r.name: r.status for r in data.loading}
        time = [round(t, 3) for t in src.time]
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
                    "values": [round(v, 2) if v is not None else None for v in ts.values],
                    "status": status_map.get(name, "ok"),
                })
        if not rows:
            log.debug("thermal_hm_data: no c:loading series found in ts_raw")
            return None
        return {
            "time":         time,
            "rows":         rows,
            "unit":         "%",
            "warn_hi":      self.config.thermal.warning_pct,
            "violation_hi": self.config.thermal.violation_pct,
        }

    def _build_voltage_hm_data(self, data: ReportData) -> dict | None:
        """Build bus-voltage heatmap data for section-level rendering.

        Args:
            data: Report dataset with voltage and time-series values.

        Returns:
            Heatmap payload for voltage section, or ``None`` if unavailable.

        Selection rules:
            - include only ``ElmTerm`` series
            - deduplicate element names across sections
            - optionally apply ``heatmap_elements`` whitelist
        """
        src = data.ts_raw if not data.ts_raw.is_empty() else data.ts_data
        if src.is_empty():
            return None
        hm_vr = self._get_voltage_hm_vr()
        whitelist = hm_vr.heatmap_elements if hm_vr else None
        status_map = {r.node: r.status for r in data.voltage}
        time = [round(t, 3) for t in src.time]
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
                    "values": [round(v, 4) if v is not None else None for v in ts.values],
                    "status": status_map.get(name, "ok"),
                })
        if not rows:
            log.debug("voltage_hm_data: no ElmTerm series found in ts_raw")
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

    @staticmethod
    def _build_ampel(data: ReportData) -> dict:
        """Compute traffic-light verdict and summary findings.

        Args:
            data: Report dataset with analyzed status values.

        Returns:
            Dictionary with ``color``, ``verdict`` and ``findings`` keys.

        Decision precedence is strict: red (any violation) > amber (warnings
        without violations) > green (all clear).
        """
        volt_viol = [r for r in data.voltage if r.status == "violation"]
        volt_warn = [r for r in data.voltage if r.status == "warning"]
        therm_viol = [r for r in data.loading if r.status == "violation"]
        therm_warn = [r for r in data.loading if r.status == "warning"]
        n1_viol = [r for r in data.n1 if r.status == "violation"]

        if volt_viol or therm_viol or n1_viol:
            color = "red"
            verdict = "DE-ENERGIZATION NOT FEASIBLE"
        elif volt_warn or therm_warn:
            color = "amber"
            verdict = "DE-ENERGIZATION FEASIBLE WITH RESERVATIONS"
        else:
            color = "green"
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

    @staticmethod
    def _build_statistics(data: ReportData) -> dict:
        """Compute distribution buckets and high-level report statistics.

        Args:
            data: Report dataset containing voltage/loading/n1 sections.

        Returns:
            Statistics dictionary used by the report statistics section.

        Voltage buckets use p.u. ranges:
            ``<0.90``, ``0.90-0.95``, ``0.95-1.05``, ``1.05-1.10``, ``>1.10``.
        Loading buckets use percent ranges:
            ``0-25%``, ``25-50%``, ``50-80%``, ``80-100%``, ``>100%``.
        """
        volt_buckets: dict[str, int] = {
            "<0.90": 0, "0.90-0.95": 0, "0.95-1.05": 0, "1.05-1.10": 0, ">1.10": 0,
        }
        for r in data.voltage:
            v = r.u_pu
            if v < 0.90:
                volt_buckets["<0.90"] += 1
            elif v < 0.95:
                volt_buckets["0.90-0.95"] += 1
            elif v <= 1.05:
                volt_buckets["0.95-1.05"] += 1
            elif v <= 1.10:
                volt_buckets["1.05-1.10"] += 1
            else:
                volt_buckets[">1.10"] += 1

        load_buckets: dict[str, int] = {
            "0-25%": 0, "25-50%": 0, "50-80%": 0, "80-100%": 0, ">100%": 0,
        }
        for r in data.loading:
            p = r.loading_pct
            if p < 25:
                load_buckets["0-25%"] += 1
            elif p < 50:
                load_buckets["25-50%"] += 1
            elif p < 80:
                load_buckets["50-80%"] += 1
            elif p <= 100:
                load_buckets["80-100%"] += 1
            else:
                load_buckets[">100%"] += 1

        n1_total = len(data.n1)
        n1_violated = sum(1 for r in data.n1 if r.status == "violation")
        worst_n1 = max(data.n1, key=lambda r: r.max_loading_pct, default=None)

        return {
            "volt_buckets": volt_buckets,
            "load_buckets": load_buckets,
            "n1_total": n1_total,
            "n1_violated": n1_violated,
            "worst_n1": worst_n1,
            "volt_worst": min(data.voltage, key=lambda r: r.u_pu, default=None),
            "load_worst": max(data.loading, key=lambda r: r.loading_pct, default=None),
            "power_balance": {
                "load_mw":   data.lf.total_load_mw,
                "gen_mw":    data.lf.total_gen_mw,
                "losses_mw": data.lf.losses_mw,
                "load_mvar": data.lf.total_load_mvar,
                "gen_mvar":  data.lf.total_gen_mvar,
            },
        }

    # -- Helper methods ----------------------------------------------------

    @staticmethod
    def _read_asset(relative_path: str) -> str:
        """Read one bundled text asset.

        Args:
            relative_path: Asset path under the report ``assets`` directory.

        Returns:
            Asset file content, or a CSS/JS comment stub when missing.
        """
        path = _ASSETS_DIR / relative_path
        if not path.exists():
            log.warning("Asset not found: %s", path)
            return f"/* Asset not found: {relative_path} */"
        return path.read_text(encoding="utf-8")
