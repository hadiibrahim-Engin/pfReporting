# buildExe.ps1
# Builds generateExe.py with Nuitka (--onefile, windowed), code-signs the result,
# and moves the distributable EXE to Release\.
#
# Shared PowerShell modules are imported from the pythonAutomation repo.
# Three options for pointing $SharedModules to those modules — see CONFIG below.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# =============================================================================
# CONFIG
# =============================================================================

$Name         = "PowerFactory_Report_Starter"
$Script       = "generateExe.py"
$ReleaseDir   = Join-Path (Get-Location) "Release"
$DigiCertUtil = "C:\Program Files\DigiCertUtility\DigiCertUtil.exe"

# Set to $false to build a console EXE (useful for debugging)
$UseWindowed  = $true

# -- Shared PowerShell modules (pythonAutomation) ------------------------------
#
# PowerShell modules are shared the same way as Python packages — three options:
#
#   Option 1 - Sibling directory (default, works when repos are co-located):
#     $SharedModules = Join-Path $PSScriptRoot "..\pythonAutomation\scripts\SetupCore\modules"
#
#   Option 2 - Git submodule (version-pinned, works in CI without extra setup):
#     git submodule add ../pythonAutomation shared/ps-utils
#     $SharedModules = Join-Path $PSScriptRoot "shared\ps-utils\scripts\SetupCore\modules"
#
#   Option 3 - Azure Artifacts NuGet feed (exact analog of pip + Azure Artifacts PyPI):
#     Register-PSRepository -Name "MyFeed" `
#         -SourceLocation "https://pkgs.dev.azure.com/<ORG>/_packaging/<FEED>/nuget/v2" `
#         -InstallationPolicy Trusted
#     Install-Module -Name "PsSharedUtils" -Repository "MyFeed" -Force
#     (then $SharedModules is no longer needed — Import-Module PsSharedUtils)
#
$SharedModules = Join-Path $PSScriptRoot "..\pythonAutomation\scripts\SetupCore\modules"

# =============================================================================
# IMPORT SHARED MODULES
# =============================================================================

if (-not (Test-Path $SharedModules)) {
    throw (
        "Shared modules not found: $SharedModules`n" +
        "Clone pythonAutomation next to this repo, or update `$SharedModules in buildExe.ps1.`n" +
        "See the CONFIG section for alternatives (git submodule, Azure Artifacts)."
    )
}

foreach ($mod in @(
    'NativeCommand.psm1',   # base: safe process execution
    'UI.psm1',              # base: Write-Banner, Write-LogStepStart
    'Versioning.psm1',      # used by PythonDiscovery
    'Compat.psm1',          # platform shims
    'Filesystem.psm1',      # robust path removal
    'PythonDiscovery.psm1', # Find-AllPythonInterpreters
    'CodeSigning.psm1'      # Sign-Files, Sign-VenvScripts, Set-CodeSignerDefaults
)) {
    Import-Module (Join-Path $SharedModules $mod) -Force
}

# Pre-configure DigiCert (kernel driver signing off for venv, on for the EXE)
if (Test-Path $DigiCertUtil) {
    Set-CodeSignerDefaults -DigiCertUtilityExe $DigiCertUtil -KernelDriverSigning $false
}

# =============================================================================
# HELPERS
# =============================================================================

