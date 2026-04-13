"""
pf_contingency_runner.py — Run N-1 (or N-k) contingency studies via
the PowerFactory Python API and collect per-element results.

For each outage:
  1. Take element out of service (out_of_service = 1)
  2. Run AC load flow (ComLdf)
  3. Collect branch: loading_pct, i_ka, p_mw, q_mvar
     Collect node:   u_pu, u_kv, angle_deg
  4. Restore element (out_of_service = 0)
  5. Store results via db_writer
"""

from __future__ import annotations
import logging
from typing import Any

from database.db_manager import DBManager
from database import db_writer as W

log = logging.getLogger(__name__)

_CLS_LINE = "ElmLne"
_CLS_TR2  = "ElmTr2"
_CLS_NODE = "ElmTerm"


# ── Entry point ───────────────────────────────────────────────────────────────

def run_n1_study(app, db: DBManager, n_level: int = 1) -> int:
    """
    Iterate over all branches (lines + transformers), simulate each outage,
    collect results, and persist to the DB.

    Parameters
    ----------
    app     : PowerFactory application handle
    db      : Active DBManager context
    n_level : 1 for N-1, 2 for N-2 (N-2 pairs not yet implemented)

    Returns
    -------
    int : number of contingencies processed
    """
    branch_id_map = W.get_branch_id_map(db)
    node_id_map   = W.get_node_id_map(db)

    outage_elements = (
        app.GetCalcRelevantObjects(_CLS_LINE) +
        app.GetCalcRelevantObjects(_CLS_TR2)
    )
    log.info("Starting N-%d study: %d outage elements", n_level, len(outage_elements))

    ldf = _get_load_flow_command(app)
    processed = 0

    for element in outage_elements:
        name = element.loc_name
        bid  = branch_id_map.get(name)
        if bid is None:
            log.debug("Branch '%s' not in DB — skipped", name)
            continue

        btype = _branch_type(element)
        try:
            _take_out(element)
            err = ldf.Execute()
            if err:
                log.warning("Load flow failed for outage '%s' (err=%d) — skipped", name, err)
                _restore(element)
                continue

            # ── Persist contingency header ─────────────────────────────────
            cont_id = W.write_contingency(db, {
                "outage_element_id":   bid,
                "outage_element_name": name,
                "n_level":             n_level,
                "outage_type":         btype,
            })

            # ── Collect branch results ─────────────────────────────────────
            br_rows = _collect_branch_results(app, cont_id, branch_id_map, skip_id=bid)
            W.write_branch_results(db, br_rows)

            # ── Collect node results ───────────────────────────────────────
            nd_rows = _collect_node_results(app, cont_id, node_id_map)
            W.write_node_results(db, nd_rows)

            processed += 1
            if processed % 100 == 0:
                log.info("  … %d / %d done", processed, len(outage_elements))

        except Exception as e:
            log.error("Error processing outage '%s': %s", name, e)
        finally:
            _restore(element)

    db.commit()
    log.info("N-%d study complete: %d contingencies stored", n_level, processed)
    return processed


# ── Private helpers ───────────────────────────────────────────────────────────

def _get_load_flow_command(app):
    """Get or create a ComLdf command object."""
    ldf = app.GetFromStudyCase("ComLdf")
    if ldf is None:
        raise RuntimeError("ComLdf not found in study case. Open a study case in PowerFactory first.")
    ldf.iopt_net = 0   # AC balanced load flow
    ldf.iopt_at  = 0   # no automatic tapping
    return ldf


def _take_out(element) -> None:
    element.outserv = 1


def _restore(element) -> None:
    element.outserv = 0


def _branch_type(element) -> str:
    cls = element.GetClassName()
    if cls == "ElmLne":
        return "cable" if element.GetAttribute("inAir") == 0 else "line"
    return "transformer"


def _collect_branch_results(
    app,
    cont_id: int,
    branch_id_map: dict[str, int],
    skip_id: int,
) -> list[dict]:
    rows = []
    for cls in (_CLS_LINE, _CLS_TR2):
        for obj in app.GetCalcRelevantObjects(cls):
            bid = branch_id_map.get(obj.loc_name)
            if bid is None or bid == skip_id:
                continue
            try:
                rows.append({
                    "contingency_id": cont_id,
                    "branch_id":      bid,
                    "loading_pct":    obj.GetAttribute("c:loading") or 0.0,
                    "i_ka":           obj.GetAttribute("m:I:bus1")  or 0.0,
                    "p_mw":           obj.GetAttribute("m:P:bus1")  or 0.0,
                    "q_mvar":         obj.GetAttribute("m:Q:bus1")  or 0.0,
                })
            except Exception:
                pass
    return rows


def _collect_node_results(
    app,
    cont_id: int,
    node_id_map: dict[str, int],
) -> list[dict]:
    rows = []
    for obj in app.GetCalcRelevantObjects(_CLS_NODE):
        nid = node_id_map.get(obj.loc_name)
        if nid is None:
            continue
        try:
            u_pu  = obj.GetAttribute("m:u")  or 1.0
            u_kv  = obj.GetAttribute("m:u1") or None
            angle = obj.GetAttribute("m:phiu") or 0.0
            rows.append({
                "contingency_id": cont_id,
                "node_id":        nid,
                "u_pu":           u_pu,
                "u_kv":           u_kv,
                "angle_deg":      angle,
            })
        except Exception:
            pass
    return rows
