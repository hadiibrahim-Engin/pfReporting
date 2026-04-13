"""
pf_extractor.py — Extract grid topology and base load-flow results
from a live PowerFactory project.

All extracted data is returned as lists of plain dicts matching the
database schema (column names as keys) so db_writer can insert them directly.
"""

from __future__ import annotations
import logging
from typing import Any

log = logging.getLogger(__name__)

# PowerFactory object class names
_CLS_NODE   = "ElmTerm"
_CLS_LINE   = "ElmLne"
_CLS_TR2    = "ElmTr2"
_CLS_LOAD   = "ElmLod"
_CLS_GEN    = "ElmSym"


# ── Safe attribute getter ──────────────────────────────────────────────────────

def _get(obj: Any, attr: str, default=None):
    """Safely read a PowerFactory object attribute."""
    try:
        val = obj.GetAttribute(attr)
        return val if val is not None else default
    except Exception:
        return default


# ── Nodes / busbars ───────────────────────────────────────────────────────────

def extract_nodes(app) -> list[dict]:
    """
    Extract all ElmTerm (busbars / nodes) from the calc-relevant network.

    Returns list of dicts matching the `nodes` table schema.
    """
    objects = app.GetCalcRelevantObjects(_CLS_NODE)
    log.info("Extracting %d nodes …", len(objects))

    rows = []
    for obj in objects:
        try:
            rows.append({
                "name":       obj.loc_name,
                "voltage_kv": _get(obj, "uknom",   0.0),   # nominal voltage kV
                "node_type":  _get(obj, "iUsage",  "busbar"),
                "substation": _parent_substation(obj),
                "x_coord":    _get(obj, "GPSlat",  None),
                "y_coord":    _get(obj, "GPSlon",  None),
            })
        except Exception as e:
            log.warning("Skipping node %s: %s", getattr(obj, "loc_name", "?"), e)
    return rows


# ── Lines / cables ────────────────────────────────────────────────────────────

def extract_lines(app) -> list[dict]:
    """Extract all ElmLne objects."""
    objects = app.GetCalcRelevantObjects(_CLS_LINE)
    log.info("Extracting %d lines/cables …", len(objects))

    rows = []
    for obj in objects:
        try:
            from_node = _get(obj, "bus1.cterm.loc_name", "")
            to_node   = _get(obj, "bus2.cterm.loc_name", "")
            rows.append({
                "name":        obj.loc_name,
                "from_node":   from_node,    # resolved to ID by db_writer
                "to_node":     to_node,
                "branch_type": "cable" if _get(obj, "inAir", 1) == 0 else "line",
                "length_km":   _get(obj, "dline",  0.0),
                "i_max_ka":    _get(obj, "Inom",   0.0),
                "voltage_kv":  _terminal_voltage(obj),
                "sn_mva":      None,
            })
        except Exception as e:
            log.warning("Skipping line %s: %s", getattr(obj, "loc_name", "?"), e)
    return rows


# ── Transformers ──────────────────────────────────────────────────────────────

def extract_transformers(app) -> list[dict]:
    """Extract all ElmTr2 (2-winding transformer) objects."""
    objects = app.GetCalcRelevantObjects(_CLS_TR2)
    log.info("Extracting %d transformers …", len(objects))

    rows = []
    for obj in objects:
        try:
            from_node = _get(obj, "bushv.cterm.loc_name", "")
            to_node   = _get(obj, "buslv.cterm.loc_name", "")
            rows.append({
                "name":        obj.loc_name,
                "from_node":   from_node,
                "to_node":     to_node,
                "branch_type": "transformer",
                "length_km":   None,
                "i_max_ka":    None,
                "voltage_kv":  _get(obj, "typ_id.utrn_h", 0.0),   # HV nominal kV
                "sn_mva":      _get(obj, "typ_id.strn",   0.0),   # rated power MVA
            })
        except Exception as e:
            log.warning("Skipping transformer %s: %s", getattr(obj, "loc_name", "?"), e)
    return rows


# ── Loads ─────────────────────────────────────────────────────────────────────

def extract_loads(app) -> list[dict]:
    """Extract all ElmLod objects."""
    objects = app.GetCalcRelevantObjects(_CLS_LOAD)
    log.info("Extracting %d loads …", len(objects))

    rows = []
    for obj in objects:
        try:
            rows.append({
                "name":     obj.loc_name,
                "node":     _get(obj, "bus1.cterm.loc_name", ""),
                "p_mw":     _get(obj, "plini", 0.0),
                "q_mvar":   _get(obj, "qlini", 0.0),
            })
        except Exception as e:
            log.warning("Skipping load %s: %s", getattr(obj, "loc_name", "?"), e)
    return rows


# ── Generators ────────────────────────────────────────────────────────────────

def extract_generators(app) -> list[dict]:
    """Extract all ElmSym (synchronous machine / generator) objects."""
    objects = app.GetCalcRelevantObjects(_CLS_GEN)
    log.info("Extracting %d generators …", len(objects))

    rows = []
    for obj in objects:
        try:
            rows.append({
                "name":     obj.loc_name,
                "node":     _get(obj, "bus1.cterm.loc_name", ""),
                "p_mw":     _get(obj, "pgini", 0.0),
                "gen_type": _gen_type(obj),
            })
        except Exception as e:
            log.warning("Skipping generator %s: %s", getattr(obj, "loc_name", "?"), e)
    return rows


# ── Base load-flow results ─────────────────────────────────────────────────────

def extract_base_loadflow(app) -> tuple[list[dict], list[dict]]:
    """
    Read branch loading % and node voltage from the current load-flow solution.
    Must call ComLdf before this.

    Returns (branch_results, node_results) as lists of dicts with
    keys matching base_loadflow schema (element_id resolved later).
    """
    branch_rows, node_rows = [], []

    for obj in app.GetCalcRelevantObjects(_CLS_LINE) + app.GetCalcRelevantObjects(_CLS_TR2):
        try:
            branch_rows.append({
                "element_name": obj.loc_name,
                "element_type": "branch",
                "loading_pct":  _get(obj, "c:loading", 0.0),
                "u_pu":         None,
            })
        except Exception:
            pass

    for obj in app.GetCalcRelevantObjects(_CLS_NODE):
        try:
            node_rows.append({
                "element_name": obj.loc_name,
                "element_type": "node",
                "loading_pct":  None,
                "u_pu":         _get(obj, "m:u", 1.0),
            })
        except Exception:
            pass

    return branch_rows, node_rows


# ── Private helpers ───────────────────────────────────────────────────────────

def _parent_substation(obj) -> str:
    try:
        parent = obj.GetParent()
        return parent.loc_name if parent else ""
    except Exception:
        return ""


def _terminal_voltage(obj) -> float:
    try:
        bus = obj.GetAttribute("bus1.cterm")
        return bus.uknom if bus else 0.0
    except Exception:
        return 0.0


def _gen_type(obj) -> str:
    itype = _get(obj, "ip_ctrl", 0)
    return {0: "sync", 1: "slack", 2: "pv"}.get(itype, "sync")
