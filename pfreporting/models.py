"""Output data models (Pydantic v2) - no PowerFactory imports."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["ok", "warning", "violation"]


# --- Project metadata ---------------------------------------------------------


class ProjectInfo(BaseModel):
    """Metadata describing the executed assessment context."""

    project: str
    study_case: str
    date: str
    time: str
    datetime_full: str
    company: str
    author: str


# --- Quasi-dynamic simulation -------------------------------------------------


class QDSInfo(BaseModel):
    """Configuration summary of the quasi-dynamic simulation run."""

    t_start_h: float = 0.0
    t_end_h: float = 24.0
    dt_h: float = 1.0
    n_steps: int = 0
    result_file: str = ""
    scenario: str = ""
    study_time_start: str = ""


class QDSStep(BaseModel):
    """Convergence state for a single quasi-dynamic simulation time step."""

    time_h: float
    converged: bool


# --- De-energized equipment ---------------------------------------------------


class SwitchedElement(BaseModel):
    """Element intentionally switched out of service before assessment."""

    name: str
    type: str
    status_before: str = "In Service"
    status_assessment: str = "De-energized"


# --- Load flow results --------------------------------------------------------


class LoadFlowResult(BaseModel):
    """Aggregated static load-flow metrics for the active study case."""

    converged: bool
    status_text: str
    iterations: int
    total_load_mw: float
    total_gen_mw: float
    losses_mw: float
    # Reactive power (populated when available)
    total_load_mvar: float = 0.0
    total_gen_mvar: float = 0.0
    losses_mvar: float = 0.0
    load_power_factor: float | None = None
    gen_power_factor: float | None = None
    qds_steps: list[QDSStep] = Field(default_factory=list)


# --- Voltage band -------------------------------------------------------------


class VoltageResult(BaseModel):
    """Voltage operating point and threshold status for one busbar/node."""

    node: str
    u_nenn_kv: float
    u_kv: float
    u_pu: float
    deviation_pct: float
    status: Status = "ok"
    time_series: list[float | None] = Field(default_factory=list)


# --- Thermal loading ----------------------------------------------------------


class LoadingResult(BaseModel):
    """Thermal loading metrics and status for one branch element."""

    name: str
    type: str
    loading_pct: float
    i_ka: float
    i_nenn_ka: float
    status: Status = "ok"
    time_series: list[float | None] = Field(default_factory=list)


# --- N-1 contingency ---------------------------------------------------------


class N1Result(BaseModel):
    """Post-contingency summary for a single N-1 outage scenario."""

    outage_element: str
    type: str
    converged: bool
    max_loading_pct: float
    max_loading_element: str
    min_voltage_pu: float
    min_voltage_node: str
    max_voltage_pu: float
    max_voltage_node: str
    violations: list[str] = Field(default_factory=list)
    status: Status = "ok"


# --- Time series --------------------------------------------------------------


class TimeSeries(BaseModel):
    """Time series for a single element."""

    element_class: str
    variable: str
    label: str
    unit: str
    values: list[float | None]


class TimeSeriesData(BaseModel):
    """Collected time series by section (VizRequest combination)."""

    time: list[float]
    # key = VizRequest.chart_id → dict[element_name, TimeSeries]
    sections: dict[str, dict[str, TimeSeries]] = Field(default_factory=dict)

    def is_empty(self) -> bool:
        """Check whether time-series payload contains usable data.

        Returns:
            ``True`` when either time axis or section mapping is empty.
        """
        return not self.time or not self.sections


# --- Overall status -----------------------------------------------------------


class StatusCounts(BaseModel):
    """Counters for status distribution within one analysis section."""

    ok: int = 0
    warning: int = 0
    violation: int = 0


class OverallStatus(BaseModel):
    """Consolidated assessment outcome across all analysis domains."""

    status: Status
    total_nodes: int
    total_elements: int
    total_n1: int
    total_violations: int
    voltage_violations: int
    voltage_warnings: int
    thermal_violations: int
    thermal_warnings: int
    n1_violations: int
    counts: dict[str, StatusCounts]
    summary_text: str = ""
