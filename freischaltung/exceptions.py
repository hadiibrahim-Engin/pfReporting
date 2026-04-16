"""Paketweite Ausnahmen für freischaltung."""


class FreischaltungError(Exception):
    """Basisklasse für alle Paket-Fehler."""


class ReaderError(FreischaltungError):
    """Fehler beim Lesen von PowerFactory-Ergebnissen."""


class AnalysisError(FreischaltungError):
    """Fehler in der Grenzwertanalyse."""


class ReportError(FreischaltungError):
    """Fehler bei der Report-Erzeugung."""
