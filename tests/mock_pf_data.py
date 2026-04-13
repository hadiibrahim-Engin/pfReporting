"""
mock_pf_data.py — Fully realistic 1000-node, ~1200-branch mock network.

No PowerFactory installation needed.  Generates reproducible data with
random.seed(42) and populates the full DB schema identically to the real
PF extractor so the entire pipeline can be tested offline.

Public API:
    populate_mock_database(db_path: str | Path) -> None
"""

from __future__ import annotations
import math
import random
from pathlib import Path

from database.db_manager import DBManager
from database import db_writer as W


# ── Reproducibility ───────────────────────────────────────────────────────────
_SEED = 42


# ── Network size constants ────────────────────────────────────────────────────
N_HV   = 50    # 110 kV nodes
N_MV   = 350   # 20 kV nodes
N_LV   = 600   # 0.4 kV nodes

N_MV_LINES  = 600   # 20 kV lines
N_LV_CABLES = 400   # 0.4 kV cables
N_HV_TR     = 150   # 110/20 kV transformers
N_MV_TR     = 50    # 20/0.4 kV transformers

N_LOADS  = 850
N_GENS   = 47


# ── Log-normal / normal samplers ──────────────────────────────────────────────

def _lognormal(rng: random.Random, mu: float, sigma: float, lo: float, hi: float) -> float:
    """Sample from a log-normal distribution clipped to [lo, hi]."""
    val = rng.lognormvariate(math.log(mu) - sigma**2 / 2, sigma)
    return max(lo, min(hi, val))


def _normal(rng: random.Random, mu: float, sigma: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, rng.gauss(mu, sigma)))


# ── Main entry point ──────────────────────────────────────────────────────────

def populate_mock_database(db_path: str | Path | None = None) -> None:
    """
    Generate a fully realistic 1000-node mock network and write it to the DB.

    Runs the complete pipeline:
        nodes → branches → loads → generators → base loadflow →
        N-1 contingency loop (~1200 outages) → branch/node results
    """
    from config import DB_PATH
    db_path = Path(db_path or DB_PATH)

    rng = random.Random(_SEED)

    with DBManager(db_path) as db:
        node_ids    = _write_nodes(db, rng)
        branch_ids  = _write_branches(db, node_ids, rng)
        _write_loads(db, node_ids, rng)
        _write_generators(db, node_ids, rng)
        _write_base_loadflow(db, branch_ids, node_ids, rng)
        _run_n1_simulation(db, branch_ids, node_ids, rng)

    print(f"Mock database populated at {db_path}")
    print(f"  Nodes:     {len(node_ids)}")
    print(f"  Branches:  {len(branch_ids)}")
    print(f"  Outages:   {len(branch_ids)} contingencies")


# ── Nodes ─────────────────────────────────────────────────────────────────────

def _write_nodes(db: DBManager, rng: random.Random) -> dict[str, int]:
    rows = []

    for i in range(N_HV):
        rows.append({
            "name":       f"HV-Knoten-{i+1:03d}",
            "voltage_kv":  110.0,
            "node_type":   "busbar",
            "substation":  f"UW-HV-{(i // 5) + 1:02d}",
            "x_coord":     rng.uniform(6.0, 14.0),
            "y_coord":     rng.uniform(47.0, 55.0),
        })

    for i in range(N_MV):
        rows.append({
            "name":       f"MV-Knoten-{i+1:03d}",
            "voltage_kv":  20.0,
            "node_type":   "busbar",
            "substation":  f"UW-MV-{(i // 10) + 1:02d}",
            "x_coord":     rng.uniform(6.0, 14.0),
            "y_coord":     rng.uniform(47.0, 55.0),
        })

    for i in range(N_LV):
        rows.append({
            "name":       f"LV-Knoten-{i+1:03d}",
            "voltage_kv":  0.4,
            "node_type":   "junction",
            "substation":  None,
            "x_coord":     rng.uniform(6.0, 14.0),
            "y_coord":     rng.uniform(47.0, 55.0),
        })

    W.write_nodes(db, rows)
    id_map = W.get_node_id_map(db)
    return id_map


# ── Branches ──────────────────────────────────────────────────────────────────

