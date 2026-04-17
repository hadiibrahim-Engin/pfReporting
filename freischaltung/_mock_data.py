"""Demo-Daten – entsprechen dem mitgelieferten report-template.html."""
from __future__ import annotations

import math

from freischaltung.models import (
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
from freischaltung.report.builder import ReportData

_STEPS = 25
_TIME  = [float(i) for i in range(_STEPS)]


def build_mock_data() -> ReportData:
    info = ProjectInfo(
        project="DEMO",
        study_case="Winterlast_2026",
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
        scenario="Winterlast_2026",
        study_time_start="01.01.2026 00:00",
    )

    switched = [
        SwitchedElement(name="Leitung_110kV_Nord", type="Leitung"),
        SwitchedElement(name="Trafo_UW_Mitte_T2",  type="Transformator (2W)"),
    ]

    # Steps 8 and 16 simulate non-convergence (all NaN in real PF – here None)
    non_conv = {8, 16}
    lf = LoadFlowResult(
        converged=True,
        status_text="Konvergiert",
        iterations=4,
        total_load_mw=245.80,
        total_gen_mw=252.30,
        losses_mw=6.50,
        qds_steps=[
            QDSStep(time_h=float(i), converged=(i not in non_conv))
            for i in range(_STEPS)
        ],
    )

    voltage = [
        VoltageResult(node="SS_Wohngebiet_20kV",  u_nenn_kv=20.0,  u_kv=17.80,  u_pu=0.8900, deviation_pct=-11.00, status="violation"),
        VoltageResult(node="SS_West_110kV",        u_nenn_kv=110.0, u_kv=103.40, u_pu=0.9400, deviation_pct=-6.00,  status="warning"),
        VoltageResult(node="SS_Krankenhaus_20kV",  u_nenn_kv=20.0,  u_kv=19.20,  u_pu=0.9600, deviation_pct=-4.00,  status="ok"),
        VoltageResult(node="SS_Industrie_20kV",    u_nenn_kv=20.0,  u_kv=19.40,  u_pu=0.9700, deviation_pct=-3.00,  status="ok"),
        VoltageResult(node="SS_Süd_110kV",         u_nenn_kv=110.0, u_kv=107.80, u_pu=0.9800, deviation_pct=-2.00,  status="ok"),
        VoltageResult(node="SS_Bahnhof_20kV",      u_nenn_kv=20.0,  u_kv=19.80,  u_pu=0.9900, deviation_pct=-1.00,  status="ok"),
        VoltageResult(node="SS_Ost_110kV",         u_nenn_kv=110.0, u_kv=111.10, u_pu=1.0100, deviation_pct=+1.00,  status="ok"),
        VoltageResult(node="SS_Schule_20kV",       u_nenn_kv=20.0,  u_kv=20.20,  u_pu=1.0100, deviation_pct=+1.00,  status="ok"),
        VoltageResult(node="SS_Nord_110kV",        u_nenn_kv=110.0, u_kv=112.20, u_pu=1.0200, deviation_pct=+2.00,  status="ok"),
        VoltageResult(node="SS_Mitte_110kV",       u_nenn_kv=110.0, u_kv=113.30, u_pu=1.0300, deviation_pct=+3.00,  status="ok"),
        VoltageResult(node="SS_Hafen_20kV",        u_nenn_kv=20.0,  u_kv=20.80,  u_pu=1.0400, deviation_pct=+4.00,  status="ok"),
        VoltageResult(node="SS_Gewerbe_20kV",      u_nenn_kv=20.0,  u_kv=21.20,  u_pu=1.0600, deviation_pct=+6.00,  status="warning"),
    ]

    loading = [
        LoadingResult(name="Leitung_110kV_Ring",  type="Leitung",           loading_pct=104.2, i_ka=0.590, i_nenn_ka=0.565, status="violation"),
        LoadingResult(name="Trafo_UW_Mitte_T1",   type="Transformator (2W)", loading_pct=91.5,  i_ka=0.0,   i_nenn_ka=0.0,   status="warning"),
        LoadingResult(name="Leitung_110kV_Ost",   type="Leitung",           loading_pct=82.5,  i_ka=0.470, i_nenn_ka=0.565, status="warning"),
        LoadingResult(name="Leitung_20kV_2",      type="Leitung",           loading_pct=71.8,  i_ka=0.290, i_nenn_ka=0.400, status="ok"),
        LoadingResult(name="Trafo_UW_Ost_T1",     type="Transformator (2W)", loading_pct=68.0,  i_ka=0.0,   i_nenn_ka=0.0,   status="ok"),
        LoadingResult(name="Leitung_110kV_Süd",   type="Leitung",           loading_pct=67.3,  i_ka=0.380, i_nenn_ka=0.565, status="ok"),
        LoadingResult(name="Trafo_UW_Süd_T1",     type="Transformator (2W)", loading_pct=55.2,  i_ka=0.0,   i_nenn_ka=0.0,   status="ok"),
        LoadingResult(name="Leitung_20kV_1",      type="Leitung",           loading_pct=45.1,  i_ka=0.180, i_nenn_ka=0.400, status="ok"),
        LoadingResult(name="Leitung_20kV_3",      type="Leitung",           loading_pct=23.4,  i_ka=0.090, i_nenn_ka=0.400, status="ok"),
    ]

    n1 = [
        N1Result(
            outage_element="Leitung_110kV_Ring", type="Leitung", converged=True,
            max_loading_pct=112.0, max_loading_element="Leitung_110kV_Ost",
            min_voltage_pu=0.8800, min_voltage_node="SS_Wohngebiet_20kV",
            max_voltage_pu=1.0600, max_voltage_node="SS_Nord_110kV",
            violations=["Überlastung: Leitung_110kV_Ost mit 112.0%", "Unterspannung: SS_Wohngebiet_20kV mit 0.88 p.u."],
            status="violation",
        ),
        N1Result(
            outage_element="Trafo_UW_Mitte_T1", type="Transformator (2W)", converged=False,
            max_loading_pct=0.0, max_loading_element="-",
            min_voltage_pu=0.0, min_voltage_node="-",
            max_voltage_pu=0.0, max_voltage_node="-",
            violations=["Lastfluss konvergiert nicht!"],
            status="violation",
        ),
        N1Result(
            outage_element="Leitung_110kV_Süd", type="Leitung", converged=True,
            max_loading_pct=88.3, max_loading_element="Leitung_110kV_Ring",
            min_voltage_pu=0.9600, min_voltage_node="SS_Süd_110kV",
            max_voltage_pu=1.0300, max_voltage_node="SS_Nord_110kV",
            violations=[], status="ok",
        ),
        N1Result(
            outage_element="Leitung_110kV_Ost", type="Leitung", converged=True,
            max_loading_pct=95.1, max_loading_element="Leitung_110kV_Ring",
            min_voltage_pu=0.9400, min_voltage_node="SS_Ost_110kV",
            max_voltage_pu=1.0400, max_voltage_node="SS_Mitte_110kV",
            violations=[], status="ok",
        ),
        N1Result(
            outage_element="Leitung_20kV_1", type="Leitung", converged=True,
            max_loading_pct=72.0, max_loading_element="Leitung_20kV_2",
            min_voltage_pu=0.9700, min_voltage_node="SS_Industrie_20kV",
            max_voltage_pu=1.0200, max_voltage_node="SS_Mitte_110kV",
            violations=[], status="ok",
        ),
        N1Result(
            outage_element="Leitung_20kV_2", type="Leitung", converged=True,
            max_loading_pct=81.0, max_loading_element="Leitung_20kV_1",
            min_voltage_pu=0.9500, min_voltage_node="SS_Gewerbe_20kV",
            max_voltage_pu=1.0300, max_voltage_node="SS_Mitte_110kV",
            violations=[], status="ok",
        ),
        N1Result(
            outage_element="Trafo_UW_Süd_T1", type="Transformator (2W)", converged=True,
            max_loading_pct=78.5, max_loading_element="Trafo_UW_Ost_T1",
            min_voltage_pu=0.9300, min_voltage_node="SS_Hafen_20kV",
            max_voltage_pu=1.0500, max_voltage_node="SS_Süd_110kV",
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
            "Die Freischaltung ist <strong>NICHT zulässig</strong>. "
            "Es liegen Verletzungen der Systemsicherheit vor.<br>"
            " – 1 Spannungsbandverletzung(en)<br>"
            " – 1 thermische Überlastung(en)<br>"
            " – 2 (N-1)-Sicherheitsverletzung(en)"
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
    """Erzeugt realistische Sinuskurven als Demo-Zeitreihen (24 h, 1 h-Schritte)."""
    sections: dict = {}

    # ── ElmLne / c:loading ──────────────────────────────────────────────────
    sections["ElmLne_c_loading"] = {
        "Leitung_110kV_Ring": TimeSeries(
            element_class="ElmLne", variable="c:loading",
            label="Leitungen – Auslastung", unit="%",
            values=_sine(95.0, 15.0, 0.0),
        ),
        "Leitung_110kV_Ost": TimeSeries(
            element_class="ElmLne", variable="c:loading",
            label="Leitungen – Auslastung", unit="%",
            values=_sine(75.0, 12.0, 0.5),
        ),
        "Leitung_110kV_Süd": TimeSeries(
            element_class="ElmLne", variable="c:loading",
            label="Leitungen – Auslastung", unit="%",
            values=_sine(60.0, 8.0, 1.0),
        ),
    }

    # ── ElmTr2 / c:loading ──────────────────────────────────────────────────
    sections["ElmTr2_c_loading"] = {
        "Trafo_UW_Mitte_T1": TimeSeries(
            element_class="ElmTr2", variable="c:loading",
            label="Transformatoren – Auslastung", unit="%",
            values=_sine(85.0, 10.0, 0.3),
        ),
    }

    # ── ElmLne / m:i1:bus1 ──────────────────────────────────────────────────
    sections["ElmLne_m_i1_bus1"] = {
        "Leitung_110kV_Ring": TimeSeries(
            element_class="ElmLne", variable="m:i1:bus1",
            label="Leitungen – Strom", unit="kA",
            values=_sine(0.48, 0.12, 0.0),
        ),
        "Leitung_110kV_Ost": TimeSeries(
            element_class="ElmLne", variable="m:i1:bus1",
            label="Leitungen – Strom", unit="kA",
            values=_sine(0.40, 0.08, 0.5),
        ),
    }

    # ── ElmLne / m:P:bus1 ───────────────────────────────────────────────────
    sections["ElmLne_m_P_bus1"] = {
        "Leitung_110kV_Ring": TimeSeries(
            element_class="ElmLne", variable="m:P:bus1",
            label="Leitungen – Wirkleistung", unit="MW",
            values=_sine(85.0, 20.0, 0.0),
        ),
        "Leitung_110kV_Ost": TimeSeries(
            element_class="ElmLne", variable="m:P:bus1",
            label="Leitungen – Wirkleistung", unit="MW",
            values=_sine(65.0, 15.0, 0.5),
        ),
    }

    # ── ElmLne / m:Q:bus1 ───────────────────────────────────────────────────
    sections["ElmLne_m_Q_bus1"] = {
        "Leitung_110kV_Ring": TimeSeries(
            element_class="ElmLne", variable="m:Q:bus1",
            label="Leitungen – Blindleistung", unit="Mvar",
            values=_sine(18.0, 6.0, 1.0),
        ),
    }

    # ── ElmTerm / m:u  (für Spannungs-Heatmap) ──────────────────────────────
    sections["ElmTerm_m_u"] = {
        "SS_Wohngebiet_20kV": TimeSeries(
            element_class="ElmTerm", variable="m:u",
            label="Knoten – Spannung", unit="p.u.",
            values=_sine(0.890, 0.030, 0.0),
        ),
        "SS_West_110kV": TimeSeries(
            element_class="ElmTerm", variable="m:u",
            label="Knoten – Spannung", unit="p.u.",
            values=_sine(0.940, 0.020, 0.5),
        ),
        "SS_Süd_110kV": TimeSeries(
            element_class="ElmTerm", variable="m:u",
            label="Knoten – Spannung", unit="p.u.",
            values=_sine(0.980, 0.010, 1.0),
        ),
        "SS_Nord_110kV": TimeSeries(
            element_class="ElmTerm", variable="m:u",
            label="Knoten – Spannung", unit="p.u.",
            values=_sine(1.020, 0.020, 0.3),
        ),
        "SS_Gewerbe_20kV": TimeSeries(
            element_class="ElmTerm", variable="m:u",
            label="Knoten – Spannung", unit="p.u.",
            values=_sine(1.060, 0.010, 0.8),
        ),
        "SS_Mitte_110kV": TimeSeries(
            element_class="ElmTerm", variable="m:u",
            label="Knoten – Spannung", unit="p.u.",
            values=_sine(1.030, 0.015, 0.2),
        ),
    }

    return TimeSeriesData(time=_TIME, sections=sections)
