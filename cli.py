"""
CLI entry point – pfreporting

Commands:
    generate         Generate a report (with real PF data or mock data)
    download-assets  Download vendor JS files
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="pfreporting",
    help="Automated De-Energization Assessment – HTML Report Generator",
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
) -> None:
    """Generate a De-Energization Assessment report."""
    from pfreporting.config import PFReportConfig
    from pfreporting.report.generator import HTMLReportGenerator

    cfg = PFReportConfig()
    if config:
        cfg = PFReportConfig.model_validate_json(config.read_text(encoding="utf-8"))
        console.print(f"[green]Configuration loaded:[/] {config}")

    if output_dir:
        cfg.report.output_dir = str(output_dir)

    if mock:
        _run_mock(cfg, pdf)
    else:
        _run_powerfactory(cfg, pdf)


def _run_mock(cfg, pdf: bool) -> None:
    """Generate a report using embedded demo data."""
    from pfreporting.report.builder import ReportData
    from pfreporting.report.generator import HTMLReportGenerator
    from pfreporting._mock_data import build_mock_data
    import datetime
    from pathlib import Path

    console.print(Panel("[bold]Demo Report (Mock Data)[/]", style="blue"))

    data: ReportData = build_mock_data()
    generator = HTMLReportGenerator(cfg)
    html = generator.generate(data)

    out_dir = Path(cfg.report.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = out_dir / f"DeEnergizationAssessment_DEMO_{ts}.html"
    dest.write_text(html, encoding="utf-8")

    console.print(f"[green]Report saved:[/] {dest}")

    if pdf:
        _export_pdf(dest)


def _run_powerfactory(cfg, pdf: bool) -> None:
    """Run the real PowerFactory assessment."""
    try:
        import powerfactory  # type: ignore
    except ImportError:
        console.print(
            "[red]PowerFactory Python API not found.[/]\n"
            "Use [bold]--mock[/] for demo data without PowerFactory."
        )
        raise typer.Exit(1)

    from pfreporting import run_report

    app_pf = powerfactory.GetApplication()
    dest = run_report(app_pf, cfg)
    console.print(f"[green]Report saved:[/] {dest}")

    if pdf:
        _export_pdf(dest)


def _export_pdf(html_path: Path) -> None:
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
    """Download Chart.js vendor files (for offline use)."""
    import subprocess

    script = Path(__file__).parent / "scripts" / "download_assets.py"
    subprocess.run([sys.executable, str(script)], check=True)


if __name__ == "__main__":
    app()
