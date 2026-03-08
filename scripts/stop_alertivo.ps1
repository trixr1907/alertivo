$ErrorActionPreference = "SilentlyContinue"

Get-Process -Name "Alertivo" -ErrorAction SilentlyContinue | Stop-Process -Force

$pythonCandidates = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue
foreach ($proc in $pythonCandidates) {
    if ($proc.CommandLine -and $proc.CommandLine.Contains("alertivo_exe_entry.py")) {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Alertivo wurde beendet (falls aktiv)."
