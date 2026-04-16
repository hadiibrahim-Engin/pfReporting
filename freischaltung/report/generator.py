"""HTML-Report-Generator – wandelt ReportData in eine portable HTML-Datei um."""
from __future__ import annotations

import json
import logging
from importlib import resources
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from freischaltung.config import FreischaltungConfig
from freischaltung.exceptions import ReportError
from freischaltung.report.builder import ReportData

log = logging.getLogger("freischaltung")

# Verzeichnis dieser Datei
_ASSETS_DIR = Path(__file__).parent / "assets"


class HTMLReportGenerator:
    """Erzeugt einen vollständig portablen (offline-fähigen) HTML-Report."""

    def __init__(self, config: FreischaltungConfig) -> None:
        self.config = config
        self._env = Environment(
            loader=PackageLoader("freischaltung.report", "templates"),
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

    # ── Öffentliche API ───────────────────────────────────────────────────

    def generate(self, data: ReportData) -> str:
        """Rendert den vollständigen HTML-Report und gibt ihn als String zurück."""
        try:
            template = self._env.get_template("report.html.j2")
        except Exception as exc:
            raise ReportError(f"Template-Ladefehler: {exc}") from exc

        chart_data = self._build_chart_data(data)
        heatmap_data = self._build_heatmap_data(data)

        try:
            html = template.render(
                info=data.info,
                overall=data.overall,
                switched=data.switched,
                lf=data.lf,
                voltage=data.voltage,
                loading=data.loading,
                n1=data.n1,
                ts_data=data.ts_data,
                viz_requests=self.config.visualizations,
                heatmap_data=heatmap_data,
                vcfg=self.config.voltage,
                tcfg=self.config.thermal,
                n1cfg=self.config.n1,
                css=self._css,
                scripts=self._scripts,
                vendor_js=self._vendor,
                chart_data_json=json.dumps(chart_data, ensure_ascii=False),
            )
        except Exception as exc:
            raise ReportError(f"Template-Renderfehler: {exc}") from exc

        log.info("HTML-Report erzeugt (%d Zeichen)", len(html))
        return html

    # ── Chart-Daten ───────────────────────────────────────────────────────

    def _build_chart_data(self, data: ReportData) -> list[dict]:
        """Erzeugt die window.__chartData-Struktur für scripts.js."""
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
        """Erzeugt Rohdaten für die CSS-/Canvas-Heatmaps."""
        result: dict[str, dict] = {}
        if data.ts_data.is_empty():
            return result

        for vr in self.config.visualizations:
            if not vr.heatmap:
                continue
            cid = vr.chart_id
            section = data.ts_data.sections.get(cid)
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
            ]
            result[cid] = {
                "time": [round(t, 2) if isinstance(t, float) else t for t in data.ts_data.time],
                "rows": rows,
                "unit": vr.unit,
            }

        return result

    # ── Hilfsmethoden ─────────────────────────────────────────────────────

    @staticmethod
    def _read_asset(relative_path: str) -> str:
        path = _ASSETS_DIR / relative_path
        if not path.exists():
            log.warning("Asset nicht gefunden: %s", path)
            return f"/* Asset nicht gefunden: {relative_path} */"
        return path.read_text(encoding="utf-8")
