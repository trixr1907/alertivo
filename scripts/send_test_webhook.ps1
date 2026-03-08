param(
    [string]$EnvPath = "config/alerts.env.ps1",
    [string]$Title = "MSI GeForce RTX 5070 Ti Gaming Trio OC",
    [string]$Price = "1039,00 €",
    [string]$Shop = "alternate",
    [string]$ProductHint = "rtx-5070-ti"
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

if (Test-Path $ResolvedEnvPath) {
    . $ResolvedEnvPath
}

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Python in .venv nicht gefunden. Starte zuerst .\scripts\start_monitor.ps1"
}

Reset-PythonEnvironment
$TempWorkdir = Join-Path $env:TEMP "gpu-price-alerts-bootstrap"
New-Item -ItemType Directory -Force -Path $TempWorkdir | Out-Null

Push-Location $TempWorkdir
& $Python (Join-Path $ProjectRoot "scripts\send_test_webhook.py") `
    --token $env:WEBHOOK_TOKEN `
    --title $Title `
    --price $Price `
    --shop $Shop `
    --product-hint $ProductHint
Pop-Location
