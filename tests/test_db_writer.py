"""Tests for PFTableWriter (db_writer.py) using mock PowerFactory objects."""
from __future__ import annotations

import math
import pytest

from pfreporting.config import PFReportConfig, VizRequest
from pfreporting.db_writer import (
    PFTableWriter,
    meta_table_name,
    table_name,
    _SUFFIX_DESC,
    _SUFFIX_SHORT_DESC,
    _SUFFIX_UNIT,
)
from pfreporting.models import TimeSeriesData


# ── Mock PowerFactory objects ──────────────────────────────────────────────────

class MockElmObj:
    def __init__(self, cls_name: str, loc_name: str) -> None:
        self._cls = cls_name
        self.loc_name = loc_name

    def GetClassName(self) -> str:
        return self._cls

    def GetDescription(self, mode: int = 0) -> str:
        return f"{self.loc_name}_desc_{'long' if mode == 0 else 'short'}"

    def GetUnit(self) -> str:
        return "%"


class MockElmRes:
    """Minimal ElmRes stub: 3 time steps, 4 columns (time + 3 elements)."""

    def __init__(self) -> None:
        self._objs = [
            None,                                 # col 0 = time (no object)
            MockElmObj("ElmLne", "Line_1"),       # col 1
            MockElmObj("ElmLne", "Line_2"),       # col 2
            MockElmObj("ElmTr2", "Trafo_1"),      # col 3
        ]
        self._vars = ["t", "c:loading", "c:loading", "c:loading"]
        self._data = [
            [0.0, 50.0, 80.0, 30.0],   # t=0
            [1.0, 60.0, 90.0, 35.0],   # t=1
            [2.0, 70.0, 95.0, 40.0],   # t=2
        ]

    def GetNumberOfRows(self) -> int:
        return len(self._data)

    def GetNumberOfColumns(self) -> int:
        return len(self._objs)

    def GetObject(self, col: int):
        return self._objs[col]

    def GetVariable(self, col: int) -> str:
        return self._vars[col]

    def FindColumn(self, name: str) -> int:
        if name in ("t", "time"):
            return 0
        return -1

    def GetValue(self, row: int, col: int):
        val = self._data[row][col]
        return None, val

    def GetDescription(self, col: int, mode: int = 0) -> str:
        obj = self._objs[col]
        return f"{obj.loc_name}_{'long' if mode == 0 else 'short'}" if obj else ""

    def GetUnit(self, col: int) -> str:
        return "%"

    def Load(self) -> None:
        pass

    def Release(self) -> None:
        pass


class MockReport:
    """In-memory IntReport stub that stores tables/fields/values."""

    def __init__(self) -> None:
        self.tables: dict[str, dict] = {}

    def Reset(self) -> None:
        self.tables.clear()

    def CreateTable(self, name: str) -> None:
        self.tables[name] = {"fields": [], "rows": {}}

    def CreateField(self, table: str, field: str, ftype: int) -> None:
        self.tables[table]["fields"].append(field)

    def SetValue(self, table: str, field: str, row: int, value) -> None:
        rows = self.tables[table]["rows"]
        if row not in rows:
            rows[row] = {}
        rows[row][field] = value

    def GetValue(self, table: str, field: str, row: int):
        try:
            return self.tables[table]["rows"][row][field]
        except KeyError:
            return None

    def GetNumberOfRows(self, table: str) -> int:
        if table not in self.tables:
            raise KeyError(table)
        rows = self.tables[table]["rows"]
        return max(rows.keys()) + 1 if rows else 0

    def GetFieldNames(self, table: str) -> list[str]:
        return self.tables[table]["fields"]


class MockApp:
    def IsNAN(self, val) -> bool:
        try:
            return math.isnan(float(val))
        except (TypeError, ValueError):
            return False

    def GetActiveStudyCase(self):
        return None

    def EchoOff(self) -> None:
        pass

    def EchoOn(self) -> None:
        pass


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def minimal_config() -> PFReportConfig:
    return PFReportConfig(
        visualizations=[
            VizRequest(
                element_class="ElmLne",
                variable="c:loading",
                label="Lines – Loading",
                unit="%",
                warn_hi=80.0,
                violation_hi=100.0,
            ),
            VizRequest(
                element_class="ElmTr2",
                variable="c:loading",
                label="Transformers – Loading",
                unit="%",
            ),
        ]
    )


@pytest.fixture
def writer(minimal_config) -> PFTableWriter:
    return PFTableWriter(MockApp(), minimal_config)


@pytest.fixture
def elmres() -> MockElmRes:
    return MockElmRes()


@pytest.fixture
def report() -> MockReport:
    return MockReport()


# ── table_name / meta_table_name helpers ──────────────────────────────────────

