"""
pfreporting - Automatic De-energization Assessment with PowerFactory.

Public API:
    run_full_workflow(app, config, pf_report)
    run_report(app, config)
    PFReportConfig
"""
from pfreporting.__version__ import __version__
from pfreporting.config import PFReportConfig
from pfreporting.pipeline import run_full_workflow, run_report

__all__ = ["run_full_workflow", "run_report", "PFReportConfig", "__version__"]
