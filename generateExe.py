"""
generateExe.py – General-purpose PowerFactory bootstrapper.

Edit the PROJECT CONFIG section for your environment.
The rest (Python discovery, venv management, INI writing, PF launch) is
reusable machinery that works unchanged across projects.

Usage:
  As .py     – python generateExe.py  (IDE run button, terminal)
  As EXE     – compile once with Nuitka (see buildExe.ps1), distribute the EXE
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# =============================================================================
# PROJECT CONFIG  ← edit this block; everything below is generic machinery
# =============================================================================

# Path to PowerFactory.exe
PF_EXE = Path(r"C:\Program Files\DIgSILENT\PowerFactory 2025 SP3\PowerFactory.exe")

# Per-user storage: venv + generated INI live here
BASE_DIR = Path(os.getenv("LOCALAPPDATA", r"C:\LocalData")) / "pf_report"
VENV_DIR = BASE_DIR / "venv"
INI_PATH = BASE_DIR / "pf_bootstrap.ini"

# ── Package source (first match wins) ────────────────────────────────────────
# Option A: editable local install — used in dev mode when the directory exists
LOCAL_PACKAGE: Optional[Path] = Path(__file__).parent / "pfreporting"

# Option B: install from Azure Artifacts PyPI feed
AZURE_FEED_URL: Optional[str] = None
# Example: "https://pkgs.dev.azure.com/<ORG>/<PROJECT>/_packaging/pfreporting-feed/pypi/simple/"
PACKAGE_NAME: str = "pfreporting"

# ── Python interpreter for venv creation ─────────────────────────────────────
# None = auto-discover (checks sys.executable, py launcher, registry, common paths).
# Set explicitly if auto-discovery is unreliable in your environment, e.g.:
#   BASE_PYTHON = Path(r"C:\Python311\python.exe")
BASE_PYTHON: Optional[Path] = None

# ── INI value overrides ───────────────────────────────────────────────────────
# Any key here replaces the same key in _INI_DEFAULTS below.
INI_OVERRIDES: Dict[str, str] = {
    # "db_service":            "MY_SERVICE",
    # "license_server":        "my-license-server",
    # "authentication_server": "auth.example.com:8080",
}

# =============================================================================
# INI TEMPLATE & DEFAULTS  (shared across all PowerFactory projects)
# =============================================================================

_INI_TEMPLATE = """\
[advanced]
additionalPath = {additional_path}
authenticationServer = {authentication_server}
workspaceTemplate = {workspaceTemplate}

[database]
password = {db_password}
service = {db_service}
username = {db_username}

[externalApplications]
pythonDir = {python_dir}
pythonInterpreter = 1

