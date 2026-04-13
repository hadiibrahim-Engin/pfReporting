"""
db_writer.py — Bulk-insert extracted PowerFactory data into the SQLite DB.

All functions accept a DBManager instance (already inside a 'with' block)
and a list of dicts matching the schema column names.
Upsert logic (INSERT OR REPLACE) ensures re-runs are idempotent.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

import config

if TYPE_CHECKING:
    from database.db_manager import DBManager


# ── Helpers ───────────────────────────────────────────────────────────────────

def _bulk_insert(db: "DBManager", sql: str, rows: list[dict]) -> None:
    """Execute INSERT OR REPLACE in batches for performance."""
    if not rows:
        return
    batch = config.DB_BATCH_SIZE
    for i in range(0, len(rows), batch):
        db.executemany(sql, rows[i : i + batch])
        db.commit()


# ── Topology ──────────────────────────────────────────────────────────────────

def write_nodes(db: "DBManager", nodes: list[dict]) -> None:
    """
    nodes: list of {name, voltage_kv, node_type, substation, x_coord, y_coord}
    """
    sql = """
        INSERT OR REPLACE INTO nodes (name, voltage_kv, node_type, substation, x_coord, y_coord)
        VALUES (:name, :voltage_kv, :node_type, :substation, :x_coord, :y_coord)
    """
    _bulk_insert(db, sql, nodes)


def write_branches(db: "DBManager", branches: list[dict]) -> None:
    """
    branches: list of {name, from_node_id, to_node_id, branch_type,
                        length_km, i_max_ka, voltage_kv, sn_mva}
    from_node_id / to_node_id must be resolved before calling (use get_node_id_map).
    """
    sql = """
        INSERT OR REPLACE INTO branches
            (name, from_node_id, to_node_id, branch_type, length_km, i_max_ka, voltage_kv, sn_mva)
        VALUES (:name, :from_node_id, :to_node_id, :branch_type, :length_km, :i_max_ka, :voltage_kv, :sn_mva)
    """
    _bulk_insert(db, sql, branches)


def write_loads(db: "DBManager", loads: list[dict]) -> None:
    """loads: list of {name, node_id, p_mw, q_mvar}"""
    sql = """
        INSERT OR REPLACE INTO loads (name, node_id, p_mw, q_mvar)
        VALUES (:name, :node_id, :p_mw, :q_mvar)
    """
    _bulk_insert(db, sql, loads)


def write_generators(db: "DBManager", generators: list[dict]) -> None:
    """generators: list of {name, node_id, p_mw, gen_type}"""
    sql = """
        INSERT OR REPLACE INTO generators (name, node_id, p_mw, gen_type)
        VALUES (:name, :node_id, :p_mw, :gen_type)
    """
    _bulk_insert(db, sql, generators)


# ── Base load flow ─────────────────────────────────────────────────────────────

def write_base_loadflow(db: "DBManager", results: list[dict]) -> None:
    """
    results: list of {element_id, element_type, loading_pct, u_pu}
    element_type: 'branch' or 'node'
    """
    sql = """
        INSERT OR REPLACE INTO base_loadflow (element_id, element_type, loading_pct, u_pu)
        VALUES (:element_id, :element_type, :loading_pct, :u_pu)
    """
    _bulk_insert(db, sql, results)


# ── Contingency results ───────────────────────────────────────────────────────

def write_contingency(db: "DBManager", contingency: dict) -> int:
    """
    contingency: {outage_element_id, outage_element_name, n_level, outage_type}
    Returns the new contingency row id.
    """
    cursor = db.execute("""
        INSERT INTO contingencies (outage_element_id, outage_element_name, n_level, outage_type)
        VALUES (:outage_element_id, :outage_element_name, :n_level, :outage_type)
    """, contingency)
    db.commit()
    return cursor.lastrowid


def write_branch_results(db: "DBManager", results: list[dict]) -> None:
    """
    results: list of {contingency_id, branch_id, loading_pct, i_ka, p_mw, q_mvar}
    """
    sql = """
        INSERT OR REPLACE INTO branch_results
            (contingency_id, branch_id, loading_pct, i_ka, p_mw, q_mvar)
        VALUES (:contingency_id, :branch_id, :loading_pct, :i_ka, :p_mw, :q_mvar)
    """
    _bulk_insert(db, sql, results)


def write_node_results(db: "DBManager", results: list[dict]) -> None:
    """
    results: list of {contingency_id, node_id, u_pu, u_kv, angle_deg}
    """
    sql = """
        INSERT OR REPLACE INTO node_results
            (contingency_id, node_id, u_pu, u_kv, angle_deg)
        VALUES (:contingency_id, :node_id, :u_pu, :u_kv, :angle_deg)
    """
    _bulk_insert(db, sql, results)


# ── Utility ───────────────────────────────────────────────────────────────────

def get_node_id_map(db: "DBManager") -> dict[str, int]:
    """Return {node_name: node_id} for FK resolution."""
    rows = db.fetchall("SELECT id, name FROM nodes")
    return {r["name"]: r["id"] for r in rows}


def get_branch_id_map(db: "DBManager") -> dict[str, int]:
    """Return {branch_name: branch_id} for FK resolution."""
    rows = db.fetchall("SELECT id, name FROM branches")
    return {r["name"]: r["id"] for r in rows}
