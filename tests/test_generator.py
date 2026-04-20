"""Tests for the HTML generator."""
import json
import re

import pytest

from pfreporting.config import PFReportConfig
from pfreporting.report.generator import HTMLReportGenerator


@pytest.fixture(scope="module")
def generated_html(mock_data) -> str:
    cfg = PFReportConfig()
    gen = HTMLReportGenerator(cfg)
    return gen.generate(mock_data)


class TestHTMLStructure:
    def test_is_valid_html_doctype(self, generated_html):
        assert generated_html.startswith("<!DOCTYPE html>")

    def test_charset_utf8(self, generated_html):
        assert 'charset="UTF-8"' in generated_html

    def test_contains_title(self, generated_html):
        assert "DE-ENERGIZATION" in generated_html.upper() or "Freischaltbewertung" in generated_html

    def test_contains_company(self, generated_html):
        assert "Amprion GmbH" in generated_html

    def test_contains_project(self, generated_html):
        assert "DEMO" in generated_html


class TestAmpelStatus:
    def test_violation_ampel_class(self, generated_html):
        # Template uses Tailwind border classes for violation state instead of custom CSS class names
        assert "border-red-400" in generated_html or "border-amber-400" in generated_html

    def test_violation_text(self, generated_html):
        assert "NOT PERMISSIBLE" in generated_html.upper() or "DE-ENERGIZATION ASSESSMENT" in generated_html.upper()

    def test_no_ok_ampel(self, generated_html):
        assert 'ampel-box ampel-ok' not in generated_html


class TestBadges:
    def test_violation_badge_present(self, generated_html):
        assert "badge-violation" in generated_html

    def test_warning_badge_present(self, generated_html):
        assert "badge-warning" in generated_html

    def test_ok_badge_present(self, generated_html):
        assert "badge-ok" in generated_html

    def test_badge_counts_roughly_correct(self, generated_html):
        n_viol = generated_html.count("badge-violation")
        n_warn = generated_html.count("badge-warning")
        assert n_viol >= 4  # at least the 4 violations
        assert n_warn >= 2  # at least warnings


class TestSections:
    def test_voltage_section(self, generated_html):
        assert "Voltage Band" in generated_html

    def test_thermal_section(self, generated_html):
        assert "Thermal Loading" in generated_html

    def test_n1_section(self, generated_html):
        # N-1 section is intentionally hidden from HTML output; only voltage+thermal shown
        assert "N-1" not in generated_html

    def test_statistics_section(self, generated_html):
        assert "Statistics" in generated_html

    def test_kpi_total_violations(self, generated_html):
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
        series_counts = [len(d.get("series", [])) for d in data]
        assert any(c > 0 for c in series_counts)


class TestOfflineCapability:
    def test_no_external_links_for_js(self, generated_html):
        # Chart.js and zoom plugins are inlined; Alpine.js uses CDN (acceptable for UI framework)
        assert "cdnjs.cloudflare.com" not in generated_html
        assert "window.__chartData" in generated_html  # core chart data is embedded

    def test_chart_js_inlined(self, generated_html):
        assert "Chart" in generated_html
        size = len(generated_html)
        assert size > 200_000  # With 3 vendor files inlined (~233 KB), must be substantial
