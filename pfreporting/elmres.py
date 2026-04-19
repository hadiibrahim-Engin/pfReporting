"""Shared PowerFactory ElmRes access helper.

Both reader.py and db_writer.py used to duplicate the same GetValue /
find_time_col / get_unit try/except patterns.  This module centralises them
and adds an opportunistic batch-read path (PF 2020+ GetColumnVectorDouble)
that collapses nrows COM calls per column into a single one.
"""
from __future__ import annotations

from typing import Any


class ElmResHelper:
    """Wraps a *loaded* PF ElmRes object with safe, efficient column reads."""

    def __init__(self, app: Any, elmres: Any) -> None:
        self._app = app
        self._res = elmres

    # -- Dimensions ----------------------------------------------------------

    @property
    def nrows(self) -> int:
        return int(self._res.GetNumberOfRows())

    @property
    def ncols(self) -> int:
        return int(self._res.GetNumberOfColumns())

    # -- Column discovery ----------------------------------------------------

    def find_time_col(self) -> int:
        """Return the index of the simulation-time column (0 as fallback)."""
        for name in ("t", "time", "Time", "TIME"):
            try:
                idx = self._res.FindColumn(name)
                if isinstance(idx, int) and idx >= 0:
                    return idx
            except Exception:
                pass
        return 0

    def get_object(self, col: int) -> Any | None:
        try:
            return self._res.GetObject(col)
        except Exception:
            return None

    def get_variable(self, col: int) -> str:
        try:
            return self._res.GetVariable(col) or ""
        except Exception:
            return ""

    def get_unit(self, col: int) -> str:
        try:
            return self._res.GetUnit(col) or ""
        except Exception:
            return ""

    def get_description(self, col: int, form: int = 0) -> str:
        try:
            return str(self._res.GetDescription(col, form) or "")
        except Exception:
            return ""

    # -- Data reads ----------------------------------------------------------

    def get_column(self, col: int) -> list[float | None]:
        """Read all row values for one column.

        Tries the PF 2020+ ``GetColumnVectorDouble`` batch API first which
        costs a single COM round-trip.  Falls back to row-by-row
        ``GetValue`` calls for older installations.
        """
        try:
            vals = self._res.GetColumnVectorDouble(col)
            if vals is not None:
                is_nan = self._app.IsNAN
                return [
                    None if v is None or is_nan(v) else float(v)
                    for v in vals
                ]
        except Exception:
            pass
        return [self._cell(row, col) for row in range(self.nrows)]

    def _cell(self, row: int, col: int) -> float | None:
        try:
            _, val = self._res.GetValue(row, col)
            if val is not None and self._app.IsNAN(val):
                return None
            return float(val) if val is not None else None
        except Exception:
            return None

    # -- Column index --------------------------------------------------------

    def build_column_index(
        self,
    ) -> dict[tuple[str, str], list[tuple[str, int, Any]]]:
        """Return a mapping of ``(element_class, variable) → [(name, col, obj)]``.

        Iterates all columns once and groups them by their PF class + variable
        combination.  Names are deduplicated with ``_2``, ``_3`` suffixes.
        """
        from pfreporting.utils import sanitize_name

        index: dict[tuple[str, str], list] = {}
        seen: dict[tuple[str, str], set[str]] = {}

        for col in range(self.ncols):
            obj = self.get_object(col)
            if obj is None:
                continue
            try:
                cls_name: str = obj.GetClassName()
            except Exception:
                continue
            var = self.get_variable(col)
            key = (cls_name, var)

            if key not in index:
                index[key] = []
                seen[key] = set()

            try:
                base = getattr(obj, "loc_name", None) or f"{cls_name}_{col}"
            except Exception:
                base = f"{cls_name}_{col}"

            col_name = sanitize_name(base)
            k = 2
            while col_name in seen[key]:
                col_name = f"{sanitize_name(base)}_{k}"
                k += 1
            seen[key].add(col_name)
            index[key].append((col_name, col, obj))

        return index
