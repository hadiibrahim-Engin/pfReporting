"""
CLI entry point - pfreporting

Commands:
    generate         Generate a report (with real PF data or mock data)
    calc-tables      Run calculations and write IntReport time-series tables
    download-assets  Download vendor JS files

Usage examples:
    # Generate a demo report without PowerFactory
    pfreporting generate --mock --output-dir ./output

    # Generate using a JSON config (PFReportConfig)
    pfreporting generate --config ./config.json --output-dir ./output

    # Run only calculations (skip HTML)
    pfreporting generate --mode calculations_only

    # Generate HTML only (no calculations)
    pfreporting generate --mode html_only

    # Create PDF output (requires: pip install pfreporting[pdf])
    pfreporting generate --mock --pdf --output-dir ./output

    # Run calculations and write scripted IntReport tables
    pfreporting calc-tables --intreport MyReport --config ./config.json

    # Download vendor JS assets (Chart.js, zoom plugin)
    pfreporting download-assets
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="pfreporting",
    help="Automated De-Energization Assessment - HTML Report Generator",
    add_completion=False,
)
console = Console()


@app.command()
def generate(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to a JSON configuration file (PFReportConfig).",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Output directory (overrides ReportConfig.output_dir).",
    ),
    mock: bool = typer.Option(
        False,
        "--mock",
        help="Use embedded demo data (no PowerFactory required).",
    ),
    pdf: bool = typer.Option(
        False,
        "--pdf",
        help="Also generate a PDF file (requires: pip install pfreporting[pdf]).",
    ),
    mode: str = typer.Option(
        "full",
        "--mode",
        "-m",
        help="Execution mode: full | calculations_only | tables_only | html_only | summary_only",
    ),
) -> None:
    """Generate a De-Energization Assessment report.

    Args:
        config: Optional JSON configuration file path.
        output_dir: Optional output directory override.
        mock: When ``True``, use embedded demo data.
        pdf: When ``True``, also export PDF output.
        mode: Controls which report phases are executed.
    """
    from pfreporting.config import PFReportConfig
    from pfreporting.pipeline import ExecutionMode

    cfg = PFReportConfig()
    if config:
        cfg = PFReportConfig.model_validate_json(config.read_text(encoding="utf-8"))
        console.print(f"[green]Configuration loaded:[/] {config}")

    if output_dir:
        cfg.report.output_dir = str(output_dir)

    try:
        exec_mode = ExecutionMode[mode.upper().replace("-", "_")]
    except KeyError:
        valid = " | ".join(m.name.lower() for m in ExecutionMode)
        console.print(f"[red]Invalid --mode '{mode}'.[/] Valid values: {valid}")
        raise typer.Exit(1)

    if mock:
        _run_mock(cfg, pdf, exec_mode)
    else:
        _run_powerfactory(cfg, pdf, exec_mode)


def _resolve_intreport(app_pf: Any, preferred_name: str | None) -> Any:
    """Resolve IntReport object by name or fall back to first in study case."""
    try:
        sc = app_pf.GetActiveStudyCase()
    except Exception:
        sc = None
    reports = sc.GetContents("*.IntReport") if sc else []
    reports = reports or []

    if preferred_name:
        for report in reports:
            if getattr(report, "loc_name", "") == preferred_name:
                return report
        console.print(
            f"[red]IntReport not found:[/] {preferred_name} "
            f"(available: {len(reports)})"
        )
        raise typer.Exit(1)

    if reports:
        return reports[0]

    console.print(
        "[red]No IntReport found in active study case.[/]\n"
        "Create one in PowerFactory or pass --intreport <name>."
    )
    raise typer.Exit(1)


@app.command("calc-tables")
def calc_tables(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to a JSON configuration file (PFReportConfig).",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    intreport: Optional[str] = typer.Option(
        None,
        "--intreport",
        "-r",
        help="Target IntReport name (defaults to config.report.intreport_name or first found).",
    ),
) -> None:
    """Run calculations and write IntReport time-series tables."""
    try:
        import powerfactory  # type: ignore
    except ImportError:
        console.print(
            "[red]PowerFactory Python API not found.[/]\n"
            "This command requires running inside a PowerFactory Python environment."
        )
        raise typer.Exit(1)

    from pfreporting.config import PFReportConfig
    from pfreporting.pipeline import ExecutionMode, run_full_workflow

    cfg = PFReportConfig()
    if config:
        cfg = PFReportConfig.model_validate_json(config.read_text(encoding="utf-8"))
        console.print(f"[green]Configuration loaded:[/] {config}")

    if not cfg.calc.run_qds:
        console.print(
            "[red]calc.run_qds is False in the configuration.[/] "
            "Enable it to generate time-series tables."
        )
        raise typer.Exit(1)

    app_pf = powerfactory.GetApplication()
    name = intreport or cfg.report.intreport_name
    pf_report = _resolve_intreport(app_pf, name)

    run_full_workflow(
        app=app_pf,
        config=cfg,
        pf_report=pf_report,
        mode=ExecutionMode.CALCULATIONS_ONLY,
    )
    console.print(
        f"[green]Calculations complete.[/] Tables written to IntReport: "
        f"{getattr(pf_report, 'loc_name', '?')}"
    )


def _run_mock(cfg, pdf: bool, exec_mode=None) -> None:
    """Generate report output from packaged mock data.

    Args:
        cfg: Loaded report configuration.
        pdf: Whether PDF export should be attempted.
        exec_mode: ExecutionMode controlling which reports are generated.
    """
    from pfreporting.report.builder import ReportData
    from pfreporting.report.generator import HTMLReportGenerator
    from pfreporting.report.renderers import ExecSummaryRenderer
    from pfreporting._mock_data import build_mock_data
    from pfreporting.pipeline import ExecutionMode
    import datetime
    from pathlib import Path

    if exec_mode is None:
        exec_mode = ExecutionMode.FULL

    console.print(Panel("[bold]Demo Report (Mock Data)[/]", style="blue"))

    data: ReportData = build_mock_data()
    out_dir = Path(cfg.report.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    if exec_mode in (ExecutionMode.FULL, ExecutionMode.HTML_ONLY, ExecutionMode.TABLES_ONLY):
        generator = HTMLReportGenerator(cfg)
        html = generator.generate(data)
        dest = out_dir / f"DeEnergizationAssessment_DEMO_{ts}.html"
        dest.write_text(html, encoding="utf-8")
        console.print(f"[green]Report saved:[/] {dest}")
        if pdf:
            _export_pdf(dest)

    if exec_mode in (ExecutionMode.FULL, ExecutionMode.SUMMARY_ONLY):
        exec_html = ExecSummaryRenderer(cfg).render(data)
        exec_dest = out_dir / f"DeEnergizationAssessment_DEMO_{ts}_ExecSummary.html"
        exec_dest.write_text(exec_html, encoding="utf-8")
        console.print(f"[green]Executive summary saved:[/] {exec_dest}")


def _run_powerfactory(cfg, pdf: bool, exec_mode=None) -> None:
    """Generate report output from live PowerFactory calculations.

    Args:
        cfg: Loaded report configuration.
        pdf: Whether PDF export should be attempted.
        exec_mode: ExecutionMode controlling which reports are generated.
    """
    try:
        import powerfactory  # type: ignore
    except ImportError:
        console.print(
            "[red]PowerFactory Python API not found.[/]\n"
            "Use [bold]--mock[/] for demo data without PowerFactory."
        )
        raise typer.Exit(1)

    from pfreporting.pipeline import ExecutionMode, run_full_workflow

    if exec_mode is None:
        exec_mode = ExecutionMode.FULL

    app_pf = powerfactory.GetApplication()
    outputs = run_full_workflow(app_pf, cfg, mode=exec_mode)
    for key, dest in outputs.items():
        console.print(f"[green]{key} saved:[/] {dest}")
        if pdf and key == "main":
            _export_pdf(dest)


def _export_pdf(html_path: Path) -> None:
    """Export a generated HTML report to PDF when WeasyPrint is available."""
    try:
        from weasyprint import HTML  # type: ignore
    except ImportError:
        console.print(
            "[yellow]PDF export not available.[/] "
            "Install: [bold]pip install pfreporting[pdf][/]"
        )
        return
    pdf_path = html_path.with_suffix(".pdf")
    HTML(filename=str(html_path)).write_pdf(str(pdf_path))
    console.print(f"[green]PDF saved:[/] {pdf_path}")


@app.command()
def download_assets() -> None:
    """Download report vendor assets used for offline chart rendering."""
    import subprocess

    script = Path(__file__).parent / "scripts" / "download_assets.py"
    subprocess.run([sys.executable, str(script)], check=True)


if __name__ == "__main__":
    app()
