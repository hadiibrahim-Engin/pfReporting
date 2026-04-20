"""Configuration hierarchy - all parameters as Pydantic v2 models."""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field, field_validator


# --- Thresholds ---------------------------------------------------------------


class VoltageConfig(BaseModel):
    lower_warning: float = 0.95
    lower_violation: float = 0.90
    upper_warning: float = 1.05
    upper_violation: float = 1.10

    @field_validator("lower_violation")
    @classmethod
    def _lo_order(cls, v: float, info) -> float:
        """Ensure lower violation threshold is strictly below warning threshold.

        Args:
            v: Proposed ``lower_violation`` value.
            info: Pydantic validation context with sibling field values.

        Returns:
            Validated ``lower_violation`` value.
        """
        lo_w = info.data.get("lower_warning", 0.95)
        if v >= lo_w:
            raise ValueError("lower_violation must be < lower_warning")
        return v

    @field_validator("upper_violation")
    @classmethod
    def _hi_order(cls, v: float, info) -> float:
        """Ensure upper violation threshold is strictly above warning threshold.

        Args:
            v: Proposed ``upper_violation`` value.
            info: Pydantic validation context with sibling field values.

        Returns:
            Validated ``upper_violation`` value.
        """
        hi_w = info.data.get("upper_warning", 1.05)
        if v <= hi_w:
            raise ValueError("upper_violation must be > upper_warning")
        return v


class ThermalConfig(BaseModel):
    warning_pct: float = Field(80.0, ge=0, le=100)
    violation_pct: float = Field(100.0, ge=0)

    @field_validator("violation_pct")
    @classmethod
    def _order(cls, v: float, info) -> float:
        """Ensure thermal violation threshold is strictly above warning level.

        Args:
            v: Proposed ``violation_pct`` value.
            info: Pydantic validation context with sibling field values.

        Returns:
            Validated ``violation_pct`` value.
        """
        warn = info.data.get("warning_pct", 80.0)
        if v <= warn:
            raise ValueError("violation_pct must be > warning_pct")
        return v


class N1Config(BaseModel):
    max_loading_pct: float = Field(100.0, ge=0)
    min_voltage_pu: float = Field(0.90, ge=0, le=1)
    max_voltage_pu: float = Field(1.10, ge=1)


# --- Calculation options ------------------------------------------------------


class CalculationOptions(BaseModel):
    """Controls which calculation steps run and appear in the report."""

    run_qds: bool = True       # Quasi-dynamic simulation + time series charts
    run_loadflow: bool = True  # Static load flow
    run_voltage: bool = True   # Voltage band check
    run_thermal: bool = True   # Thermal loading check
    run_n1: bool = True        # N-1 contingency analysis


# --- QDS time range override --------------------------------------------------


class QDSConfig(BaseModel):
    """Optional overrides for the quasi-dynamic simulation time range.

    If set, these values are applied to ComStatsim before execution and are
    used instead of reading from the PowerFactory object. Leave as None to
    keep whatever is configured inside PowerFactory.
    """

    t_start: float | None = None   # Simulation start time [h] (legacy override)
    t_end: float | None = None     # Simulation end time [h] (legacy override)
    dt: float | None = None        # Time step [h]
    start_datetime: str | None = None  # Absolute start datetime, e.g. "2026-04-19 00:00"
    end_datetime: str | None = None    # Absolute end datetime, e.g. "2026-04-20 00:00"


# --- Visualization ------------------------------------------------------------


class VizRequest(BaseModel):
    """Describes a time series visualization in the report."""

    element_class: str
    variable: str
    label: str
    unit: str
    warn_hi: float | None = None
    violation_hi: float | None = None
    warn_lo: float | None = None
    violation_lo: float | None = None
    heatmap: bool = False
    heatmap_elements: list[str] | None = None
    max_elements: int = Field(200, ge=1, le=2000)

    @property
    def chart_id(self) -> str:
        """Build deterministic chart identifier.

        Returns:
            Sanitized id composed from ``element_class`` and ``variable``.
        """
        from pfreporting.utils import sanitize_name

        return sanitize_name(f"{self.element_class}_{self.variable}")


def _default_visualizations() -> list[VizRequest]:
    """Return built-in visualization defaults for report sections.

    Returns:
        Ordered list of default ``VizRequest`` definitions.
    """
    return [
        VizRequest(
            element_class="ElmLne",
            variable="c:loading",
            label="Lines - Loading",
            unit="%",
            warn_hi=80.0,
            violation_hi=100.0,
            heatmap=True,
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmTr2",
            variable="c:loading",
            label="Transformers - Loading",
            unit="%",
            warn_hi=80.0,
            violation_hi=100.0,
            heatmap=True,
            max_elements=50,
        ),
        VizRequest(
            element_class="ElmTerm",
            variable="m:u",
            label="Nodes - Voltage",
            unit="p.u.",
            warn_lo=0.95,
            violation_lo=0.90,
            warn_hi=1.05,
            violation_hi=1.10,
            heatmap=True,
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:i1:bus1",
            label="Lines - Current",
            unit="kA",
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:P:bus1",
            label="Lines - Active Power",
            unit="MW",
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:Q:bus1",
            label="Lines - Reactive Power",
            unit="Mvar",
            max_elements=200,
        ),
    ]


# --- Report output ------------------------------------------------------------


class ReportConfig(BaseModel):
    output_dir: str = r"C:\PF_Reports"
    company: str = "Amprion GmbH"
    use_timestamp_subdir: bool = True
    quasi_dynamic_result_file: str = "Quasi-Dynamic Simulation AC.ElmRes"
    intreport_name: str | None = None
    log_level: str = "INFO"
    max_points: int | None = Field(default=None, ge=50)
    output_format: str = "single"

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, v: str) -> str:
        level = str(v).upper()
        if level not in logging._nameToLevel:
            raise ValueError("log_level must be a valid logging level name")
        return level

    @field_validator("output_format")
    @classmethod
    def _validate_output_format(cls, v: str) -> str:
        if v not in ("single", "multi"):
            raise ValueError("output_format must be 'single' or 'multi'")
        return v


# --- Main config --------------------------------------------------------------


class PFReportConfig(BaseModel):
    voltage: VoltageConfig = Field(default_factory=VoltageConfig)
    thermal: ThermalConfig = Field(default_factory=ThermalConfig)
    n1: N1Config = Field(default_factory=N1Config)
    report: ReportConfig = Field(default_factory=ReportConfig)
    calc: CalculationOptions = Field(default_factory=CalculationOptions)
    qds: QDSConfig = Field(default_factory=QDSConfig)
    visualizations: list[VizRequest] = Field(
        default_factory=_default_visualizations
    )
