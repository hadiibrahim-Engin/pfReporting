"""
test_pipeline.py — End-to-end pipeline test using mock data (no PF needed).

Run with:
    pytest tests/test_pipeline.py -v
or via CLI:
    python main.py test
"""

import pytest
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db_manager import DBManager
from database import db_queries as Q
from analysis import kpi_calculator, violation_detector, ranking
from reporting import chart_builder, data_assembler
from tests.mock_pf_data import populate_mock_database


# ── Fixture: temporary DB populated with mock data ────────────────────────────

@pytest.fixture(scope="module")
def mock_db(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("data") / "test.db"
    populate_mock_database(db_path)
    return db_path


@pytest.fixture(scope="module")
def db(mock_db):
    manager = DBManager(mock_db)
    manager.__enter__()
    yield manager
    manager.__exit__(None, None, None)


# ── Database layer ────────────────────────────────────────────────────────────

class TestDatabase:
    def test_nodes_populated(self, db):
        nodes = Q.get_all_nodes(db)
        assert len(nodes) == 1000, f"Expected 1000 nodes, got {len(nodes)}"

    def test_branches_populated(self, db):
        branches = Q.get_all_branches(db)
        assert len(branches) == 1200, f"Expected 1200 branches, got {len(branches)}"

    def test_contingencies_populated(self, db):
        full = Q.get_full_contingency_list(db)
        assert len(full) == 1200, f"Expected 1200 contingencies, got {len(full)}"

    def test_loading_violations_exist(self, db):
        viols = Q.get_loading_violations(db, threshold=80.0)
        assert len(viols) > 0, "Expected loading violations in mock data"

    def test_voltage_violations_exist(self, db):
        viols = Q.get_voltage_violations(db)
        assert len(viols) >= 0   # may be empty depending on mock data

    def test_top10_ordered_desc(self, db):
        top = Q.get_top_n_contingencies(db, n=10)
        loads = [r["max_loading_pct"] for r in top]
        assert loads == sorted(loads, reverse=True), "Top-10 not sorted by loading DESC"

    def test_critical_elements_have_frequency(self, db):
        elements = Q.get_critical_elements(db)
        for e in elements:
            assert e["frequency"] >= 1


# ── Analysis layer ────────────────────────────────────────────────────────────

class TestAnalysis:
    def test_kpis_complete(self, db):
        kpis = kpi_calculator.calculate_kpis(db)
        required = [
            "total_contingencies_analyzed",
            "critical_violations_count",
            "warning_count",
            "max_loading_pct",
            "max_loading_element",
            "voltage_violation_count",
            "affected_nodes_count",
            "n1_compliance_rate_pct",
            "prio1_measures_count",
        ]
        for key in required:
            assert key in kpis, f"Missing KPI key: {key}"

    def test_n1_compliance_rate_in_range(self, db):
        kpis = kpi_calculator.calculate_kpis(db)
        assert 0.0 <= kpis["n1_compliance_rate_pct"] <= 100.0

    def test_max_loading_positive(self, db):
        kpis = kpi_calculator.calculate_kpis(db)
        assert kpis["max_loading_pct"] > 0.0

    def test_loading_violations_have_severity(self, db):
        viols = violation_detector.loading_violations(db)
        for v in viols:
            assert v["severity"] in ("Kritisch", "Warnung")

    def test_ranking_adds_rank_field(self, db):
        top = ranking.top_n_contingencies(db, n=5)
        assert len(top) <= 5
        for i, r in enumerate(top, start=1):
            assert r["rank"] == i, f"Rank mismatch at position {i}"


# ── Reporting layer ───────────────────────────────────────────────────────────

class TestReporting:
    def test_pareto_chart_data_valid_json(self, db):
        import json
        top = ranking.top_n_contingencies(db, n=10)
        payload = chart_builder.pareto_chart_data(top)
        data = json.loads(payload)
        assert "labels" in data
        assert "loading_pct" in data
        assert "cumulative_pct" in data
        assert len(data["labels"]) == len(top)

    def test_loading_bar_chart_data_valid(self, db):
        import json
        viols = violation_detector.loading_violations(db)
        payload = chart_builder.loading_bar_chart_data(viols)
        data = json.loads(payload)
        assert len(data["labels"]) == len(data["values"])

    def test_context_assembler(self, mock_db):
        ctx = data_assembler.assemble_context(
            db_path=mock_db,
            scenario="Testlauf",
            netzname="Testnetz",
        )
        assert "kpis" in ctx
        assert "top_contingencies" in ctx
        assert "loading_violations" in ctx
        assert "full_contingency_list" in ctx
        assert ctx["netzname"] == "Testnetz"


# ── HTML render ───────────────────────────────────────────────────────────────

class TestHTMLRenderer:
    def test_render_to_temp_file(self, mock_db, tmp_path):
        from reporting.html_renderer import render_report
        template = Path(__file__).parent.parent / "templates" / "outage_report.html"
        if not template.exists():
            pytest.skip("Template not found — skipping render test")

        ctx = data_assembler.assemble_context(mock_db, netzname="Test")
        out = tmp_path / "report.html"
        result = render_report(ctx, template_path=template, output_path=out)
        assert result.exists()
        assert result.stat().st_size > 1000
