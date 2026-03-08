param(
    [string]$ConfigPath = "system.json",
    [string]$Title = "Alertivo Testangebot",
    [string]$Price = "499,00 EUR",
    [string]$TrackerId = "",
    [string]$Shop = "",
    [string]$ProductHint = "",
    [string]$Token = ""
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

$ResolvedConfigPath = $ConfigPath
if (-not [System.IO.Path]::IsPathRooted($ResolvedConfigPath)) {
    $ResolvedConfigPath = Join-Path $ProjectRoot $ResolvedConfigPath
}

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Python in .venv nicht gefunden. Fuehre zuerst .\\scripts\\setup_ready.ps1 aus."
}

$TempWorkdir = Join-Path $env:TEMP "alertivo-bootstrap"
New-Item -ItemType Directory -Force -Path $TempWorkdir | Out-Null

$ArgumentList = @(
    (Join-Path $ProjectRoot "scripts\send_test_webhook.py"),
    "--config", $ResolvedConfigPath,
    "--title", $Title,
    "--price", $Price
)

if ($TrackerId) {
    $ArgumentList += @("--tracker-id", $TrackerId)
}
if ($Shop) {
    $ArgumentList += @("--shop", $Shop)
}
if ($ProductHint) {
    $ArgumentList += @("--product-hint", $ProductHint)
}
if ($Token) {
    $ArgumentList += @("--token", $Token)
}

Reset-PythonEnvironment
Push-Location $TempWorkdir
& $Python @ArgumentList
Pop-Location
