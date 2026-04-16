"""Tests für den HTML-Generator."""
import json
import re

import pytest

from freischaltung.config import FreischaltungConfig
from freischaltung.report.generator import HTMLReportGenerator


@pytest.fixture(scope="module")
def generated_html(mock_data) -> str:
    cfg = FreischaltungConfig()
    gen = HTMLReportGenerator(cfg)
    return gen.generate(mock_data)


class TestHTMLStructure:
    def test_is_valid_html_doctype(self, generated_html):
        assert generated_html.startswith("<!DOCTYPE html>")

    def test_charset_utf8(self, generated_html):
        assert 'charset="UTF-8"' in generated_html

    def test_contains_title(self, generated_html):
        assert "Freischaltungsbewertung" in generated_html

    def test_contains_company(self, generated_html):
        assert "Amprion GmbH" in generated_html

    def test_contains_project(self, generated_html):
        assert "DEMO" in generated_html


class TestAmpelStatus:
    def test_violation_ampel_class(self, generated_html):
        assert "ampel-verletzung" in generated_html

    def test_violation_text(self, generated_html):
        assert "NICHT ZULÄSSIG" in generated_html.upper() or "NICHT ZUL" in generated_html

    def test_no_ok_ampel(self, generated_html):
        # Should not have the OK ampel box for a violation report
        assert 'ampel-box ampel-ok' not in generated_html


class TestBadges:
    def test_violation_badge_present(self, generated_html):
        assert "badge-verletzung" in generated_html

    def test_warning_badge_present(self, generated_html):
        assert "badge-warnung" in generated_html

    def test_ok_badge_present(self, generated_html):
        assert "badge-ok" in generated_html

    def test_badge_counts_roughly_correct(self, generated_html):
        n_viol = generated_html.count("badge-verletzung")
        n_warn = generated_html.count("badge-warnung")
        assert n_viol >= 4  # at least the 4 violations
        assert n_warn >= 2  # at least warnings


class TestSections:
    def test_voltage_section(self, generated_html):
        assert "Spannungsbandprüfung" in generated_html or "Spannungsband" in generated_html

    def test_thermal_section(self, generated_html):
        assert "Thermische Auslastung" in generated_html

    def test_n1_section(self, generated_html):
        assert "N-1" in generated_html or "Kontingenz" in generated_html

    def test_statistics_section(self, generated_html):
        assert "Statistik" in generated_html

    def test_kpi_total_violations(self, generated_html):
        # KPI: 4 Verletzungen gesamt
        assert ">4<" in generated_html


class TestCharts:
    def test_canvas_elements_present(self, generated_html):
        assert "<canvas" in generated_html

    def test_chart_data_script_block(self, generated_html):
        assert "window.__chartData" in generated_html

    def test_chart_data_is_valid_json(self, generated_html):
        match = re.search(r'window\.__chartData\s*=\s*(\[.*?\]);', generated_html, re.DOTALL)
        assert match is not None, "window.__chartData not found"
        data = json.loads(match.group(1))
        assert isinstance(data, list)

    def test_chart_data_has_series(self, generated_html):
        match = re.search(r'window\.__chartData\s*=\s*(\[.*?\]);', generated_html, re.DOTALL)
        data = json.loads(match.group(1))
        # At least one chart should have series
        series_counts = [len(d.get("series", [])) for d in data]
        assert any(c > 0 for c in series_counts)


class TestOfflineCapability:
    def test_no_external_links_for_js(self, generated_html):
        # Vendor JS should be inlined, not loaded from CDN
        assert "cdn.jsdelivr.net" not in generated_html
        assert "cdnjs.cloudflare.com" not in generated_html

    def test_chart_js_inlined(self, generated_html):
        # chart.min.js content should be inline (check for typical Chart.js signature)
        assert "Chart" in generated_html
        # Chart.js defines itself as "chart.js" or similar
        size = len(generated_html)
        assert size > 200_000  # With 3 vendor files inlined (~233 KB), must be substantial