[license]
container = {license_container}
floatingServer = {license_floating_server}
server = {license_server}
"""

_INI_DEFAULTS: Dict[str, str] = {
    "additional_path":         r"C:\LocalData\instantclient",
    "authentication_server":   "CHANGE_ME_AUTH_SERVER:PORT",
    "workspaceTemplate": (
        r"C:\Program Files\DIgSILENT\PowerFactory 2025 SP3"
        r"\WorkspaceTemplate\TemplateWorkspace20250917.zip"
    ),
    "db_password":             "CHANGE_ME_DB_PASSWORD",
    "db_service":              "CHANGE_ME_DB_SERVICE",
    "db_username":             "CHANGE_ME_DB_USERNAME",
    "license_container":       "CHANGE_ME_LICENSE_CONTAINER",
    "license_floating_server": "CHANGE_ME_FLOATING_SERVER",
    "license_server":          "CHANGE_ME_LICENSE_SERVER",
}

# =============================================================================
# PYTHON AUTO-DISCOVERY
# =============================================================================


def _candidate_pythons() -> List[Path]:
    """Collect Python interpreter candidates from most to least preferred."""
    candidates: List[Path] = []

    # 1. Explicit override always wins
    if BASE_PYTHON:
        candidates.append(BASE_PYTHON)

    # 2. Current interpreter — valid when running the .py script directly
    exe = Path(sys.executable)
    if exe.stem.lower().startswith("python"):
        candidates.append(exe)

    # 3. Windows Python Launcher (py.exe) — covers most standard installs
    try:
        result = subprocess.run(
            ["py", "-3", "-c", "import sys; print(sys.executable)"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            candidates.append(Path(result.stdout.strip()))
    except Exception:
        pass

    # 4. Windows registry — covers both HKLM (system) and HKCU (user) installs
    try:
        import winreg  # type: ignore[import]
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                core = winreg.OpenKey(hive, r"SOFTWARE\Python\PythonCore")
                n_versions = winreg.QueryInfoKey(core)[0]
                for i in range(n_versions):
                    ver = winreg.EnumKey(core, i)
                    try:
                        install_key = winreg.OpenKey(core, rf"{ver}\InstallPath")
                        exe_path, _ = winreg.QueryValueEx(install_key, "ExecutablePath")
                        candidates.append(Path(exe_path))
                    except OSError:
                        pass
            except OSError:
                pass
    except ImportError:
        pass  # not on Windows — harmless during macOS development

    # 5. Common install directories (newest version first via reverse sort)
    local_app = Path(os.getenv("LOCALAPPDATA", ""))
    search_roots = [
        local_app / "Programs" / "Python",
        Path(r"C:\Python"),
        Path(r"C:\Program Files\Python"),
        Path(r"C:\Program Files (x86)\Python"),
    ]
    for root in search_roots:
        if root.exists():
            for sub in sorted(root.iterdir(), reverse=True):
                py_exe = sub / "python.exe"
                if py_exe.exists():
                    candidates.append(py_exe)

    return candidates


def find_python() -> Path:
    """Return the first existing Python interpreter candidate."""
    for candidate in _candidate_pythons():
        if candidate.exists():
            return candidate
    raise RuntimeError(
        "No Python 3 interpreter found.\n\n"
        "Please choose one of the following options:\n"
        "  • Install Python 3.11+ from https://python.org\n"
        "  • Set BASE_PYTHON in generateExe.py to an existing python.exe"
    )


# =============================================================================
# VENV MANAGEMENT
# =============================================================================


def _install_package() -> None:
    pip = VENV_DIR / "Scripts" / "pip.exe"
    if not pip.exists():
        raise RuntimeError(f"pip.exe not found after venv creation: {pip}")

    if LOCAL_PACKAGE and LOCAL_PACKAGE.exists():
        subprocess.check_call([str(pip), "install", "-e", str(LOCAL_PACKAGE)])
        return

    if AZURE_FEED_URL:
        subprocess.check_call([
            str(pip), "install", PACKAGE_NAME,
            "--index-url", AZURE_FEED_URL,
            "--extra-index-url", "https://pypi.org/simple/",
        ])
        return

    raise RuntimeError(
        "No package source configured.\n"
        "Please set LOCAL_PACKAGE (local directory) or AZURE_FEED_URL."
    )


def ensure_venv() -> None:
    """Create the venv and install the package if it doesn't exist yet."""
    if VENV_DIR.exists():
        return
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    base = find_python()
    subprocess.check_call([str(base), "-m", "venv", str(VENV_DIR)])
    _install_package()


def venv_python() -> Path:
    """Return python.exe inside the venv."""
    for candidate in (VENV_DIR / "Scripts" / "python.exe", VENV_DIR / "python.exe"):
        if candidate.exists():
            return candidate
    raise RuntimeError(
        f"python.exe not found in venv: {VENV_DIR}\n"
        "Delete the directory and restart to recreate the venv."
    )


# =============================================================================
# INI FILE
# =============================================================================


def write_ini(python_dir: Path) -> Path:
    """Write the PowerFactory INI file and return its path."""
    values = dict(_INI_DEFAULTS)
    values.update(INI_OVERRIDES)
    values["python_dir"] = str(python_dir)
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    INI_PATH.write_text(_INI_TEMPLATE.format(**values), encoding="utf-8")
    return INI_PATH


# =============================================================================
# POWERFACTORY LAUNCH
# =============================================================================


def launch_powerfactory(ini_file: Path, python_exe: Path) -> None:
    """Launch PowerFactory detached, stripped of any PyInstaller/Nuitka env vars."""
    if not PF_EXE.exists():
        raise RuntimeError(
            f"PowerFactory.exe not found:\n{PF_EXE}\n\n"
            "Please update PF_EXE in generateExe.py."
        )

    env = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "NUITKA_ONEFILE_PARENT"):
        env.pop(key, None)

    subprocess.Popen(
        [str(PF_EXE), "/ini", str(ini_file), "-python", str(python_exe)],
        shell=False,
        creationflags=0x00000008 | 0x08000000,  # DETACHED_PROCESS | CREATE_NO_WINDOW
        cwd=str(Path.home()),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


# =============================================================================
# ERROR REPORTING
# =============================================================================


def _show_error(message: str) -> None:
    """Display a Windows MessageBox — visible even without a console window."""
    try:
        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            0, message, "PowerFactory Report Starter", 0x10
        )
    except Exception:
        pass


# =============================================================================
# ENTRY POINT
# =============================================================================


def main() -> None:
    try:
        ensure_venv()
        py_exe   = venv_python()
        ini_file = write_ini(VENV_DIR)
        launch_powerfactory(ini_file, py_exe)
        time.sleep(1)
    except Exception as exc:
        _show_error(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
