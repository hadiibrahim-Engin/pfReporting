param(
    [Parameter(Mandatory = $false)]
    [string]$SourceRoot = (Get-Location).Path,

    [Parameter(Mandatory = $true)]
    [string]$TargetRoot,

    [Parameter(Mandatory = $false)]
    [string[]]$ExcludeDirectories = @('.git', '.venv', '.pytest_cache', '__pycache__', 'node_modules'),

    [Parameter(Mandatory = $false)]
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Test-IsExcludedPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string[]]$ExcludedNames
    )

    foreach ($name in $ExcludedNames) {
        $pattern = "*${([System.IO.Path]::DirectorySeparatorChar)}$name*"
        if ($Path -like $pattern -or [System.IO.Path]::GetFileName($Path) -eq $name) {
            return $true
        }
    }

    return $false
}

try {
    $resolvedSource = (Resolve-Path -Path $SourceRoot).Path

    if (-not (Test-Path -Path $TargetRoot)) {
        New-Item -Path $TargetRoot -ItemType Directory -Force | Out-Null
    }

    $resolvedTarget = (Resolve-Path -Path $TargetRoot).Path

    if ($resolvedSource -eq $resolvedTarget) {
        throw 'SourceRoot und TargetRoot duerfen nicht identisch sein.'
    }

    Write-Info "Quelle: $resolvedSource"
    Write-Info "Ziel:   $resolvedTarget"

    $dirCount = 0
    $fileCount = 0

    $allDirectories = Get-ChildItem -Path $resolvedSource -Directory -Recurse -Force
    foreach ($dir in $allDirectories) {
        if (Test-IsExcludedPath -Path $dir.FullName -ExcludedNames $ExcludeDirectories) {
            continue
        }

        $relativeDir = [System.IO.Path]::GetRelativePath($resolvedSource, $dir.FullName)
        $targetDir = Join-Path -Path $resolvedTarget -ChildPath $relativeDir

        if (-not (Test-Path -Path $targetDir)) {
            New-Item -Path $targetDir -ItemType Directory -Force | Out-Null
            $dirCount++
        }
    }

    $allFiles = Get-ChildItem -Path $resolvedSource -File -Recurse -Force
    foreach ($file in $allFiles) {
        if (Test-IsExcludedPath -Path $file.FullName -ExcludedNames $ExcludeDirectories) {
            continue
        }

        $relativeFile = [System.IO.Path]::GetRelativePath($resolvedSource, $file.FullName)
        $targetFile = Join-Path -Path $resolvedTarget -ChildPath $relativeFile
        $targetDir = Split-Path -Path $targetFile -Parent

        if (-not (Test-Path -Path $targetDir)) {
            New-Item -Path $targetDir -ItemType Directory -Force | Out-Null
            $dirCount++
        }

        if ((Test-Path -Path $targetFile) -and -not $Force.IsPresent) {
            Write-Warn "Datei existiert bereits, uebersprungen: $relativeFile"
            continue
        }

        New-Item -Path $targetFile -ItemType File -Force | Out-Null
        $fileCount++
    }

    Write-Host ''
    Write-Host 'Fertig.' -ForegroundColor Green
    Write-Host "Erstellte Ordner: $dirCount"
    Write-Host "Erstellte Dateien: $fileCount"
}
catch {
    Write-Error "Fehler beim Erstellen der Struktur: $($_.Exception.Message)"
    exit 1
}
