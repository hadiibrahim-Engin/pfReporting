"""HTML report generator — converts ReportData into a portable HTML file."""
from __future__ import annotations

import datetime
import json
import shutil
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


class _BaseReportGenerator:
    """Shared Jinja2 environment and render context for all report generators."""

    def __init__(self, config: PFReportConfig) -> None:
        self.config = config
        self._env = Environment(
            loader=PackageLoader("pfreporting.report", "templates"),
            autoescape=select_autoescape(["html"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _build_render_context(self, data: ReportData) -> dict:
        """Assemble the full Jinja2 template context from ReportData."""
        t = ReportDataTransformer(self.config)

        chart_data = t.build_chart_data(data)
        heatmap    = t.build_heatmap_data(data)
        thermal_hm = t.build_thermal_hm_data(data)
        voltage_hm = t.build_voltage_hm_data(data)
        ampel      = t.build_ampel(data)
        stats      = t.build_statistics(data)
        radar      = t.build_radar_data(data)

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

        return dict(
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
            voltage_by_level=dict(sorted(voltage_by_level.items())),
            ampel=ampel,
            stats=stats,
            chart_data_json=json.dumps(chart_data, ensure_ascii=False),
            radar_data=radar,
            radar_data_json=json.dumps(radar, ensure_ascii=False),
            multipage=False,
        )


class HTMLReportGenerator(_BaseReportGenerator):
    """Generate a fully portable single-file HTML report from a ReportData snapshot."""

    def __init__(self, config: PFReportConfig) -> None:
        super().__init__(config)
        self._css      = self._read_asset("style.css")
        self._scripts  = self._read_asset("scripts.js")
        self._logo_svg = self._read_asset("logo_amprion.svg")
        self._chartjs = self._read_asset("vendor/chart.min.js")
        self._chartjs_zoom = self._read_asset("vendor/chartjs-plugin-zoom.min.js")
        self._hammer_js = self._read_asset("vendor/hammer.min.js")

    # -- Public API --------------------------------------------------------

    def generate(self, data: ReportData) -> str:
        """Render the complete HTML report string."""
        try:
            template = self._env.get_template("report.html.j2")
        except Exception as exc:
            raise ReportError(f"Template load error: {exc}") from exc

        ctx = self._build_render_context(data)
        try:
            html = template.render(
                **ctx,
                css=self._css,
                scripts=self._scripts,
                logo_svg=self._logo_svg,
                chartjs=self._chartjs,
                chartjs_zoom=self._chartjs_zoom,
                hammer_js=self._hammer_js,
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


class MultiPageReportGenerator(_BaseReportGenerator):
    """Generate a multi-page HTML report folder from a ReportData snapshot.

    Produces a folder with one HTML file per section and a shared assets/
    subdirectory. Pages link to each other via static <a href> navigation.
    Falls back to CDN for optional assets (Alpine, Tailwind, DataTables) if
    they have not been downloaded locally via ``pfreporting download-assets``.
    """

    PAGE_MAP = [
        ("index.html",         "pages/index.html.j2",         "overview"),
        ("statistics.html",    "pages/statistics.html.j2",    "statistics"),
        ("quasi_dynamic.html", "pages/quasi_dynamic.html.j2", "quasi_dynamic"),
        ("tables.html",        "pages/tables.html.j2",        "tables"),
        ("details.html",       "pages/details.html.j2",       "details"),
    ]

    def generate(self, data: ReportData) -> Path:
        """Render all pages and copy assets into a new folder. Returns the folder path."""
        ctx = self._build_render_context(data)
        folder = self._resolve_folder(data)
        folder.mkdir(parents=True, exist_ok=True)

        assets_dest = folder / "assets"
        ctx["asset_urls"] = self._copy_assets(assets_dest)
        ctx["multipage"] = True

        for filename, tmpl_path, page_id in self.PAGE_MAP:
            if page_id == "quasi_dynamic" and not self.config.calc.run_qds:
                continue
            try:
                tmpl = self._env.get_template(tmpl_path)
            except Exception as exc:
                raise ReportError(f"Template load error ({tmpl_path}): {exc}") from exc
            try:
                html = tmpl.render(**ctx, active_page=page_id)
            except Exception as exc:
                raise ReportError(f"Template render error ({tmpl_path}): {exc}") from exc
            (folder / filename).write_text(html, encoding="utf-8")
            log.info("Page written: %s", filename)

        log.info("Multi-page report folder: %s", folder)
        return folder

    def _resolve_folder(self, data: ReportData) -> Path:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = data.info.project.replace(" ", "_")[:40]
        folder_name = f"DeEnergizationAssessment_{safe_name}_{ts}"
        base = Path(self.config.report.output_dir)
        return base / folder_name

    def _copy_assets(self, dest: Path) -> dict:
        """Copy static assets to dest/ and return URL dict for templates.

        Bundled assets (style.css, scripts.js, Chart.js vendor) are always
        copied. Optional CDN assets (Alpine, Tailwind, DataTables) use the
        local copy if downloaded, otherwise a public CDN URL.
        """
        dest.mkdir(parents=True, exist_ok=True)

        for fname in ("style.css", "scripts.js"):
            src = _ASSETS_DIR / fname
            if src.exists():
                shutil.copy2(src, dest / fname)
            else:
                log.warning("Bundled asset missing: %s", src)

        vendor_dest = dest / "vendor"
        vendor_dest.mkdir(exist_ok=True)
        for fname in ("chart.min.js", "chartjs-plugin-zoom.min.js", "hammer.min.js"):
            src = _ASSETS_DIR / "vendor" / fname
            if src.exists():
                shutil.copy2(src, vendor_dest / fname)
            else:
                log.warning("Vendor asset missing: %s — run 'pfreporting download-assets'", fname)

        def _asset_url(rel_path: str, cdn_url: str) -> str:
            src = _ASSETS_DIR / rel_path
            dst = dest / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                shutil.copy2(src, dst)
                return f"./assets/{rel_path}"
            log.warning(
                "Optional asset not found: %s — using CDN (%s). "
                "Run 'pfreporting download-assets' for offline support.",
                rel_path, cdn_url,
            )
            return cdn_url

        return {
            "chartjs": _asset_url(
                "vendor/chart.min.js",
                "./assets/vendor/chart.min.js",
            ),
            "chartjs_zoom": _asset_url(
                "vendor/chartjs-plugin-zoom.min.js",
                "./assets/vendor/chartjs-plugin-zoom.min.js",
            ),
            "hammer_js": _asset_url(
                "vendor/hammer.min.js",
                "./assets/vendor/hammer.min.js",
            ),
            "tailwind": _asset_url(
                "tailwind.min.js", "https://cdn.tailwindcss.com"
            ),
            "alpine": _asset_url(
                "alpine.min.js",
                "https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js",
            ),
            "jquery": _asset_url(
                "datatables/jquery.min.js",
                "https://code.jquery.com/jquery-3.7.1.min.js",
            ),
            "datatables_js": _asset_url(
                "datatables/dataTables.min.js",
                "https://cdn.datatables.net/1.13.8/js/jquery.dataTables.min.js",
            ),
            "datatables_tailwind_js": _asset_url(
                "datatables/dataTables.tailwindcss.min.js",
                "https://cdn.datatables.net/1.13.8/js/dataTables.tailwindcss.min.js",
            ),
            "datatables_css": _asset_url(
                "datatables/dataTables.tailwindcss.min.css",
                "https://cdn.datatables.net/1.13.8/css/dataTables.tailwindcss.min.css",
            ),
        }
