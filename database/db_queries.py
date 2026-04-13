"""
db_queries.py — All read queries used by the analysis and reporting layers.

Every function takes a DBManager instance and returns plain Python dicts
(converted from sqlite3.Row) so the callers have no DB dependency.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

import config

if TYPE_CHECKING:
    from database.db_manager import DBManager


def _rows(db: "DBManager", sql: str, params=()) -> list[dict]:
    return [dict(r) for r in db.fetchall(sql, params)]


# ── Topology ──────────────────────────────────────────────────────────────────

def get_all_nodes(db: "DBManager") -> list[dict]:
    return _rows(db, "SELECT * FROM nodes ORDER BY voltage_kv DESC, name")


def get_all_branches(db: "DBManager") -> list[dict]:
    return _rows(db, "SELECT * FROM branches ORDER BY voltage_kv DESC, name")


# ── KPI summary ───────────────────────────────────────────────────────────────

def get_kpi_summary(db: "DBManager") -> dict:
    """Single aggregated query returning all top-level KPI values."""
    row = db.fetchone("""
        SELECT
            COUNT(DISTINCT c.id)                                    AS total_contingencies,
            COUNT(DISTINCT CASE WHEN br.loading_pct > 100 THEN c.id END) AS critical_contingencies,
            COUNT(CASE WHEN br.loading_pct > 100 THEN 1 END)        AS critical_violations,
            COUNT(CASE WHEN br.loading_pct BETWEEN 80 AND 100 THEN 1 END) AS warning_violations,
            MAX(br.loading_pct)                                     AS max_loading_pct
        FROM contingencies c
        JOIN branch_results br ON br.contingency_id = c.id
    """)
    kpi = dict(row) if row else {}

    # Max loading element name
    max_row = db.fetchone("""
        SELECT b.name
        FROM branch_results br
        JOIN branches b ON b.id = br.branch_id
        ORDER BY br.loading_pct DESC
        LIMIT 1
    """)
    kpi["max_loading_element"] = max_row["name"] if max_row else "—"

    # Voltage violations
    v_row = db.fetchone("""
        SELECT COUNT(*) AS cnt
        FROM node_results
        WHERE u_pu < :lo OR u_pu > :hi
    """, {"lo": config.VOLTAGE_MIN_PU, "hi": config.VOLTAGE_MAX_PU})
    kpi["voltage_violations"] = v_row["cnt"] if v_row else 0

    # Affected nodes
    na_row = db.fetchone("""
        SELECT COUNT(DISTINCT node_id) AS cnt
        FROM node_results
        WHERE u_pu < :lo OR u_pu > :hi
    """, {"lo": config.VOLTAGE_MIN_PU, "hi": config.VOLTAGE_MAX_PU})
    kpi["affected_nodes"] = na_row["cnt"] if na_row else 0

    # N-1 compliance rate (contingencies with NO critical branch violation)
    ok_row = db.fetchone("""
        SELECT COUNT(DISTINCT c.id) AS ok_cnt
        FROM contingencies c
        WHERE NOT EXISTS (
            SELECT 1 FROM branch_results br
            WHERE br.contingency_id = c.id
              AND br.loading_pct > :threshold
        )
    """, {"threshold": config.LOADING_CRITICAL_PCT})
    total = kpi.get("total_contingencies", 0)
    ok    = ok_row["ok_cnt"] if ok_row else 0
    kpi["n1_compliance_rate_pct"] = round(ok / total * 100, 1) if total else 0.0

    return kpi


# ── Violations ────────────────────────────────────────────────────────────────

def get_loading_violations(db: "DBManager", threshold: float = None) -> list[dict]:
    threshold = threshold or config.LOADING_WARNING_PCT
    return _rows(db, """
        SELECT
            b.name       AS branch_name,
            c.outage_element_name AS contingency_name,
            b.voltage_kv,
            br.loading_pct,
            br.i_ka,
            br.p_mw,
            br.q_mvar,
            CASE WHEN br.loading_pct > 100 THEN 'Kritisch' ELSE 'Warnung' END AS severity
        FROM branch_results br
        JOIN branches      b ON b.id = br.branch_id
        JOIN contingencies c ON c.id = br.contingency_id
        WHERE br.loading_pct >= :threshold
        ORDER BY br.loading_pct DESC
    """, {"threshold": threshold})


def get_voltage_violations(
    db: "DBManager",
    u_min: float = None,
    u_max: float = None,
) -> list[dict]:
    u_min = u_min or config.VOLTAGE_MIN_PU
    u_max = u_max or config.VOLTAGE_MAX_PU
    return _rows(db, """
        SELECT
            n.name       AS node_name,
            c.outage_element_name AS contingency_name,
            n.voltage_kv,
            nr.u_pu,
            nr.u_kv,
            ROUND((nr.u_pu - 1.0) * 100, 2) AS deviation_pct,
            CASE WHEN nr.u_pu < :lo THEN 'Unterspannung' ELSE 'Überspannung' END AS type,
            CASE WHEN ABS(nr.u_pu - 1.0) > 0.07 THEN 'Kritisch' ELSE 'Warnung' END AS severity
        FROM node_results   nr
        JOIN nodes          n  ON n.id  = nr.node_id
        JOIN contingencies  c  ON c.id  = nr.contingency_id
        WHERE nr.u_pu < :lo OR nr.u_pu > :hi
        ORDER BY ABS(nr.u_pu - 1.0) DESC
    """, {"lo": u_min, "hi": u_max})


# ── Top-N contingencies ───────────────────────────────────────────────────────

def get_top_n_contingencies(db: "DBManager", n: int = None) -> list[dict]:
    n = n or config.TOP_N_CONTINGENCIES
    return _rows(db, """
        SELECT
            c.id,
            c.outage_element_name AS contingency_name,
            c.outage_element_name AS outage_element,
            c.outage_type,
            b_out.voltage_kv,
            MAX(br.loading_pct)  AS max_loading_pct,
            COUNT(DISTINCT CASE WHEN br.loading_pct > :warn THEN br.branch_id END) AS affected_branches,
            COUNT(DISTINCT CASE WHEN nr.u_pu < :lo OR nr.u_pu > :hi THEN nr.node_id END) AS affected_nodes,
            CASE
                WHEN MAX(br.loading_pct) > 100 THEN 'Kritisch'
                WHEN MAX(br.loading_pct) > 80  THEN 'Warnung'
                ELSE 'OK'
            END AS severity_label
        FROM contingencies c
        JOIN branch_results br  ON br.contingency_id = c.id
        JOIN branches b_out      ON b_out.id = c.outage_element_id
        LEFT JOIN node_results nr ON nr.contingency_id = c.id
        GROUP BY c.id
        ORDER BY max_loading_pct DESC
        LIMIT :n
    """, {
        "warn": config.LOADING_WARNING_PCT,
        "lo":   config.VOLTAGE_MIN_PU,
        "hi":   config.VOLTAGE_MAX_PU,
        "n":    n,
    })


# ── Critical elements ─────────────────────────────────────────────────────────

def get_critical_elements(db: "DBManager") -> list[dict]:
    """Elements that appear most frequently in violations, with max loading."""
    return _rows(db, """
        SELECT
            b.name       AS element_name,
            b.branch_type AS element_type,
            b.voltage_kv,
            COUNT(*)     AS frequency,
            MAX(br.loading_pct) AS max_loading_pct,
            CASE
                WHEN MAX(br.loading_pct) > 100 THEN 1
                WHEN MAX(br.loading_pct) > 80  THEN 2
                ELSE 3
            END AS priority
        FROM branch_results br
        JOIN branches b ON b.id = br.branch_id
        WHERE br.loading_pct >= :threshold
        GROUP BY br.branch_id
        ORDER BY frequency DESC, max_loading_pct DESC
        LIMIT 15
    """, {"threshold": config.LOADING_WARNING_PCT})


# ── Full appendix ─────────────────────────────────────────────────────────────

def get_full_contingency_list(db: "DBManager") -> list[dict]:
    """All contingencies with their worst-case results — for the appendix."""
    return _rows(db, """
        SELECT
            c.outage_element_name AS contingency_name,
            c.outage_element_name AS outage_element,
            c.outage_type,
            COALESCE(MAX(br.loading_pct), 0) AS max_loading_pct,
            COUNT(DISTINCT CASE WHEN nr.u_pu < :lo OR nr.u_pu > :hi THEN nr.node_id END) AS voltage_violations,
            CASE
                WHEN MAX(br.loading_pct) > 100 THEN 'Kritisch'
                WHEN MAX(br.loading_pct) > 80  THEN 'Warnung'
                ELSE 'OK'
            END AS status
        FROM contingencies c
        LEFT JOIN branch_results br ON br.contingency_id = c.id
        LEFT JOIN node_results   nr ON nr.contingency_id = c.id
        GROUP BY c.id
        ORDER BY max_loading_pct DESC
    """, {"lo": config.VOLTAGE_MIN_PU, "hi": config.VOLTAGE_MAX_PU})