# Still needed for the Release EXE file-move step.
function Wait-ForFileUnlock {
    param(
        [Parameter(Mandatory)][string] $Path,
        [int] $TimeoutSec = 120,
        [int] $DelayMs    = 250
    )
    if (-not (Test-Path $Path)) { return $true }
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($true) {
        try {
            $fs = [System.IO.File]::Open(
                $Path,
                [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::ReadWrite,
                [System.IO.FileShare]::None
            )
            $fs.Close()
            return $true
        } catch {
            if ($sw.Elapsed.TotalSeconds -ge $TimeoutSec) { return $false }
            Start-Sleep -Milliseconds $DelayMs
        }
    }
}

# =============================================================================
# MAIN
# =============================================================================

if (-not (Test-Path $Script)) {
    throw "Entry-point script not found: $Script"
}

# -- 1. Discover Python --------------------------------------------------------
Write-Banner "Searching for Python interpreter…" -Type INFO

$pythons = Find-AllPythonInterpreters
if (-not $pythons -or $pythons.Count -eq 0) {
    throw (
        "No Python interpreter found.`n" +
        "Please install Python 3.11+ from https://python.org."
    )
}
$PythonExe = $pythons[0].Exe          # sorted descending → index 0 = newest
Write-Banner "Python: $PythonExe  (v$($pythons[0].Version))" -Type SUCCESS

# -- 2. Create isolated build venv ---------------------------------------------
Write-Banner "Creating build venv…" -Type INFO

$BuildVenv   = Join-Path $env:TEMP "pf_nuitka_build"
$BuildPython = Join-Path $BuildVenv "Scripts\python.exe"
$BuildPip    = Join-Path $BuildVenv "Scripts\pip.exe"

if (Test-Path $BuildVenv) {
    Write-Banner "Removing stale build venv: $BuildVenv" -Type WARN
    Remove-Item -Recurse -Force $BuildVenv
}

& $PythonExe -m venv $BuildVenv
if ($LASTEXITCODE -ne 0) { throw "venv creation failed." }

Write-Banner "Installing Nuitka + zstandard…" -Type INFO
& $BuildPip install --quiet --upgrade pip nuitka zstandard
if ($LASTEXITCODE -ne 0) { throw "pip install failed." }
Write-Banner "Packages installed." -Type SUCCESS

# -- 3. Sign build venv executables -------------------------------------------
if (Test-Path $DigiCertUtil) {
    Write-Banner "Signing build venv (Scripts\*.exe)…" -Type INFO
    $venvSig = Sign-VenvScripts `
        -VenvDir            $BuildVenv `
        -DigiCertUtilityExe $DigiCertUtil `
        -KernelDriverSigning $false
    Write-Banner "Signed: $($venvSig.Signed) / $($venvSig.Total)  —  Errors: $($venvSig.Failed.Count)" -Type SUCCESS
} else {
    Write-Banner "DigiCertUtil not found — signing skipped." -Type WARN
}

# -- 4. Clean previous build artifacts ----------------------------------------
Write-Banner "Cleaning old artifacts…" -Type INFO
Remove-Item -Recurse -Force ".\Release" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force ".\build"   -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force ".\dist"    -ErrorAction SilentlyContinue

# -- 5. Build with Nuitka ------------------------------------------------------
Write-Banner "Building EXE with Nuitka…" -Type INFO

$consoleMode = if ($UseWindowed) { "disable" } else { "force" }

& $BuildPython -m nuitka `
    --onefile `
    "--windows-console-mode=$consoleMode" `
    "--output-filename=$Name.exe" `
    --output-dir=dist `
    "$Script"

if ($LASTEXITCODE -ne 0) { throw "Nuitka failed with exit code $LASTEXITCODE." }

$DistExe = Join-Path (Get-Location) "dist\$Name.exe"
if (-not (Test-Path $DistExe)) {
    throw "Built EXE not found: $DistExe"
}
Write-Banner "Nuitka build complete: $DistExe" -Type SUCCESS

# -- 6. Sign the distributable EXE --------------------------------------------
if (Test-Path $DigiCertUtil) {
    Write-Banner "Signing EXE (KernelDriverSigning)…" -Type INFO
    $exeSig = Sign-Files `
        -DigiCertUtilityExe  $DigiCertUtil `
        -Files               @($DistExe) `
        -KernelDriverSigning $true
    if ($exeSig.Failed.Count -gt 0) {
        throw "EXE signing failed: $($exeSig.Failed -join ', ')"
    }
    Write-Banner "EXE signed successfully." -Type SUCCESS
} else {
    Write-Banner "DigiCertUtil not found — EXE signing skipped." -Type WARN
}

# -- 7. Move to Release\ -------------------------------------------------------
Write-Banner "Moving EXE to Release\…" -Type INFO

if (-not (Test-Path $ReleaseDir)) {
    New-Item -ItemType Directory -Path $ReleaseDir | Out-Null
}
$TargetExe = Join-Path $ReleaseDir "$Name.exe"
if (Test-Path $TargetExe) {
    if (-not (Wait-ForFileUnlock -Path $TargetExe -TimeoutSec 30)) {
        throw "Release EXE is locked and cannot be replaced: $TargetExe"
    }
    Remove-Item -Force $TargetExe
}
Move-Item -Force $DistExe $TargetExe

# -- 8. Clean build artifacts and temp venv -----------------------------------
Write-Banner "Cleaning up…" -Type INFO
Remove-Item -Recurse -Force ".\build"  -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force ".\dist"   -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $BuildVenv -ErrorAction SilentlyContinue

# -- 9. Summary ----------------------------------------------------------------
$hash    = (Get-FileHash $TargetExe -Algorithm SHA256).Hash
$exeSize = [math]::Round((Get-Item $TargetExe).Length / 1KB, 1)

Write-Banner "════════════════════════════════════════" -Type SUCCESS
Write-Banner " Distributable EXE:" -Type SUCCESS
Write-Banner "   $TargetExe" -Type SUCCESS
Write-Banner "   Size  : ${exeSize} KB" -Type SUCCESS
Write-Banner "   SHA256: $hash" -Type SUCCESS
Write-Banner "════════════════════════════════════════" -Type SUCCESS