def test_table_name():
    assert table_name("ElmLne_c_loading") == "ElmLne_c_loading_TS"


def test_meta_table_name():
    assert meta_table_name("ElmLne_c_loading") == "ElmLne_c_loading_TS_Meta"


# ── write_all creates expected tables ─────────────────────────────────────────

def test_write_all_creates_tables(writer, report, elmres):
    ts_data = writer.write_all(report, elmres, clear_existing=True)

    vrs = writer._cfg.visualizations
    for vr in vrs:
        assert table_name(vr.chart_id) in report.tables
        assert meta_table_name(vr.chart_id) in report.tables


def test_write_all_returns_timeseries_data(writer, report, elmres):
    ts_data = writer.write_all(report, elmres)
    assert isinstance(ts_data, TimeSeriesData)


def test_write_all_correct_row_count(writer, report, elmres):
    writer.write_all(report, elmres)
    vr = writer._cfg.visualizations[0]
    tbl = table_name(vr.chart_id)
    assert report.GetNumberOfRows(tbl) == 3  # 3 time steps


def test_write_all_time_values(writer, report, elmres):
    writer.write_all(report, elmres)
    vr = writer._cfg.visualizations[0]
    tbl = table_name(vr.chart_id)
    assert report.GetValue(tbl, "time", 0) == pytest.approx(0.0)
    assert report.GetValue(tbl, "time", 1) == pytest.approx(1.0)
    assert report.GetValue(tbl, "time", 2) == pytest.approx(2.0)


def test_write_all_element_values(writer, report, elmres):
    ts_data = writer.write_all(report, elmres)
    vr = writer._cfg.visualizations[0]  # ElmLne c:loading
    tbl = table_name(vr.chart_id)
    # Line_1: 50.0, 60.0, 70.0
    assert report.GetValue(tbl, "Line_1", 0) == pytest.approx(50.0)
    assert report.GetValue(tbl, "Line_1", 2) == pytest.approx(70.0)
    # Line_2: 80.0, 90.0, 95.0
    assert report.GetValue(tbl, "Line_2", 1) == pytest.approx(90.0)


def test_write_all_meta_unit_stored(writer, report, elmres):
    writer.write_all(report, elmres)
    vr = writer._cfg.visualizations[0]
    tbl_meta = meta_table_name(vr.chart_id)
    unit_val = report.GetValue(tbl_meta, "Line_1" + _SUFFIX_UNIT, 0)
    assert unit_val is not None


def test_write_all_tr2_section(writer, report, elmres):
    ts_data = writer.write_all(report, elmres)
    vr = writer._cfg.visualizations[1]  # ElmTr2 c:loading
    assert vr.chart_id in ts_data.sections
    section = ts_data.sections[vr.chart_id]
    assert "Trafo_1" in section
    assert section["Trafo_1"].values[0] == pytest.approx(30.0)
    assert section["Trafo_1"].values[2] == pytest.approx(40.0)


# ── clear_existing=True resets report ─────────────────────────────────────────

def test_clear_existing_resets(writer, report, elmres):
    report.tables["stale_table"] = {}
    writer.write_all(report, elmres, clear_existing=True)
    assert "stale_table" not in report.tables


def test_no_clear_existing_keeps_tables(writer, report, elmres):
    report.tables["old_table"] = {}
    writer.write_all(report, elmres, clear_existing=False)
    assert "old_table" in report.tables


# ── TimeSeriesData returned directly ──────────────────────────────────────────

def test_returned_ts_data_time_vector(writer, report, elmres):
    ts_data = writer.write_all(report, elmres)
    assert ts_data.time == pytest.approx([0.0, 1.0, 2.0])


def test_returned_ts_data_series_values(writer, report, elmres):
    ts_data = writer.write_all(report, elmres)
    vr = writer._cfg.visualizations[0]
    section = ts_data.sections[vr.chart_id]
    assert section["Line_1"].values == pytest.approx([50.0, 60.0, 70.0])


def test_returned_ts_data_not_empty(writer, report, elmres):
    ts_data = writer.write_all(report, elmres)
    assert not ts_data.is_empty()


# ── max_elements cap ──────────────────────────────────────────────────────────

def test_max_elements_cap():
    config = PFReportConfig(
        visualizations=[
            VizRequest(
                element_class="ElmLne",
                variable="c:loading",
                label="Test",
                unit="%",
                max_elements=1,  # cap at 1 element
            )
        ]
    )
    writer = PFTableWriter(MockApp(), config)
    report = MockReport()
    elmres = MockElmRes()
    ts_data = writer.write_all(report, elmres)
    vr = config.visualizations[0]
    section = ts_data.sections[vr.chart_id]
    assert len(section) == 1  # only first element kept
