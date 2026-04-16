"""Tests für die AnalysisEngine – Grenzwertlogik."""
import pytest

from freischaltung.analysis import AnalysisEngine
from freischaltung.config import FreischaltungConfig


@pytest.fixture
def engine() -> AnalysisEngine:
    return AnalysisEngine(FreischaltungConfig())


class TestVoltageAnalysis:
    def test_ok_range(self, engine, mock_voltage_results):
        r = mock_voltage_results[0]  # u_pu=1.00
        result = engine.analyze_voltages([r])[0]
        assert result.status == "ok"

    def test_lower_boundary_warning(self, engine):
        from freischaltung.models import VoltageResult
        r = VoltageResult(node="X", u_nenn_kv=110.0, u_kv=104.5, u_pu=0.95, deviation_pct=-5.0)
        engine.analyze_voltages([r])
        assert r.status == "warning"

    def test_lower_boundary_ok_just_above_warn(self, engine):
        from freischaltung.models import VoltageResult
        r = VoltageResult(node="X", u_nenn_kv=110.0, u_kv=105.6, u_pu=0.9501, deviation_pct=-4.99)
        engine.analyze_voltages([r])
        assert r.status == "ok"

    def test_lower_violation(self, engine):
        from freischaltung.models import VoltageResult
        r = VoltageResult(node="X", u_nenn_kv=110.0, u_kv=98.0, u_pu=0.89, deviation_pct=-11.0)
        engine.analyze_voltages([r])
        assert r.status == "violation"

    def test_upper_violation(self, engine):
        from freischaltung.models import VoltageResult
        r = VoltageResult(node="X", u_nenn_kv=110.0, u_kv=122.1, u_pu=1.11, deviation_pct=+11.0)
        engine.analyze_voltages([r])
        assert r.status == "violation"

    def test_all_fixture_statuses(self, engine, mock_voltage_results):
        engine.analyze_voltages(mock_voltage_results)
        expected = ["ok", "warning", "violation", "warning", "violation"]
        assert [r.status for r in mock_voltage_results] == expected


class TestThermalAnalysis:
    def test_boundary_79_9_is_ok(self, engine):
        from freischaltung.models import LoadingResult
        r = LoadingResult(name="X", type="Leitung", loading_pct=79.9, i_ka=0.0, i_nenn_ka=0.0)
        engine.analyze_thermal([r])
        assert r.status == "ok"

    def test_boundary_80_is_warning(self, engine):
        from freischaltung.models import LoadingResult
        r = LoadingResult(name="X", type="Leitung", loading_pct=80.0, i_ka=0.0, i_nenn_ka=0.0)
        engine.analyze_thermal([r])
        assert r.status == "warning"

    def test_boundary_100_is_violation(self, engine):
        from freischaltung.models import LoadingResult
        r = LoadingResult(name="X", type="Leitung", loading_pct=100.0, i_ka=0.0, i_nenn_ka=0.0)
        engine.analyze_thermal([r])
        assert r.status == "violation"

    def test_overload_is_violation(self, engine):
        from freischaltung.models import LoadingResult
        r = LoadingResult(name="X", type="Leitung", loading_pct=120.0, i_ka=0.0, i_nenn_ka=0.0)
        engine.analyze_thermal([r])
        assert r.status == "violation"


class TestN1Analysis:
    def test_converged_no_violations_is_ok(self, engine):
        from freischaltung.models import N1Result
        r = N1Result(
            outage_element="X", type="Leitung", converged=True,
            max_loading_pct=90.0, max_loading_element="Y",
            min_voltage_pu=0.96, min_voltage_node="Z",
            max_voltage_pu=1.04, max_voltage_node="W",
        )
        engine.analyze_n1([r])
        assert r.status == "ok"

    def test_non_convergence_is_violation(self, engine, mock_n1_results):
        engine.analyze_n1(mock_n1_results)
        non_conv = next(r for r in mock_n1_results if not r.converged)
        assert non_conv.status == "violation"

    def test_violation_list_sets_violation(self, engine, mock_n1_results):
        engine.analyze_n1(mock_n1_results)
        lne_b = next(r for r in mock_n1_results if r.outage_element == "Lne_B")
        assert lne_b.status == "violation"


class TestOverallStatus:
    def test_no_violations_is_ok(self, engine, mock_voltage_results, mock_loading_results, mock_n1_results):
        # Force all to ok
        for r in mock_voltage_results:
            r.status = "ok"
        for r in mock_loading_results:
            r.status = "ok"
        for r in mock_n1_results:
            r.status = "ok"
            r.violations = []
            r.converged = True
        status = engine.get_overall_status(mock_voltage_results, mock_loading_results, mock_n1_results)
        assert status.status == "ok"

    def test_single_violation_sets_violation(self, engine, mock_voltage_results, mock_loading_results, mock_n1_results):
        for r in mock_voltage_results + mock_loading_results:
            r.status = "ok"
        for r in mock_n1_results:
            r.status = "ok"
        mock_loading_results[0].status = "violation"
        status = engine.get_overall_status(mock_voltage_results, mock_loading_results, mock_n1_results)
        assert status.status == "violation"
        assert status.thermal_violations == 1

    def test_mock_data_status(self, mock_data):
        assert mock_data.overall.status == "violation"
        assert mock_data.overall.total_violations == 4
