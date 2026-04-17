"""Package-wide exceptions for pfreporting."""


class PFReportError(Exception):
    """Base class for all package errors."""


class ReaderError(PFReportError):
    """Error reading PowerFactory results."""


class AnalysisError(PFReportError):
    """Error in threshold analysis."""


class ReportError(PFReportError):
    """Error during report generation."""
