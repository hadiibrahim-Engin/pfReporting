"""Ausgabe-Datenmodelle (Pydantic v2) – kein PowerFactory-Import."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["ok", "warning", "violation"]


# ─── Projekt-Metadaten ───────────────────────────────────────────────────────


class ProjectInfo(BaseModel):
    project: str
    study_case: str
    date: str
    time: str
    datetime_full: str
    company: str
    author: str


# ─── Freigeschaltete Betriebsmittel ─────────────────────────────────────────


class SwitchedElement(BaseModel):
    name: str
    type: str
    status_before: str = "In Betrieb"
    status_assessment: str = "Freigeschaltet"


# ─── Lastflussergebnisse ─────────────────────────────────────────────────────


class LoadFlowResult(BaseModel):
    converged: bool
    status_text: str
    iterations: int
    total_load_mw: float
    total_gen_mw: float
    losses_mw: float


# ─── Spannungsband ───────────────────────────────────────────────────────────


class VoltageResult(BaseModel):
    node: str
    u_nenn_kv: float
    u_kv: float
    u_pu: float
    deviation_pct: float
    status: Status = "ok"
    time_series: list[float | None] = Field(default_factory=list)


# ─── Thermische Auslastung ───────────────────────────────────────────────────


class LoadingResult(BaseModel):
    name: str
    type: str
    loading_pct: float
    i_ka: float
    i_nenn_ka: float
    status: Status = "ok"
    time_series: list[float | None] = Field(default_factory=list)


# ─── N-1-Kontingenz ──────────────────────────────────────────────────────────


class N1Result(BaseModel):
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


# ─── Zeitreihen ──────────────────────────────────────────────────────────────


class TimeSeries(BaseModel):
    """Zeitreihe eines einzelnen Elements."""

    element_class: str
    variable: str
    label: str
    unit: str
    values: list[float | None]


class TimeSeriesData(BaseModel):
    """Gesammelte Zeitreihen nach Abschnitt (VizRequest-Kombination)."""

    time: list[float]
    # key = VizRequest.chart_id → dict[element_name, TimeSeries]
    sections: dict[str, dict[str, TimeSeries]] = Field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.time or not self.sections


# ─── Gesamtstatus ────────────────────────────────────────────────────────────


class StatusCounts(BaseModel):
    ok: int = 0
    warning: int = 0
    violation: int = 0


class OverallStatus(BaseModel):
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
