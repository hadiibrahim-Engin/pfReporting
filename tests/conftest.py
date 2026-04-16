"""Gemeinsame Fixtures für alle Tests."""
import pytest

from freischaltung._mock_data import build_mock_data
from freischaltung.config import (
    FreischaltungConfig,
    N1Config,
    ReportConfig,
    ThermalConfig,
    VoltageConfig,
)
from freischaltung.models import (
    LoadingResult,
    N1Result,
    VoltageResult,
)
from freischaltung.report.builder import ReportData


@pytest.fixture(scope="session")
def mock_config() -> FreischaltungConfig:
    return FreischaltungConfig()


@pytest.fixture(scope="session")
def mock_data() -> ReportData:
    return build_mock_data()


@pytest.fixture
def mock_voltage_results() -> list[VoltageResult]:
    return [
        VoltageResult(node="Bus_OK",        u_nenn_kv=110.0, u_kv=110.0, u_pu=1.00,  deviation_pct=0.0),
        VoltageResult(node="Bus_Warn_Lo",   u_nenn_kv=110.0, u_kv=104.5, u_pu=0.95,  deviation_pct=-5.0),
        VoltageResult(node="Bus_Viol_Lo",   u_nenn_kv=110.0, u_kv=98.0,  u_pu=0.89,  deviation_pct=-11.0),
        VoltageResult(node="Bus_Warn_Hi",   u_nenn_kv=110.0, u_kv=115.5, u_pu=1.05,  deviation_pct=+5.0),
        VoltageResult(node="Bus_Viol_Hi",   u_nenn_kv=110.0, u_kv=121.0, u_pu=1.11,  deviation_pct=+11.0),
    ]


@pytest.fixture
def mock_loading_results() -> list[LoadingResult]:
    return [
        LoadingResult(name="Lne_OK",    type="Leitung", loading_pct=50.0, i_ka=0.3, i_nenn_ka=0.6),
        LoadingResult(name="Lne_Warn",  type="Leitung", loading_pct=80.0, i_ka=0.5, i_nenn_ka=0.6),
        LoadingResult(name="Lne_Viol",  type="Leitung", loading_pct=100.0, i_ka=0.6, i_nenn_ka=0.6),
        LoadingResult(name="Lne_Viol2", type="Leitung", loading_pct=120.0, i_ka=0.7, i_nenn_ka=0.6),
    ]


@pytest.fixture
def mock_n1_results() -> list[N1Result]:
    return [
        N1Result(
            outage_element="Lne_A", type="Leitung", converged=True,
            max_loading_pct=90.0, max_loading_element="Lne_B",
            min_voltage_pu=0.96, min_voltage_node="Bus_X",
            max_voltage_pu=1.04, max_voltage_node="Bus_Y",
        ),
        N1Result(
            outage_element="Lne_B", type="Leitung", converged=True,
            max_loading_pct=102.0, max_loading_element="Lne_C",
            min_voltage_pu=0.92, min_voltage_node="Bus_X",
            max_voltage_pu=1.06, max_voltage_node="Bus_Y",
            violations=["Überlastung: Lne_C mit 102.0%"],
        ),
        N1Result(
            outage_element="Trafo_A", type="Transformator (2W)", converged=False,
            max_loading_pct=0.0, max_loading_element="-",
            min_voltage_pu=0.0, min_voltage_node="-",
            max_voltage_pu=0.0, max_voltage_node="-",
            violations=["Lastfluss konvergiert nicht!"],
        ),
    ]
