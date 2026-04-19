"""HTML report generator — converts ReportData into a portable HTML file."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from pfreporting.config import PFReportConfig
from pfreporting.exceptions import ReportError
from pfreporting.logger import get_logger
from pfreporting.report.builder import ReportData
from pfreporting.report.transformer import ReportDataTransformer

log = get_logger()

_ASSETS_DIR = Path(__file__).parent / "assets"


class HTMLReportGenerator:
    """Generate a fully portable HTML report from a ReportData snapshot."""

    def __init__(self, config: PFReportConfig) -> None:
        self.config = config
        self._env = Environment(
            loader=PackageLoader("pfreporting.report", "templates"),
            autoescape=select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._css      = self._read_asset("style.css")
        self._scripts  = self._read_asset("scripts.js")
        self._logo_svg = self._read_asset("logo_amprion.svg")

    # -- Public API --------------------------------------------------------

    def generate(self, data: ReportData) -> str:
        """Render the complete HTML report string."""
        try:
            template = self._env.get_template("report.html.j2")
        except Exception as exc:
            raise ReportError(f"Template load error: {exc}") from exc

        t = ReportDataTransformer(self.config)

        chart_data  = t.build_chart_data(data)
        heatmap     = t.build_heatmap_data(data)
        thermal_hm  = t.build_thermal_hm_data(data)
        voltage_hm  = t.build_voltage_hm_data(data)
        ampel       = t.build_ampel(data)
        stats       = t.build_statistics(data)

        top_voltage_violations = sorted(
            [r for r in data.voltage if r.status == "violation"],
            key=lambda r: r.u_pu,
        )
        top_loading_violations = sorted(
            [r for r in data.loading if r.status == "violation"],
            key=lambda r: r.loading_pct,
            reverse=True,
        )

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
                warnings=data.warnings,
                heatmap_data=heatmap,
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
                logo_svg=self._logo_svg,
                chart_data_json=json.dumps(chart_data, ensure_ascii=False),
            )
        except Exception as exc:
            raise ReportError(f"Template render error: {exc}") from exc

        log.info("HTML report generated (%d characters)", len(html))
        return html

    # -- Asset loading -----------------------------------------------------

    @staticmethod
    def _read_asset(relative_path: str) -> str:
        path = _ASSETS_DIR / relative_path
        if not path.exists():
            log.warning("Asset not found: %s", path)
            return f"/* Asset not found: {relative_path} */"
        return path.read_text(encoding="utf-8")
