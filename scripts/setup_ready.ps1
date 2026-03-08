param(
    [string]$ConfigPath = "config/monitor.yaml",
    [string]$EnvPath = "config/alerts.env.ps1",
    [switch]$RegisterTasks,
    [switch]$OpenDistillTargets
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Reset-PythonEnvironment {
    $vars = @(
        "PYTHONHOME",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "__PYVENV_LAUNCHER__",
        "PYTHONPLATLIBDIR"
    )
    foreach ($name in $vars) {
        if (Test-Path "Env:$name") {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        }
    }
}

Reset-PythonEnvironment

$ResolvedEnvPath = $EnvPath
if (-not [System.IO.Path]::IsPathRooted($ResolvedEnvPath)) {
    $ResolvedEnvPath = Join-Path $ProjectRoot $ResolvedEnvPath
}

$ResolvedConfigPath = $ConfigPath
if (-not [System.IO.Path]::IsPathRooted($ResolvedConfigPath)) {
    $ResolvedConfigPath = Join-Path $ProjectRoot $ResolvedConfigPath
}

if (-not (Test-Path $ResolvedEnvPath)) {
    Copy-Item (Join-Path $ProjectRoot "config\alerts.env.ps1.example") $ResolvedEnvPath
}

$envContent = Get-Content $ResolvedEnvPath -Raw
if ($envContent -match "replace-me-long-random-string") {
    $randomToken = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")
    $envContent = $envContent -replace "replace-me-long-random-string", $randomToken
    Set-Content -Path $ResolvedEnvPath -Value $envContent -Encoding UTF8
}

function Get-PythonLauncher {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py"
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return "python"
    }
    throw "Kein Python-Launcher gefunden. Installiere Python 3.12+ mit py.exe oder python.exe."
}

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VenvRoot = Join-Path $ProjectRoot ".venv"
$LinuxPython = Join-Path $ProjectRoot ".venv\bin\python"
$Launcher = Get-PythonLauncher
$TempWorkdir = Join-Path $env:TEMP "gpu-price-alerts-bootstrap"
New-Item -ItemType Directory -Force -Path $TempWorkdir | Out-Null

function New-WindowsVenv {
    Push-Location $TempWorkdir
    try {
        if ($Launcher -eq "py") {
            try {
                & py -3.12 -m venv $VenvRoot
            }
            catch {
                & py -3 -m venv $VenvRoot
            }
        }
        else {
            & python -m venv $VenvRoot
        }
    }
    finally {
        Pop-Location
    }
}

function Test-VenvPython {
    if (-not (Test-Path $Python)) {
        return $false
    }

    Reset-PythonEnvironment
    Push-Location $TempWorkdir
    try {
        & $Python -c "import pip" | Out-Null
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
    finally {
        Pop-Location
    }
}

if ((Test-Path ".venv") -and (-not (Test-Path $Python))) {
    if (Test-Path $LinuxPython) {
        Write-Host "Vorhandene .venv stammt nicht aus Windows. Erzeuge Windows-.venv neu..."
        Remove-Item ".venv" -Recurse -Force
    }
}

if (-not (Test-Path $Python)) {
    New-WindowsVenv
}

if (-not (Test-VenvPython)) {
    Write-Host "Vorhandene .venv ist defekt. Erzeuge Windows-.venv neu..."
    Remove-Item ".venv" -Recurse -Force -ErrorAction SilentlyContinue
    New-WindowsVenv
}

if (-not (Test-Path $Python)) {
    throw "Windows-Python in .venv konnte nicht erstellt werden: $Python"
}

if (-not (Test-VenvPython)) {
    throw "Python/Pip in .venv ist weiterhin defekt: $Python"
}

Reset-PythonEnvironment
Push-Location $TempWorkdir
& $Python -m pip install --disable-pip-version-check -e "$ProjectRoot"
Pop-Location

. $ResolvedEnvPath

Push-Location $TempWorkdir
& $Python (Join-Path $ProjectRoot "scripts\validate_setup.py") --config $ResolvedConfigPath --env $ResolvedEnvPath
Pop-Location

if ($OpenDistillTargets) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "scripts\open_distill_targets.ps1")
}

if ($RegisterTasks) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "scripts\register_tasks.ps1") -ConfigPath $ConfigPath -EnvPath $EnvPath
}

Write-Host ""
Write-Host "Ready state:"
Write-Host " - Env file: $ResolvedEnvPath"
Write-Host " - Config file: $ResolvedConfigPath"
Write-Host " - Virtualenv: $Python"
Write-Host ""
Write-Host "Start command:"
Write-Host " .\scripts\start_alertivo.ps1 -ConfigPath $ConfigPath -EnvPath $EnvPath"
