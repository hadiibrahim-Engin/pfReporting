"""Konfigurationshierarchie – alle Parameter als Pydantic-v2-Modelle."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


# ─── Grenzwerte ──────────────────────────────────────────────────────────────


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
            raise ValueError("lower_violation muss < lower_warning sein")
        return v

    @field_validator("upper_violation")
    @classmethod
    def _hi_order(cls, v: float, info) -> float:
        hi_w = info.data.get("upper_warning", 1.05)
        if v <= hi_w:
            raise ValueError("upper_violation muss > upper_warning sein")
        return v


class ThermalConfig(BaseModel):
    warning_pct: float = Field(80.0, ge=0, le=100)
    violation_pct: float = Field(100.0, ge=0)

    @field_validator("violation_pct")
    @classmethod
    def _order(cls, v: float, info) -> float:
        warn = info.data.get("warning_pct", 80.0)
        if v <= warn:
            raise ValueError("violation_pct muss > warning_pct sein")
        return v


class N1Config(BaseModel):
    max_loading_pct: float = Field(100.0, ge=0)
    min_voltage_pu: float = Field(0.90, ge=0, le=1)
    max_voltage_pu: float = Field(1.10, ge=1)


# ─── Visualisierung ──────────────────────────────────────────────────────────


class VizRequest(BaseModel):
    """Beschreibt eine Zeitreihen-Visualisierung im Report."""

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
        """Eindeutige ID für das Chart-Canvas-Element."""
        from freischaltung.utils import sanitize_name

        return sanitize_name(f"{self.element_class}_{self.variable}")


def _default_visualizations() -> list[VizRequest]:
    return [
        VizRequest(
            element_class="ElmLne",
            variable="c:loading",
            label="Leitungen – Auslastung",
            unit="%",
            warn_hi=80.0,
            violation_hi=100.0,
            heatmap=True,
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmTr2",
            variable="c:loading",
            label="Transformatoren – Auslastung",
            unit="%",
            warn_hi=80.0,
            violation_hi=100.0,
            heatmap=False,
            max_elements=50,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:i1:bus1",
            label="Leitungen – Strom",
            unit="kA",
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:P:bus1",
            label="Leitungen – Wirkleistung",
            unit="MW",
            max_elements=200,
        ),
        VizRequest(
            element_class="ElmLne",
            variable="m:Q:bus1",
            label="Leitungen – Blindleistung",
            unit="Mvar",
            max_elements=200,
        ),
    ]


# ─── Report-Ausgabe ──────────────────────────────────────────────────────────


class ReportConfig(BaseModel):
    output_dir: str = r"C:\PF_Reports"
    company: str = "Amprion GmbH"
    use_timestamp_subdir: bool = True
    quasi_dynamic_result_file: str = "Quasi-Dynamic Simulation AC.ElmRes"


# ─── Haupt-Config ────────────────────────────────────────────────────────────


class FreischaltungConfig(BaseModel):
    voltage: VoltageConfig = Field(default_factory=VoltageConfig)
    thermal: ThermalConfig = Field(default_factory=ThermalConfig)
    n1: N1Config = Field(default_factory=N1Config)
    report: ReportConfig = Field(default_factory=ReportConfig)
    visualizations: list[VizRequest] = Field(
        default_factory=_default_visualizations
    )
