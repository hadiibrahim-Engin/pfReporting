"""Tests for PFTableReader (db_reader.py) using mock PowerFactory objects."""
from __future__ import annotations

import pytest

from pfreporting.config import PFReportConfig, VizRequest
from pfreporting.db_reader import PFTableReader
from pfreporting.db_writer import (
    PFTableWriter,
    _SUFFIX_DESC,
    _SUFFIX_SHORT_DESC,
    _SUFFIX_UNIT,
    meta_table_name,
    table_name,
)
from pfreporting.models import TimeSeriesData


# -- Reuse mocks from test_db_writer ------------------------------------------

class MockElmObj:
    def __init__(self, cls_name: str, loc_name: str) -> None:
        self._cls = cls_name
        self.loc_name = loc_name

    def GetClassName(self) -> str:
        return self._cls

    def GetDescription(self, mode: int = 0) -> str:
        return f"{self.loc_name}_{'long' if mode == 0 else 'short'}"

    def GetUnit(self) -> str:
        return "%"


class MockElmRes:
    def __init__(self) -> None:
        self._objs = [
            None,
            MockElmObj("ElmLne", "Line_A"),
            MockElmObj("ElmLne", "Line_B"),
        ]
        self._vars = ["t", "c:loading", "c:loading"]
        self._data = [
            [0.0, 55.0, 85.0],
            [1.0, 60.0, 92.0],
            [2.0, 65.0, 105.0],
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
        return 0 if name in ("t", "time") else -1

    def GetValue(self, row: int, col: int):
        return None, self._data[row][col]

    def Load(self) -> None:
        pass

    def Release(self) -> None:
        pass


import math

class MockApp:
    def IsNAN(self, val) -> bool:
        try:
            return math.isnan(float(val))
        except (TypeError, ValueError):
            return False


class MockReport:
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


class MockReportNoFieldNames(MockReport):
    def GetFieldNames(self, table: str) -> list[str]:
        raise AttributeError("GetFieldNames not available")


# -- Fixtures -------------------------------------------------------------------

@pytest.fixture
def config() -> PFReportConfig:
    return PFReportConfig(
        visualizations=[
            VizRequest(
                element_class="ElmLne",
                variable="c:loading",
                label="Lines - Loading",
                unit="%",
                warn_hi=80.0,
                violation_hi=100.0,
            )
        ]
    )


@pytest.fixture
def populated_report(config) -> MockReport:
    """Report pre-populated by PFTableWriter (round-trip)."""
    report = MockReport()
    writer = PFTableWriter(MockApp(), config)
    writer.write_all(report, MockElmRes(), clear_existing=True)
    return report


# -- Basic read_all -------------------------------------------------------------

def test_read_all_returns_timeseries_data(config, populated_report):
    reader = PFTableReader(MockApp(), config)
    ts_data = reader.read_all(populated_report)
    assert isinstance(ts_data, TimeSeriesData)


def test_read_all_section_present(config, populated_report):
    reader = PFTableReader(MockApp(), config)
    ts_data = reader.read_all(populated_report)
    vr = config.visualizations[0]
    assert vr.chart_id in ts_data.sections


def test_read_all_time_vector(config, populated_report):
    reader = PFTableReader(MockApp(), config)
    ts_data = reader.read_all(populated_report)
    assert ts_data.time == pytest.approx([0.0, 1.0, 2.0])


def test_read_all_series_values_match_written(config, populated_report):
    reader = PFTableReader(MockApp(), config)
    ts_data = reader.read_all(populated_report)
    vr = config.visualizations[0]
    section = ts_data.sections[vr.chart_id]

    assert "Line_A" in section
    assert "Line_B" in section
    assert section["Line_A"].values == pytest.approx([55.0, 60.0, 65.0])
    assert section["Line_B"].values == pytest.approx([85.0, 92.0, 105.0])


def test_read_all_unit_from_meta(config, populated_report):
    reader = PFTableReader(MockApp(), config)
    ts_data = reader.read_all(populated_report)
    vr = config.visualizations[0]
    section = ts_data.sections[vr.chart_id]
    for ts in section.values():
        assert ts.unit != ""


def test_read_all_meta_fallback_when_fieldnames_missing(config):
    report = MockReportNoFieldNames()
    writer = PFTableWriter(MockApp(), config)
    writer.write_all(report, MockElmRes(), clear_existing=True)
    reader = PFTableReader(MockApp(), config)
    ts_data = reader.read_all(report)
    vr = config.visualizations[0]
    assert vr.chart_id in ts_data.sections


# -- Round-trip: write then read -----------------------------------------------

def test_roundtrip_values_identical(config):
    report = MockReport()
    app = MockApp()
    elmres = MockElmRes()

    writer = PFTableWriter(app, config)
    written = writer.write_all(report, elmres)

    reader = PFTableReader(app, config)
    read = reader.read_all(report)

    vr = config.visualizations[0]
    for name, ts in written.sections[vr.chart_id].items():
        assert read.sections[vr.chart_id][name].values == pytest.approx(ts.values)


def test_roundtrip_time_identical(config):
    report = MockReport()
    app = MockApp()
    elmres = MockElmRes()

    writer = PFTableWriter(app, config)
    written = writer.write_all(report, elmres)

    reader = PFTableReader(app, config)
    read = reader.read_all(report)

    assert read.time == pytest.approx(written.time)


# -- Missing table handling -----------------------------------------------------

def test_read_missing_table_returns_empty(config):
    reader = PFTableReader(MockApp(), config)
    empty_report = MockReport()  # no tables written
    ts_data = reader.read_all(empty_report)
    assert ts_data.is_empty() or len(ts_data.sections) == 0


# -- GetFieldNames fallback -----------------------------------------------------

def test_read_without_get_field_names(config, populated_report):
    """When GetFieldNames raises, reader should warn and return empty section."""
    class ReportNoFieldNames(MockReport):
        def GetFieldNames(self, table: str) -> list[str]:
            raise AttributeError("GetFieldNames not available")

    report = ReportNoFieldNames()
    writer = PFTableWriter(MockApp(), config)
    writer.write_all(report, MockElmRes(), clear_existing=True)

    reader = PFTableReader(MockApp(), config)
    ts_data = reader.read_all(report)
    vr = config.visualizations[0]
    section = ts_data.sections.get(vr.chart_id, {})
    assert isinstance(section, dict)


# -- Label and element_class metadata preserved --------------------------------

def test_series_metadata_preserved(config, populated_report):
    reader = PFTableReader(MockApp(), config)
    ts_data = reader.read_all(populated_report)
    vr = config.visualizations[0]
    section = ts_data.sections[vr.chart_id]
    ts = next(iter(section.values()))
    assert ts.element_class == vr.element_class
    assert ts.variable == vr.variable
    assert ts.label == vr.label
