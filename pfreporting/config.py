"""Configuration hierarchy – all parameters as Pydantic v2 models."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


# ─── Thresholds ───────────────────────────────────────────────────────────────


class VoltageConfig(BaseModel):
    lower_warning: float = 0.95
    lower_violation: float = 0.90
    upper_warning: float = 1.05
    upper_violation: float = 1.10

    @field_validator("lower_violation")
    @classmethod
    def _lo_order(cls, v: float, info) -> float:
        lo_w = info.data.get("lower_warning", 0.95)
        if v >= lo_w:
            raise ValueError("lower_violation must be < lower_warning")
        return v

    @field_validator("upper_violation")
    @classmethod
    def _hi_order(cls, v: float, info) -> float:
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
        warn = info.data.get("warning_pct", 80.0)
        if v <= warn:
            raise ValueError("violation_pct must be > warning_pct")
        return v


class N1Config(BaseModel):
    max_loading_pct: float = Field(100.0, ge=0)
    min_voltage_pu: float = Field(0.90, ge=0, le=1)
    max_voltage_pu: float = Field(1.10, ge=1)


# ─── Visualization ────────────────────────────────────────────────────────────


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
    max_elements: int = Field(200, ge=1, le=2000)

    @property
    def chart_id(self) -> str:
        """Unique ID for the chart canvas element."""
        from pfreporting.utils import sanitize_name

        return sanitize_name(f"{self.element_class}_{self.variable}")


def _default_visualizations() -> list[VizRequest]:
    return [
        VizRequest(
            element_class="ElmLne",
            variable="c:loading",
            label="Lines – Loading",
            unit="%",
            warn_hi=80.0,
            violation_hi=100.0,
            heatmap=True,
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmTr2",
            variable="c:loading",
            label="Transformers – Loading",
            unit="%",
            warn_hi=80.0,
            violation_hi=100.0,
            heatmap=False,
            max_elements=50,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:i1:bus1",
            label="Lines – Current",
            unit="kA",
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:P:bus1",
            label="Lines – Active Power",
            unit="MW",
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:Q:bus1",
            label="Lines – Reactive Power",
            unit="Mvar",
            max_elements=200,
        ),
    ]


# ─── Report output ────────────────────────────────────────────────────────────


class ReportConfig(BaseModel):
    output_dir: str = r"C:\PF_Reports"
    company: str = "Amprion GmbH"
    use_timestamp_subdir: bool = True
    quasi_dynamic_result_file: str = "Quasi-Dynamic Simulation AC.ElmRes"


# ─── Main config ──────────────────────────────────────────────────────────────


class PFReportConfig(BaseModel):
    voltage: VoltageConfig = Field(default_factory=VoltageConfig)
    thermal: ThermalConfig = Field(default_factory=ThermalConfig)
    n1: N1Config = Field(default_factory=N1Config)
    report: ReportConfig = Field(default_factory=ReportConfig)
    visualizations: list[VizRequest] = Field(
        default_factory=_default_visualizations
    )
