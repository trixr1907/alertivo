param(
    [string]$ConfigPath = "system.json"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Python-Umgebung fehlt: $Python. Bitte zuerst .\scripts\setup_ready.ps1 ausfuehren."
}

$ResolvedConfigPath = if ([System.IO.Path]::IsPathRooted($ConfigPath)) { $ConfigPath } else { Join-Path $ProjectRoot $ConfigPath }

Start-Process -WindowStyle Hidden -FilePath $Python -ArgumentList @(
    (Join-Path $ProjectRoot "scripts\alertivo_exe_entry.py"),
    "--config", $ResolvedConfigPath
)

Write-Host "Alertivo startet im Hintergrund."
