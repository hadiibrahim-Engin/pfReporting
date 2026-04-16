"""
CLI-Einstiegspunkt – freischaltung-report

Befehle:
    generate   Erzeugt einen Report (mit echten PF-Daten oder Mock-Daten)
    download-assets   Lädt Vendor-JS-Dateien herunter
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="freischaltung-report",
    help="Automatische Freischaltungsbewertung – HTML-Report-Generator",
    add_completion=False,
)
console = Console()


@app.command()
def generate(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Pfad zu einer JSON-Konfigurationsdatei (FreischaltungConfig).",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Ausgabeverzeichnis (überschreibt ReportConfig.output_dir).",
    ),
    mock: bool = typer.Option(
        False,
        "--mock",
        help="Verwendet eingebettete Demo-Daten (kein PowerFactory erforderlich).",
    ),
    pdf: bool = typer.Option(
        False,
        "--pdf",
        help="Erzeugt zusätzlich eine PDF-Datei (benötigt: pip install freischaltung[pdf]).",
    ),
) -> None:
    """Erzeugt einen Freischaltungsbewertungs-Report."""
    from freischaltung.config import FreischaltungConfig
    from freischaltung.report.generator import HTMLReportGenerator

    # Konfiguration laden
    cfg = FreischaltungConfig()
    if config:
        cfg = FreischaltungConfig.model_validate_json(config.read_text(encoding="utf-8"))
        console.print(f"[green]Konfiguration geladen:[/] {config}")

    if output_dir:
        cfg.report.output_dir = str(output_dir)

    if mock:
        _run_mock(cfg, pdf)
    else:
        _run_powerfactory(cfg, pdf)


def _run_mock(cfg, pdf: bool) -> None:
    """Generiert einen Report mit eingebetteten Demo-Daten."""
    from freischaltung.report.builder import ReportData
    from freischaltung.report.generator import HTMLReportGenerator
    from freischaltung._mock_data import build_mock_data
    import datetime
    from pathlib import Path

    console.print(Panel("[bold]Demo-Report (Mock-Daten)[/]", style="blue"))

    data: ReportData = build_mock_data()
    generator = HTMLReportGenerator(cfg)
    html = generator.generate(data)

    out_dir = Path(cfg.report.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = out_dir / f"Freischaltungsbewertung_DEMO_{ts}.html"
    dest.write_text(html, encoding="utf-8")

    console.print(f"[green]Report gespeichert:[/] {dest}")

    if pdf:
        _export_pdf(dest)


def _run_powerfactory(cfg, pdf: bool) -> None:
    """Startet die echte PowerFactory-Auswertung."""
    try:
        import powerfactory  # type: ignore
    except ImportError:
        console.print(
            "[red]PowerFactory-Python-API nicht gefunden.[/]\n"
            "Verwende [bold]--mock[/] für Demo-Daten ohne PowerFactory."
        )
        raise typer.Exit(1)

    from freischaltung import run_report

    app_pf = powerfactory.GetApplication()
    dest = run_report(app_pf, cfg)
    console.print(f"[green]Report gespeichert:[/] {dest}")

    if pdf:
        _export_pdf(dest)


def _export_pdf(html_path: Path) -> None:
    try:
        from weasyprint import HTML  # type: ignore
    except ImportError:
        console.print(
            "[yellow]PDF-Export nicht verfügbar.[/] "
            "Installiere: [bold]pip install freischaltung[pdf][/]"
        )
        return
    pdf_path = html_path.with_suffix(".pdf")
    HTML(filename=str(html_path)).write_pdf(str(pdf_path))
    console.print(f"[green]PDF gespeichert:[/] {pdf_path}")


@app.command()
def download_assets() -> None:
    """Lädt Chart.js-Vendor-Dateien herunter (für Offline-Betrieb)."""
    import subprocess

    script = Path(__file__).parent / "scripts" / "download_assets.py"
    subprocess.run([sys.executable, str(script)], check=True)


if __name__ == "__main__":
    app()
