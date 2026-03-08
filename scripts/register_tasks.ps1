param(
    [string]$TaskName = "GPUPriceAlerts",
    [string]$ConfigPath = "config/monitor.yaml",
    [string]$EnvPath = "config/alerts.env.ps1"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StartScript = Join-Path $ProjectRoot "scripts\start_monitor.ps1"

$MonitorAction = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$StartScript`" -ConfigPath `"$ConfigPath`" -EnvPath `"$EnvPath`""
$WatchdogAction = "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command `"if (-not (Get-Process python -ErrorAction SilentlyContinue | Where-Object { `$_.Path -like '*GPU*' })) { Start-Process powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','`"$StartScript`"','-ConfigPath','`"$ConfigPath`"','-EnvPath','`"$EnvPath`"' }`""

schtasks /Create /TN $TaskName /SC ONLOGON /RL HIGHEST /TR $MonitorAction /F | Out-Null
schtasks /Create /TN "$TaskName-Watchdog" /SC MINUTE /MO 5 /RL HIGHEST /TR $WatchdogAction /F | Out-Null

Write-Host "Tasks registered:"
Write-Host " - $TaskName"
Write-Host " - $TaskName-Watchdog"
