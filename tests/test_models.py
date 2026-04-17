"""Tests for Pydantic models."""
import pytest
from pydantic import ValidationError

from pfreporting.models import (
    LoadFlowResult,
    LoadingResult,
    N1Result,
    OverallStatus,
    ProjectInfo,
    StatusCounts,
    VoltageResult,
)


class TestVoltageResult:
    def test_defaults(self):
        r = VoltageResult(node="Bus", u_nenn_kv=110.0, u_kv=110.0, u_pu=1.0, deviation_pct=0.0)
        assert r.status == "ok"
        assert r.time_series == []

    def test_status_literal(self):
        r = VoltageResult(node="X", u_nenn_kv=20.0, u_kv=18.0, u_pu=0.9, deviation_pct=-10.0, status="violation")
        assert r.status == "violation"

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            VoltageResult(node="X", u_nenn_kv=20.0, u_kv=18.0, u_pu=0.9, deviation_pct=-10.0, status="critical")


class TestLoadingResult:
    def test_defaults(self):
        r = LoadingResult(name="Lne", type="Line", loading_pct=50.0, i_ka=0.3, i_nenn_ka=0.5)
        assert r.status == "ok"
        assert r.time_series == []

    def test_stores_values(self):
        r = LoadingResult(name="Lne", type="Line", loading_pct=104.2, i_ka=0.59, i_nenn_ka=0.565, status="violation")
        assert r.loading_pct == 104.2
        assert r.status == "violation"


class TestN1Result:
    def test_default_status(self):
        r = N1Result(
            outage_element="X", type="Line", converged=True,
            max_loading_pct=80.0, max_loading_element="Y",
            min_voltage_pu=0.97, min_voltage_node="Z",
            max_voltage_pu=1.03, max_voltage_node="W",
        )
        assert r.status == "ok"
        assert r.violations == []

    def test_non_convergence(self):
        r = N1Result(
            outage_element="T", type="Transformer (2W)", converged=False,
            max_loading_pct=0.0, max_loading_element="-",
            min_voltage_pu=0.0, min_voltage_node="-",
            max_voltage_pu=0.0, max_voltage_node="-",
        )
        assert not r.converged


class TestOverallStatus:
    def test_fields(self):
        s = OverallStatus(
            status="violation",
            total_nodes=10, total_elements=8, total_n1=5,
            total_violations=3,
            voltage_violations=1, voltage_warnings=2,
            thermal_violations=1, thermal_warnings=1,
            n1_violations=1,
            counts={
                "voltage": StatusCounts(ok=7, warning=2, violation=1),
                "thermal": StatusCounts(ok=6, warning=1, violation=1),
                "n1":      StatusCounts(ok=4, warning=0, violation=1),
            },
        )
        assert s.status == "violation"
        assert s.counts["voltage"].ok == 7
