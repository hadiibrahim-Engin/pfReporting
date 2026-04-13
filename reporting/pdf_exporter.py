"""
pdf_exporter.py — Convert the rendered HTML report to PDF.

Primary:  WeasyPrint  (pure Python, no external binary, recommended)
Fallback: pdfkit      (wraps wkhtmltopdf, needs separate install)

Installation:
    pip install weasyprint          # primary
    pip install pdfkit              # fallback
    brew install wkhtmltopdf        # required by pdfkit (macOS)
    # on Debian/Ubuntu: apt-get install wkhtmltopdf
"""

from __future__ import annotations
import logging
from pathlib import Path

import config

log = logging.getLogger(__name__)


def export_pdf(
    html_path: str | Path | None = None,
    pdf_path: str | Path | None  = None,
) -> Path:
    """
    Convert an HTML file to PDF.

    Tries WeasyPrint first; falls back to pdfkit if WeasyPrint is not installed.

    Parameters
    ----------
    html_path : Source HTML file (default: config.HTML_OUTPUT)
    pdf_path  : Destination PDF file (default: config.PDF_OUTPUT)

    Returns
    -------
    Path : Absolute path of the written PDF.

    Raises
    ------
    RuntimeError : If neither WeasyPrint nor pdfkit is available.
    """
    html_path = Path(html_path or config.HTML_OUTPUT)
    pdf_path  = Path(pdf_path  or config.PDF_OUTPUT)

    if not html_path.exists():
        raise FileNotFoundError(f"HTML source not found: {html_path}")

    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    if _try_weasyprint(html_path, pdf_path):
        return pdf_path.resolve()

    if _try_pdfkit(html_path, pdf_path):
        return pdf_path.resolve()

    raise RuntimeError(
        "No PDF engine available. Install WeasyPrint (`pip install weasyprint`) "
        "or pdfkit + wkhtmltopdf."
    )


# ── WeasyPrint (primary) ──────────────────────────────────────────────────────

def _try_weasyprint(html_path: Path, pdf_path: Path) -> bool:
    try:
        from weasyprint import HTML  # type: ignore
        log.info("Exporting PDF with WeasyPrint …")
        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        log.info("PDF written to %s", pdf_path)
        return True
    except ImportError:
        log.debug("WeasyPrint not installed — trying pdfkit …")
        return False
    except Exception as e:
        log.error("WeasyPrint failed: %s", e)
        return False


# ── pdfkit / wkhtmltopdf (fallback) ──────────────────────────────────────────

def _try_pdfkit(html_path: Path, pdf_path: Path) -> bool:
    try:
        import pdfkit  # type: ignore
        options = {
            "page-size":       "A4",
            "orientation":     "Portrait",
            "margin-top":      "10mm",
            "margin-bottom":   "10mm",
            "margin-left":     "10mm",
            "margin-right":    "10mm",
            "encoding":        "UTF-8",
            "enable-local-file-access": None,
            "javascript-delay": "2000",    # allow Chart.js to render
            "no-stop-slow-scripts": None,
        }
        log.info("Exporting PDF with pdfkit/wkhtmltopdf …")
        pdfkit.from_file(str(html_path), str(pdf_path), options=options)
        log.info("PDF written to %s", pdf_path)
        return True
    except ImportError:
        log.debug("pdfkit not installed")
        return False
    except Exception as e:
        log.error("pdfkit failed: %s", e)
        return False
