"""Supplementary HTML renderers for standalone report documents."""
from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from pfreporting.config import PFReportConfig
from pfreporting.logger import get_logger
from pfreporting.report.builder import ReportData
from pfreporting.report.transformer import ReportDataTransformer

log = get_logger()

_ASSETS_DIR = Path(__file__).parent / "assets"


def _make_env() -> Environment:
    return Environment(
        loader=PackageLoader("pfreporting.report", "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _read_asset(relative_path: str) -> str:
    path = _ASSETS_DIR / relative_path
    if not path.exists():
        log.warning("Asset not found: %s", path)
        return f"/* Asset not found: {relative_path} */"
    return path.read_text(encoding="utf-8")


class QDSDetailRenderer:
    """Standalone QDS detail report (time series + heatmaps, no tabs)."""

    def __init__(self, config: PFReportConfig) -> None:
        self.config   = config
        self._env     = _make_env()
        self._css     = _read_asset("style.css")
        self._scripts = _read_asset("scripts.js")
        self._chartjs = _read_asset("vendor/chart.min.js")
        self._chartjs_zoom = _read_asset("vendor/chartjs-plugin-zoom.min.js")
        self._hammer_js = _read_asset("vendor/hammer.min.js")

    def render(self, data: ReportData) -> str:
        t            = ReportDataTransformer(self.config)
        chart_data   = t.build_chart_data(data)
        heatmap_data = t.build_heatmap_data(data)

        template = self._env.get_template("qds_detail.html.j2")
        return template.render(
            info=data.info,
            qds_info=data.qds_info,
            lf=data.lf,
            ts_data=data.ts_data,
            viz_requests=self.config.visualizations,
            heatmap_data=heatmap_data,
            calc_options=self.config.calc,
            css=self._css,
            scripts=self._scripts,
            chartjs=self._chartjs,
            chartjs_zoom=self._chartjs_zoom,
            hammer_js=self._hammer_js,
            chart_data_json=json.dumps(chart_data, ensure_ascii=False),
        )


class LoadFlowComparisonRenderer:
    """Standalone before/after load-flow comparison report."""

    def __init__(self, config: PFReportConfig) -> None:
        self.config = config
        self._env   = _make_env()
        self._css   = _read_asset("style.css")

    def render(self, data: ReportData, data_before: ReportData | None = None) -> str:
        voltage_rows = self._build_voltage_comparison(data, data_before)
        loading_rows = self._build_loading_comparison(data, data_before)

        template = self._env.get_template("loadflow_comparison.html.j2")
        return template.render(
            info=data.info,
            lf_after=data.lf,
            lf_before=data_before.lf if data_before else None,
            voltage_rows=voltage_rows,
            loading_rows=loading_rows,
            n1=data.n1,
            calc_options=self.config.calc,
            css=self._css,
        )

    @staticmethod
    def _build_voltage_comparison(
        data: ReportData, data_before: ReportData | None,
    ) -> list[dict]:
        before_map = {r.node: r.u_pu for r in data_before.voltage} if data_before else {}
        rows = []
        for r in data.voltage:
            u_before = before_map.get(r.node)
            rows.append({
                "node":        r.node,
                "u_nenn_kv":   r.u_nenn_kv,
                "u_pu_before": u_before,
                "u_pu_after":  r.u_pu,
                "delta":       (r.u_pu - u_before) if u_before is not None else None,
                "status":      r.status,
            })
        return sorted(rows, key=lambda r: (r["status"] != "violation", r["status"] != "warning", r["node"]))

    @staticmethod
    def _build_loading_comparison(
        data: ReportData, data_before: ReportData | None,
    ) -> list[dict]:
        before_map = {r.name: r.loading_pct for r in data_before.loading} if data_before else {}
        rows = []
        for r in data.loading:
            l_before = before_map.get(r.name)
            rows.append({
                "name":           r.name,
                "loading_before": l_before,
                "loading_after":  r.loading_pct,
                "delta":          (r.loading_pct - l_before) if l_before is not None else None,
                "status":         r.status,
            })
        return sorted(rows, key=lambda r: (r["status"] != "violation", r["status"] != "warning", r["name"]))


class ExecSummaryRenderer:
    """Print-optimised standalone executive summary (no Alpine/DataTables/Chart.js)."""

    MAX_VIOLATIONS = 10

    def __init__(self, config: PFReportConfig) -> None:
        self.config = config
        self._env   = _make_env()
        self._css   = _read_asset("style.css")

    def render(self, data: ReportData) -> str:
        t      = ReportDataTransformer(self.config)
        ampel  = t.build_ampel(data)
        stats  = t.build_statistics(data)

        top_voltage = sorted(
            [r for r in data.voltage if r.status == "violation"],
            key=lambda r: r.u_pu,
        )[: self.MAX_VIOLATIONS]
        top_loading = sorted(
            [r for r in data.loading if r.status == "violation"],
            key=lambda r: r.loading_pct,
            reverse=True,
        )[: self.MAX_VIOLATIONS]

        template = self._env.get_template("executive_summary_standalone.html.j2")
        return template.render(
            info=data.info,
            overall=data.overall,
            lf=data.lf,
            ampel=ampel,
            stats=stats,
            top_voltage_violations=top_voltage,
            top_loading_violations=top_loading,
            vcfg=self.config.voltage,
            tcfg=self.config.thermal,
            n1cfg=self.config.n1,
            calc_options=self.config.calc,
            css=self._css,
        )
