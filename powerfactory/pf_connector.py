"""
pf_connector.py — Establish a connection to a running PowerFactory instance
and activate the target project.

This module wraps the `powerfactory` COM/Python API.
It must be run from within PowerFactory's embedded Python or an external
Python process with the PF installation on sys.path.

Usage:
    from powerfactory.pf_connector import connect

    app, project = connect(project_name="Mein_Netz")
"""

from __future__ import annotations
import sys
import logging

log = logging.getLogger(__name__)


def connect(
    project_name: str,
    username: str = "",
    show_ui: bool = False,
) -> tuple:
    """
    Connect to a running PowerFactory instance and activate a project.

    Parameters
    ----------
    project_name : str
        Name of the project to activate (exact match, case-sensitive on some PF versions).
    username : str
        PF username. Leave empty to use the currently logged-in Windows user.
    show_ui : bool
        If True, the PF main window becomes visible.

    Returns
    -------
    (app, project) : tuple
        PF application handle and activated project handle.

    Raises
    ------
    RuntimeError
        If PF is not running, the project is not found, or activation fails.
    """
    try:
        import powerfactory as pf  # type: ignore  # not available outside PF
    except ImportError as e:
        raise RuntimeError(
            "PowerFactory module not found. "
            "Run this script from within PowerFactory's Python environment, "
            "or add the PF installation directory to sys.path."
        ) from e

    # ── Get application handle ────────────────────────────────────────────────
    try:
        if username:
            app = pf.GetApplicationExt(username)
        else:
            app = pf.GetApplicationExt()
    except Exception as e:
        raise RuntimeError(f"Could not connect to PowerFactory: {e}") from e

    if app is None:
        raise RuntimeError(
            "PowerFactory is not running or could not be started. "
            "Launch PowerFactory first."
        )

    if show_ui:
        app.Show()

    app.ClearOutputWindow()
    log.info("Connected to PowerFactory %s", _get_version(app))

    # ── Activate project ──────────────────────────────────────────────────────
    err = app.ActivateProject(project_name)
    if err:
        available = _list_projects(app)
        raise RuntimeError(
            f"Could not activate project '{project_name}' (error code {err}). "
            f"Available projects: {available}"
        )

    project = app.GetActiveProject()
    if project is None:
        raise RuntimeError("Project activation succeeded but GetActiveProject() returned None.")

    log.info("Activated project: %s", project.loc_name)
    return app, project


def disconnect(app) -> None:
    """Cleanly release the PowerFactory application handle."""
    if app is not None:
        try:
            app.PostCommand("exit")
        except Exception:
            pass


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_version(app) -> str:
    try:
        return app.GetVersion()
    except Exception:
        return "(unknown version)"


def _list_projects(app) -> list[str]:
    """Return names of all projects visible to the current user."""
    try:
        user = app.GetCurrentUser()
        projs = user.GetContents("*.IntPrj")
        return [p.loc_name for p in projs] if projs else []
    except Exception:
        return []
