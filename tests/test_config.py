"""Tests für die Konfigurationsmodelle."""
import json

import pytest
from pydantic import ValidationError

from freischaltung.config import (
    FreischaltungConfig,
    ThermalConfig,
    VizRequest,
    VoltageConfig,
)


class TestVoltageConfig:
    def test_defaults(self):
        c = VoltageConfig()
        assert c.lower_violation < c.lower_warning
        assert c.upper_warning < c.upper_violation

    def test_invalid_lower_order(self):
        with pytest.raises(ValidationError):
            VoltageConfig(lower_warning=0.95, lower_violation=0.96)

    def test_invalid_upper_order(self):
        with pytest.raises(ValidationError):
            VoltageConfig(upper_warning=1.05, upper_violation=1.04)


class TestThermalConfig:
    def test_defaults(self):
        c = ThermalConfig()
        assert c.warning_pct < c.violation_pct

    def test_violation_must_exceed_warning(self):
        with pytest.raises(ValidationError):
            ThermalConfig(warning_pct=80.0, violation_pct=79.0)

    def test_warning_negative(self):
        with pytest.raises(ValidationError):
            ThermalConfig(warning_pct=-1.0)


class TestVizRequest:
    def test_chart_id_sanitized(self):
        vr = VizRequest(element_class="ElmLne", variable="c:loading", label="Test", unit="%")
        cid = vr.chart_id
        assert ":" not in cid
        assert cid.isidentifier() or "_" in cid

    def test_max_elements_bounds(self):
        with pytest.raises(ValidationError):
            VizRequest(element_class="ElmLne", variable="c:loading", label="X", unit="%", max_elements=0)
        with pytest.raises(ValidationError):
            VizRequest(element_class="ElmLne", variable="c:loading", label="X", unit="%", max_elements=2001)


class TestFreischaltungConfig:
    def test_default_visualizations(self):
        cfg = FreischaltungConfig()
        assert len(cfg.visualizations) >= 1
        loading_vr = [v for v in cfg.visualizations if v.variable == "c:loading"]
        assert len(loading_vr) >= 1

    def test_json_round_trip(self):
        cfg = FreischaltungConfig()
        serialized = cfg.model_dump_json()
        restored = FreischaltungConfig.model_validate_json(serialized)
        assert restored.voltage.lower_violation == cfg.voltage.lower_violation
        assert len(restored.visualizations) == len(cfg.visualizations)

    def test_json_round_trip_with_overrides(self):
        data = {
            "voltage": {"lower_warning": 0.93, "lower_violation": 0.88, "upper_warning": 1.07, "upper_violation": 1.12},
            "thermal": {"warning_pct": 75.0, "violation_pct": 95.0},
        }
        cfg = FreischaltungConfig.model_validate(data)
        assert cfg.voltage.lower_warning == 0.93
        assert cfg.thermal.warning_pct == 75.0
