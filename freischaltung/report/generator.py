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

        thermal_hm = self._build_thermal_hm_data(data)
        voltage_hm = self._build_voltage_hm_data(data)

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

    def _build_thermal_hm_data(self, data: ReportData) -> dict | None:
        """Heatmap-Daten für thermische Auslastung (alle c:loading-Serien)."""
        if data.ts_data.is_empty():
            return None
        status_map = {r.name: r.status for r in data.loading}
        time = [round(t, 3) for t in data.ts_data.time]
        seen: set[str] = set()
        rows: list[dict] = []
        for section in data.ts_data.sections.values():
            for name, ts in section.items():
                if ts.variable == "c:loading" and name not in seen:
                    seen.add(name)
                    rows.append({
                        "name":   name,
                        "values": [round(v, 2) if v is not None else None for v in ts.values],
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

    def _build_voltage_hm_data(self, data: ReportData) -> dict | None:
        """Heatmap-Daten für Spannungen (alle ElmTerm-Serien)."""
        if data.ts_data.is_empty():
            return None
        status_map = {r.node: r.status for r in data.voltage}
        time = [round(t, 3) for t in data.ts_data.time]
        seen: set[str] = set()
        rows: list[dict] = []
        for section in data.ts_data.sections.values():
            for name, ts in section.items():
                if ts.element_class == "ElmTerm" and name not in seen:
                    seen.add(name)
                    rows.append({
                        "name":   name,
                        "values": [round(v, 4) if v is not None else None for v in ts.values],
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

    # ── Hilfsmethoden ─────────────────────────────────────────────────────

    @staticmethod
    def _read_asset(relative_path: str) -> str:
        path = _ASSETS_DIR / relative_path
        if not path.exists():
            log.warning("Asset nicht gefunden: %s", path)
            return f"/* Asset nicht gefunden: {relative_path} */"
        return path.read_text(encoding="utf-8")