def _write_branches(db: DBManager, node_ids: dict, rng: random.Random) -> dict[str, int]:
    rows      = []
    hv_names  = [n for n in node_ids if n.startswith("HV-")]
    mv_names  = [n for n in node_ids if n.startswith("MV-")]
    lv_names  = [n for n in node_ids if n.startswith("LV-")]

    # 20 kV lines
    for i in range(N_MV_LINES):
        a, b = rng.sample(mv_names, 2)
        rows.append({
            "name":        f"Ltg. M-{i+1:03d}",
            "from_node_id": node_ids[a],
            "to_node_id":   node_ids[b],
            "branch_type": "line",
            "length_km":    _normal(rng, 4.0, 2.5, 0.5, 15.0),
            "i_max_ka":     _normal(rng, 0.55, 0.12, 0.3, 0.8),
            "voltage_kv":   20.0,
            "sn_mva":       None,
        })

    # 0.4 kV cables
    for i in range(N_LV_CABLES):
        a, b = rng.sample(lv_names, 2)
        rows.append({
            "name":        f"Kab. L-{i+1:03d}",
            "from_node_id": node_ids[a],
            "to_node_id":   node_ids[b],
            "branch_type": "cable",
            "length_km":    _normal(rng, 0.4, 0.3, 0.05, 2.0),
            "i_max_ka":     _normal(rng, 0.35, 0.07, 0.2, 0.5),
            "voltage_kv":   0.4,
            "sn_mva":       None,
        })

    # 110/20 kV transformers
    for i in range(N_HV_TR):
        hv = rng.choice(hv_names)
        mv = rng.choice(mv_names)
        rows.append({
            "name":        f"Trafo T-{i+1:03d}",
            "from_node_id": node_ids[hv],
            "to_node_id":   node_ids[mv],
            "branch_type": "transformer",
            "length_km":    None,
            "i_max_ka":     None,
            "voltage_kv":   110.0,
            "sn_mva":       rng.choice([25.0, 40.0, 63.0]),
        })

    # 20/0.4 kV transformers
    for i in range(N_MV_TR):
        mv = rng.choice(mv_names)
        lv = rng.choice(lv_names)
        rows.append({
            "name":        f"Trafo TN-{i+1:03d}",
            "from_node_id": node_ids[mv],
            "to_node_id":   node_ids[lv],
            "branch_type": "transformer",
            "length_km":    None,
            "i_max_ka":     None,
            "voltage_kv":   20.0,
            "sn_mva":       rng.choice([0.25, 0.4, 0.63, 1.0]),
        })

    W.write_branches(db, rows)
    return W.get_branch_id_map(db)


# ── Loads ─────────────────────────────────────────────────────────────────────

def _write_loads(db: DBManager, node_ids: dict, rng: random.Random) -> None:
    node_list = list(node_ids.keys())
    rows = []
    for i in range(N_LOADS):
        node = rng.choice(node_list)
        p    = _lognormal(rng, 1.5, 0.8, 0.01, 20.0)
        rows.append({
            "name":    f"Last-{i+1:04d}",
            "node_id":  node_ids[node],
            "p_mw":     round(p, 3),
            "q_mvar":   round(p * rng.uniform(0.1, 0.4), 3),
        })
    W.write_loads(db, rows)


# ── Generators ────────────────────────────────────────────────────────────────

def _write_generators(db: DBManager, node_ids: dict, rng: random.Random) -> None:
    hv_mv = [n for n in node_ids if not n.startswith("LV-")]
    rows  = []
    types = ["sync", "pv", "wind", "slack"]
    for i in range(N_GENS):
        node = rng.choice(hv_mv)
        rows.append({
            "name":     f"Gen-{i+1:03d}",
            "node_id":   node_ids[node],
            "p_mw":      round(rng.uniform(5.0, 150.0), 1),
            "gen_type":  rng.choice(types),
        })
    W.write_generators(db, rows)


# ── Base load flow ─────────────────────────────────────────────────────────────

