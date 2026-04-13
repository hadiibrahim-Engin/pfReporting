"""
main.py — CLI entry point for the contingency reporting pipeline.

Commands:
    python main.py extract   → Extract from live PowerFactory → DB
    python main.py analyze   → Compute and print KPIs from existing DB
    python main.py report    → Generate HTML (+ optional PDF) from DB
    python main.py all       → extract → analyze → report
    python main.py test      → Full pipeline using mock data (no PF needed)

Examples:
    python main.py test --output output/report.html
    python main.py report --db data/my.db --scenario "Sommer-Niedriglast"
    python main.py all --project "Mein_Netz" --pdf
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt= "%H:%M:%S",
)
log = logging.getLogger("main")


# ── CLI definition ────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog        = "contingency_reporter",
        description = "N-1/N-k Contingency Analysis Reporting Pipeline",
        formatter_class = argparse.RawDescriptionHelpFormatter,
        epilog      = __doc__,
    )
    p.add_argument("command", choices=["extract", "analyze", "report", "all", "test"],
                   help="Pipeline command to run")
    p.add_argument("--db",       default=None, metavar="PATH",
                   help="SQLite database path (default: data/contingency.db)")
    p.add_argument("--output",   default=None, metavar="PATH",
                   help="HTML output path (default: output/Outage_Report.html)")
    p.add_argument("--project",  default=None, metavar="NAME",
                   help="PowerFactory project name (required for 'extract' / 'all')")
    p.add_argument("--scenario", default=None, metavar="NAME",
                   help="Scenario label for report header")
    p.add_argument("--netzname", default=None, metavar="NAME",
                   help="Network name for report header")
    p.add_argument("--pdf",      action="store_true",
                   help="Also export a PDF after HTML render")
    p.add_argument("--top-n",   type=int, default=None, metavar="INT",
                   help="Number of top contingencies to show (default: 10)")
    p.add_argument("--verbose", "-v", action="store_true",
                   help="Enable DEBUG logging")
    return p


# ── Command implementations ───────────────────────────────────────────────────

def cmd_extract(args) -> None:
    import config
    from powerfactory.pf_connector import connect
    from powerfactory import pf_extractor as EX
    from powerfactory.pf_contingency_runner import run_n1_study
    from database.db_manager import DBManager
    from database import db_writer as W

    project = args.project or config.PF_PROJECT_NAME
    db_path = args.db or config.DB_PATH

    log.info("Connecting to PowerFactory — project: %s", project)
    app, proj = connect(project)

    with DBManager(db_path) as db:
        log.info("Extracting topology …")
        nodes = EX.extract_nodes(app)
        W.write_nodes(db, nodes)

        lines = EX.extract_lines(app)
        trafos = EX.extract_transformers(app)
        # resolve node names → IDs before writing
        node_map = W.get_node_id_map(db)
        for row in lines + trafos:
            row["from_node_id"] = node_map.get(row.pop("from_node", ""), None)
            row["to_node_id"]   = node_map.get(row.pop("to_node",   ""), None)
        W.write_branches(db, lines + trafos)

        loads = EX.extract_loads(app)
        for row in loads:
            row["node_id"] = node_map.get(row.pop("node", ""), None)
        W.write_loads(db, loads)

        gens = EX.extract_generators(app)
        for row in gens:
            row["node_id"] = node_map.get(row.pop("node", ""), None)
        W.write_generators(db, gens)

        log.info("Running N-1 study …")
        run_n1_study(app, db)

    log.info("Extraction complete → %s", db_path)


def cmd_analyze(args) -> None:
    import config
    from database.db_manager import DBManager
    from analysis.kpi_calculator import calculate_kpis, print_kpi_summary

    db_path = args.db or config.DB_PATH
    with DBManager(db_path) as db:
        kpis = calculate_kpis(db)
    print_kpi_summary(kpis)


def cmd_report(args) -> None:
    import config
    from reporting.data_assembler import assemble_context
    from reporting.html_renderer import render_report
    from reporting.pdf_exporter import export_pdf

    db_path   = args.db       or config.DB_PATH
    html_out  = args.output   or config.HTML_OUTPUT
    scenario  = args.scenario or config.DEFAULT_SCENARIO
    netzname  = args.netzname or "Übertragungsnetz"

    if args.top_n:
        config.TOP_N_CONTINGENCIES = args.top_n

    log.info("Assembling report context from %s …", db_path)
    ctx = assemble_context(db_path, scenario=scenario, netzname=netzname)

    log.info("Rendering HTML …")
    out = render_report(ctx, output_path=html_out)
    log.info("HTML written → %s", out)
    _print_open_hint(out)

    if args.pdf:
        log.info("Exporting PDF …")
        pdf_out = export_pdf(html_path=out)
        log.info("PDF written → %s", pdf_out)


def cmd_test(args) -> None:
    import config
    from tests.mock_pf_data import populate_mock_database

    db_path  = args.db     or config.DB_PATH
    html_out = args.output or config.HTML_OUTPUT

    log.info("Generating mock 1000-node network → %s …", db_path)
    t0 = time.perf_counter()
    populate_mock_database(db_path)
    elapsed = time.perf_counter() - t0
    log.info("Mock data generated in %.1f s", elapsed)

    args.db       = db_path
    args.output   = html_out
    args.scenario = args.scenario or "Winter-Hochlast (Mock)"
    args.netzname = args.netzname or "Testnetz 1000 Knoten"
    cmd_report(args)


def cmd_all(args) -> None:
    cmd_extract(args)
    cmd_analyze(args)
    cmd_report(args)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _print_open_hint(path: Path) -> None:
    """Suggest how to open the report in a browser."""
    try:
        import os
        hint = f"file://{path.resolve()}"
    except Exception:
        hint = str(path)
    print(f"\n  Report ready: {hint}\n")


# ── Entry ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    dispatch = {
        "extract": cmd_extract,
        "analyze": cmd_analyze,
        "report":  cmd_report,
        "all":     cmd_all,
        "test":    cmd_test,
    }

    try:
        dispatch[args.command](args)
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
        sys.exit(130)
    except Exception as e:
        log.error("Pipeline failed: %s", e, exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    main()
