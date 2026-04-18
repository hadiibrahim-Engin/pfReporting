"""Demo data – matches the bundled report template."""
from __future__ import annotations

import math

from pfreporting.models import (
    LoadFlowResult,
    LoadingResult,
    N1Result,
    OverallStatus,
    ProjectInfo,
    QDSInfo,
    QDSStep,
    StatusCounts,
    SwitchedElement,
    TimeSeries,
    TimeSeriesData,
    VoltageResult,
)
from pfreporting.report.builder import ReportData

_STEPS = 25
_TIME  = [float(i) for i in range(_STEPS)]


def build_mock_data() -> ReportData:
    info = ProjectInfo(
        project="DEMO",
        study_case="WinterLoad_2026",
        date="23.03.2026",
        time="21:26",
        datetime_full="23.03.2026 21:26:04",
        company="Amprion GmbH",
        author="Hadi Ibrahim",
    )

    qds_info = QDSInfo(
        t_start_h=0.0,
        t_end_h=24.0,
        dt_h=1.0,
        n_steps=_STEPS,
        result_file="Quasi-Dynamic Simulation AC.ElmRes",
        scenario="WinterLoad_2026",
        study_time_start="01.01.2026 00:00",
    )

    switched = [
        SwitchedElement(name="Line_110kV_North", type="Line"),
        SwitchedElement(name="Trafo_SS_Central_T2", type="Transformer (2W)"),
    ]

    # Steps 8 and 16 simulate non-convergence (all NaN in real PF – here None)
    non_conv = {8, 16}
    lf = LoadFlowResult(
        converged=True,
        status_text="Converged",
        iterations=4,
        total_load_mw=245.80,
        total_gen_mw=252.30,
        losses_mw=6.50,
        total_load_mvar=45.20,
        total_gen_mvar=48.10,
        losses_mvar=2.90,
        load_power_factor=0.983,
        gen_power_factor=0.982,
        qds_steps=[
            QDSStep(time_h=float(i), converged=(i not in non_conv))
            for i in range(_STEPS)
        ],
    )

    voltage = [
        VoltageResult(node="SS_Residential_20kV", u_nenn_kv=20.0,  u_kv=17.80,  u_pu=0.8900, deviation_pct=-11.00, status="violation"),
        VoltageResult(node="SS_West_110kV",        u_nenn_kv=110.0, u_kv=103.40, u_pu=0.9400, deviation_pct=-6.00,  status="warning"),
        VoltageResult(node="SS_Hospital_20kV",     u_nenn_kv=20.0,  u_kv=19.20,  u_pu=0.9600, deviation_pct=-4.00,  status="ok"),
        VoltageResult(node="SS_Industrial_20kV",   u_nenn_kv=20.0,  u_kv=19.40,  u_pu=0.9700, deviation_pct=-3.00,  status="ok"),
        VoltageResult(node="SS_South_110kV",       u_nenn_kv=110.0, u_kv=107.80, u_pu=0.9800, deviation_pct=-2.00,  status="ok"),
        VoltageResult(node="SS_Station_20kV",      u_nenn_kv=20.0,  u_kv=19.80,  u_pu=0.9900, deviation_pct=-1.00,  status="ok"),
        VoltageResult(node="SS_East_110kV",        u_nenn_kv=110.0, u_kv=111.10, u_pu=1.0100, deviation_pct=+1.00,  status="ok"),
        VoltageResult(node="SS_School_20kV",       u_nenn_kv=20.0,  u_kv=20.20,  u_pu=1.0100, deviation_pct=+1.00,  status="ok"),
        VoltageResult(node="SS_North_110kV",       u_nenn_kv=110.0, u_kv=112.20, u_pu=1.0200, deviation_pct=+2.00,  status="ok"),
        VoltageResult(node="SS_Central_110kV",     u_nenn_kv=110.0, u_kv=113.30, u_pu=1.0300, deviation_pct=+3.00,  status="ok"),
        VoltageResult(node="SS_Harbor_20kV",       u_nenn_kv=20.0,  u_kv=20.80,  u_pu=1.0400, deviation_pct=+4.00,  status="ok"),
        VoltageResult(node="SS_Commercial_20kV",   u_nenn_kv=20.0,  u_kv=21.20,  u_pu=1.0600, deviation_pct=+6.00,  status="warning"),
    ]

    loading = [
        LoadingResult(name="Line_110kV_Ring",     type="Line",             loading_pct=104.2, i_ka=0.590, i_nenn_ka=0.565, status="violation"),
        LoadingResult(name="Trafo_SS_Central_T1", type="Transformer (2W)", loading_pct=91.5,  i_ka=0.0,   i_nenn_ka=0.0,   status="warning"),
        LoadingResult(name="Line_110kV_East",     type="Line",             loading_pct=82.5,  i_ka=0.470, i_nenn_ka=0.565, status="warning"),
        LoadingResult(name="Line_20kV_2",         type="Line",             loading_pct=71.8,  i_ka=0.290, i_nenn_ka=0.400, status="ok"),
        LoadingResult(name="Trafo_SS_East_T1",    type="Transformer (2W)", loading_pct=68.0,  i_ka=0.0,   i_nenn_ka=0.0,   status="ok"),
        LoadingResult(name="Line_110kV_South",    type="Line",             loading_pct=67.3,  i_ka=0.380, i_nenn_ka=0.565, status="ok"),
        LoadingResult(name="Trafo_SS_South_T1",   type="Transformer (2W)", loading_pct=55.2,  i_ka=0.0,   i_nenn_ka=0.0,   status="ok"),
        LoadingResult(name="Line_20kV_1",         type="Line",             loading_pct=45.1,  i_ka=0.180, i_nenn_ka=0.400, status="ok"),
        LoadingResult(name="Line_20kV_3",         type="Line",             loading_pct=23.4,  i_ka=0.090, i_nenn_ka=0.400, status="ok"),
    ]

    n1 = [
        N1Result(
            outage_element="Line_110kV_Ring", type="Line", converged=True,
            max_loading_pct=112.0, max_loading_element="Line_110kV_East",
            min_voltage_pu=0.8800, min_voltage_node="SS_Residential_20kV",
            max_voltage_pu=1.0600, max_voltage_node="SS_North_110kV",
            violations=["Overload: Line_110kV_East at 112.0%", "Undervoltage: SS_Residential_20kV at 0.88 p.u."],
            status="violation",
        ),
        N1Result(
            outage_element="Trafo_SS_Central_T1", type="Transformer (2W)", converged=False,
            max_loading_pct=0.0, max_loading_element="-",
            min_voltage_pu=0.0, min_voltage_node="-",
            max_voltage_pu=0.0, max_voltage_node="-",
            violations=["Load flow does not converge!"],
            status="violation",
        ),
        N1Result(
            outage_element="Line_110kV_South", type="Line", converged=True,
            max_loading_pct=88.3, max_loading_element="Line_110kV_Ring",
            min_voltage_pu=0.9600, min_voltage_node="SS_South_110kV",
            max_voltage_pu=1.0300, max_voltage_node="SS_North_110kV",
            violations=[], status="ok",
        ),
        N1Result(
            outage_element="Line_110kV_East", type="Line", converged=True,
            max_loading_pct=95.1, max_loading_element="Line_110kV_Ring",
            min_voltage_pu=0.9400, min_voltage_node="SS_East_110kV",
            max_voltage_pu=1.0400, max_voltage_node="SS_Central_110kV",
            violations=[], status="ok",
        ),
        N1Result(
            outage_element="Line_20kV_1", type="Line", converged=True,
            max_loading_pct=72.0, max_loading_element="Line_20kV_2",
            min_voltage_pu=0.9700, min_voltage_node="SS_Industrial_20kV",
            max_voltage_pu=1.0200, max_voltage_node="SS_Central_110kV",
            violations=[], status="ok",
        ),
        N1Result(
            outage_element="Line_20kV_2", type="Line", converged=True,
            max_loading_pct=81.0, max_loading_element="Line_20kV_1",
            min_voltage_pu=0.9500, min_voltage_node="SS_Commercial_20kV",
            max_voltage_pu=1.0300, max_voltage_node="SS_Central_110kV",
            violations=[], status="ok",
        ),
        N1Result(
            outage_element="Trafo_SS_South_T1", type="Transformer (2W)", converged=True,
            max_loading_pct=78.5, max_loading_element="Trafo_SS_East_T1",
            min_voltage_pu=0.9300, min_voltage_node="SS_Harbor_20kV",
            max_voltage_pu=1.0500, max_voltage_node="SS_South_110kV",
            violations=[], status="ok",
        ),
    ]

    overall = OverallStatus(
        status="violation",
        total_nodes=12,
        total_elements=9,
        total_n1=7,
        total_violations=4,
        voltage_violations=1,
        voltage_warnings=2,
        thermal_violations=1,
        thermal_warnings=2,
        n1_violations=2,
        counts={
            "voltage": StatusCounts(ok=9, warning=2, violation=1),
            "thermal": StatusCounts(ok=6, warning=2, violation=1),
            "n1":      StatusCounts(ok=5, warning=0, violation=2),
        },
        summary_text=(
            "De-energization is <strong>NOT permissible</strong>. "
            "System security violations are present.<br>"
            " – 1 voltage band violation(s)<br>"
            " – 1 thermal overload(s)<br>"
            " – 2 (N-1) security violation(s)"
        ),
    )

    ts_data = _build_mock_timeseries()

    return ReportData(
        info=info,
        qds_info=qds_info,
        switched=switched,
        lf=lf,
        voltage=voltage,
        loading=loading,
        n1=n1,
        overall=overall,
        ts_data=ts_data,
    )