def _write_base_loadflow(
    db: DBManager,
    branch_ids: dict,
    node_ids: dict,
    rng: random.Random,
) -> None:
    rows = []
    for name, bid in branch_ids.items():
        loading = _lognormal(rng, 52.0, 0.35, 5.0, 95.0)  # log-normal ~N(52,18%)
        rows.append({"element_id": bid, "element_type": "branch", "loading_pct": round(loading, 2), "u_pu": None})

    for name, nid in node_ids.items():
        u = _normal(rng, 1.01, 0.012, 0.97, 1.04)
        rows.append({"element_id": nid, "element_type": "node", "loading_pct": None, "u_pu": round(u, 5)})

    W.write_base_loadflow(db, rows)


# ── N-1 simulation ────────────────────────────────────────────────────────────

def _run_n1_simulation(
    db: DBManager,
    branch_ids: dict,
    node_ids: dict,
    rng: random.Random,
) -> None:
    """
    Approximate N-1 without AC solver:
    - For each outage, scale neighbours' loadings by a log-normal factor.
    - Inject 4 % critical (>100 %) and 12 % warning (80–100 %) cases.
    """
    node_list   = list(node_ids.values())
    branch_list = list(branch_ids.items())   # (name, id)
    n_branches  = len(branch_list)

    for idx, (b_name, b_id) in enumerate(branch_list):
        # Determine severity bucket for this contingency
        roll = rng.random()
        if roll < 0.04:
            severity = "critical"
        elif roll < 0.16:
            severity = "warning"
        else:
            severity = "normal"

        # ── Persist contingency header ─────────────────────────────────────────
        cont_id = W.write_contingency(db, {
            "outage_element_id":   b_id,
            "outage_element_name": b_name,
            "n_level":             1,
            "outage_type":         _infer_type(b_name),
        })

        # ── Branch results for all other branches ──────────────────────────────
        br_rows = []
        for b2_name, b2_id in branch_list:
            if b2_id == b_id:
                continue   # the outaged element itself
            base = _lognormal(rng, 52.0, 0.35, 5.0, 95.0)
            factor = _contingency_factor(rng, severity, idx, n_branches)
            loading = min(base * factor, 200.0)
            br_rows.append({
                "contingency_id": cont_id,
                "branch_id":      b2_id,
                "loading_pct":    round(loading, 2),
                "i_ka":           round(loading * rng.uniform(0.004, 0.008), 4),
                "p_mw":           round(rng.uniform(1.0, 50.0), 2),
                "q_mvar":         round(rng.uniform(0.1, 15.0), 2),
            })

        W.write_branch_results(db, br_rows)

        # ── Node results (voltage deviation proportional to worst loading) ──────
        max_load = max((r["loading_pct"] for r in br_rows), default=0.0)
        nd_rows  = []
        for n_id in node_list:
            u_dev = _voltage_deviation(rng, max_load)
            u_pu  = round(max(0.85, min(1.15, 1.0 + u_dev)), 5)
            nd_rows.append({
                "contingency_id": cont_id,
                "node_id":        n_id,
                "u_pu":           u_pu,
                "u_kv":           None,
                "angle_deg":      round(rng.gauss(0, 5), 3),
            })
        W.write_node_results(db, nd_rows)

        if (idx + 1) % 200 == 0:
            print(f"  N-1 simulation: {idx + 1}/{n_branches} outages processed")


def _infer_type(name: str) -> str:
    name_lower = name.lower()
    if "trafo" in name_lower:
        return "transformer"
    if "kab" in name_lower:
        return "cable"
    return "line"


def _contingency_factor(rng: random.Random, severity: str, idx: int, total: int) -> float:
    """Return a loading multiplier based on the severity bucket."""
    if severity == "critical":
        # Factor that pushes loading above 100 %
        base = _lognormal(rng, 1.25, 0.20, 0.8, 2.5)
        return max(base, 100.0 / _lognormal(rng, 52.0, 0.35, 20.0, 80.0))
    if severity == "warning":
        return _lognormal(rng, 1.55, 0.15, 1.1, 2.0)
    return _lognormal(rng, 1.10, 0.18, 0.9, 1.8)


def _voltage_deviation(rng: random.Random, max_loading: float) -> float:
    """Small voltage deviation correlated with loading severity."""
    scale = max_loading / 100.0
    return rng.gauss(0, 0.015 * scale)
