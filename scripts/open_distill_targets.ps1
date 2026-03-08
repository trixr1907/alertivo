param(
    [string]$ConfigPath = "system.json"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Get-PythonCommand {
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return "py"
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return "python"
    }
    throw "Kein Python-Launcher gefunden."
}

$ResolvedConfigPath = $ConfigPath
if (-not [System.IO.Path]::IsPathRooted($ResolvedConfigPath)) {
    $ResolvedConfigPath = Join-Path $ProjectRoot $ResolvedConfigPath
}

$PythonCommand = Get-PythonCommand
$env:PYTHONPATH = (Join-Path $ProjectRoot "src")

$PythonArgs = @(
    "-c",
    @'
import json
import sys
from pathlib import Path

from gpu_alerts.config import build_distill_targets, load_config

config = load_config(Path(sys.argv[1]))
urls = [entry["url"] for entry in build_distill_targets(config) if entry.get("url")]
print(json.dumps(urls))
'@,
    $ResolvedConfigPath
)

if ($PythonCommand -eq "py") {
    $RawUrls = & py -3 @PythonArgs
}
else {
    $RawUrls = & $PythonCommand @PythonArgs
}

$Targets = @()
if ($RawUrls) {
    $Targets = ($RawUrls | ConvertFrom-Json) | Select-Object -Unique
}

foreach ($Target in $Targets) {
    Start-Process $Target
    Start-Sleep -Milliseconds 200
}

Write-Host "Opened $($Targets.Count) Distill target tabs."