def _sine(base: float, amp: float, phase: float = 0.0) -> list[float]:
    return [
        round(base + amp * math.sin(2 * math.pi * i / 24 + phase), 4)
        for i in range(_STEPS)
    ]


def _build_mock_timeseries() -> TimeSeriesData:
    """Generate realistic sine curves as demo time series (24 h, 1 h steps)."""
    sections: dict = {}

    # ── ElmLne / c:loading ──────────────────────────────────────────────────
    sections["ElmLne_c_loading"] = {
        "Line_110kV_Ring": TimeSeries(
            element_class="ElmLne", variable="c:loading",
            label="Lines – Loading", unit="%",
            values=_sine(95.0, 15.0, 0.0),
        ),
        "Line_110kV_East": TimeSeries(
            element_class="ElmLne", variable="c:loading",
            label="Lines – Loading", unit="%",
            values=_sine(75.0, 12.0, 0.5),
        ),
        "Line_110kV_South": TimeSeries(
            element_class="ElmLne", variable="c:loading",
            label="Lines – Loading", unit="%",
            values=_sine(60.0, 8.0, 1.0),
        ),
    }

    # ── ElmTr2 / c:loading ──────────────────────────────────────────────────
    sections["ElmTr2_c_loading"] = {
        "Trafo_SS_Central_T1": TimeSeries(
            element_class="ElmTr2", variable="c:loading",
            label="Transformers – Loading", unit="%",
            values=_sine(85.0, 10.0, 0.3),
        ),
    }

    # ── ElmLne / m:i1:bus1 ──────────────────────────────────────────────────
    sections["ElmLne_m_i1_bus1"] = {
        "Line_110kV_Ring": TimeSeries(
            element_class="ElmLne", variable="m:i1:bus1",
            label="Lines – Current", unit="kA",
            values=_sine(0.48, 0.12, 0.0),
        ),
        "Line_110kV_East": TimeSeries(
            element_class="ElmLne", variable="m:i1:bus1",
            label="Lines – Current", unit="kA",
            values=_sine(0.40, 0.08, 0.5),
        ),
    }

    # ── ElmLne / m:P:bus1 ───────────────────────────────────────────────────
    sections["ElmLne_m_P_bus1"] = {
        "Line_110kV_Ring": TimeSeries(
            element_class="ElmLne", variable="m:P:bus1",
            label="Lines – Active Power", unit="MW",
            values=_sine(85.0, 20.0, 0.0),
        ),
        "Line_110kV_East": TimeSeries(
            element_class="ElmLne", variable="m:P:bus1",
            label="Lines – Active Power", unit="MW",
            values=_sine(65.0, 15.0, 0.5),
        ),
    }

    # ── ElmLne / m:Q:bus1 ───────────────────────────────────────────────────
    sections["ElmLne_m_Q_bus1"] = {
        "Line_110kV_Ring": TimeSeries(
            element_class="ElmLne", variable="m:Q:bus1",
            label="Lines – Reactive Power", unit="Mvar",
            values=_sine(18.0, 6.0, 1.0),
        ),
    }

    # ── ElmTerm / m:u  (for voltage heatmap) ────────────────────────────────
    sections["ElmTerm_m_u"] = {
        "SS_Residential_20kV": TimeSeries(
            element_class="ElmTerm", variable="m:u",
            label="Nodes – Voltage", unit="p.u.",
            values=_sine(0.890, 0.030, 0.0),
        ),
        "SS_West_110kV": TimeSeries(
            element_class="ElmTerm", variable="m:u",
            label="Nodes – Voltage", unit="p.u.",
            values=_sine(0.940, 0.020, 0.5),
        ),
        "SS_South_110kV": TimeSeries(
            element_class="ElmTerm", variable="m:u",
            label="Nodes – Voltage", unit="p.u.",
            values=_sine(0.980, 0.010, 1.0),
        ),
        "SS_North_110kV": TimeSeries(
            element_class="ElmTerm", variable="m:u",
            label="Nodes – Voltage", unit="p.u.",
            values=_sine(1.020, 0.020, 0.3),
        ),
        "SS_Commercial_20kV": TimeSeries(
            element_class="ElmTerm", variable="m:u",
            label="Nodes – Voltage", unit="p.u.",
            values=_sine(1.060, 0.010, 0.8),
        ),
        "SS_Central_110kV": TimeSeries(
            element_class="ElmTerm", variable="m:u",
            label="Nodes – Voltage", unit="p.u.",
            values=_sine(1.030, 0.015, 0.2),
        ),
    }

    return TimeSeriesData(time=_TIME, sections=sections)
