param(
    [string]$EnvPath = "config/alerts.env.ps1",
    [string]$ProfilePath = "config/user-profile.json",
    [string]$MonitorConfigPath = "config/monitor-config.json"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

function Resolve-RelativePath([string]$PathValue) {
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }
    return Join-Path $ProjectRoot $PathValue
}

$resolvedEnvPath = Resolve-RelativePath $EnvPath
$resolvedProfilePath = Resolve-RelativePath $ProfilePath
$resolvedMonitorConfigPath = Resolve-RelativePath $MonitorConfigPath
$examplePath = Join-Path $ProjectRoot "config/alerts.env.ps1.example"

if (-not (Test-Path $resolvedEnvPath)) {
    if (-not (Test-Path $examplePath)) {
        throw "Beispiel-Env-Datei fehlt: $examplePath"
    }
    Copy-Item $examplePath $resolvedEnvPath -Force
}

if (-not (Test-Path $resolvedProfilePath)) {
    $profileDir = Split-Path -Parent $resolvedProfilePath
    if (-not (Test-Path $profileDir)) {
        New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    }
    $profileJson = @"
{
  "display_name": "Alertivo User",
  "onboarding_completed": false,
  "simple_mode": true,
  "autostart_enabled": false,
  "close_to_tray": false,
  "intro_enabled": true,
  "preferred_source": ""
}
"@
    Set-Content -Path $resolvedProfilePath -Value $profileJson -Encoding UTF8
}

if (-not (Test-Path $resolvedMonitorConfigPath)) {
    $monitorConfigDir = Split-Path -Parent $resolvedMonitorConfigPath
    if (-not (Test-Path $monitorConfigDir)) {
        New-Item -ItemType Directory -Path $monitorConfigDir -Force | Out-Null
    }
    $stateJson = @"
{
  "version": 1,
  "migrated": false,
  "migrated_at": "",
  "monitor_config_path": "",
  "backup_path": null
}
"@
    Set-Content -Path $resolvedMonitorConfigPath -Value $stateJson -Encoding UTF8
}

exit 0
