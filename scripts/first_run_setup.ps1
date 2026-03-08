param(
    [string]$SystemPath = "system.json",
    [string]$AppName = "Alertivo"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

function Resolve-RelativePath([string]$PathValue) {
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }
    return Join-Path $ProjectRoot $PathValue
}

$ResolvedSystemPath = Resolve-RelativePath $SystemPath
$AppDataBase = if ($env:APPDATA) {
    Join-Path $env:APPDATA $AppName
} else {
    Join-Path (Join-Path $HOME ".config") $AppName
}

$TrackersDir = Join-Path $AppDataBase "trackers"
$DataDir = Join-Path $AppDataBase "data"
$LogsDir = Join-Path $AppDataBase "logs"
$StateDir = Join-Path $AppDataBase "state"
$SettingsPath = Join-Path $AppDataBase "settings.json"
$MigrationPath = Join-Path $StateDir "migration.json"

$directories = @($AppDataBase, $TrackersDir, $DataDir, $LogsDir, $StateDir)
foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

if (-not (Test-Path $ResolvedSystemPath)) {
    $systemJson = @"
{
  "schema_version": 1,
  "app": {
    "name": "Alertivo"
  },
  "control_center": {
    "host": "127.0.0.1",
    "port": 8787
  },
  "webhook": {
    "path": "/webhook/distill"
  },
  "logging": {
    "level": "INFO"
  },
  "monitoring": {
    "enable_restock_alerts": true,
    "new_listing_reference_min_age_seconds": 60,
    "default_timeout_seconds": 20,
    "default_interval_seconds": 60,
    "user_agent": "Alertivo/1.0"
  },
  "storage": {
    "appdata_subdir": "Alertivo",
    "database_filename": "alerts.sqlite",
    "logs_dirname": "logs"
  }
}
"@
    Set-Content -Path $ResolvedSystemPath -Value $systemJson -Encoding UTF8
}

if (-not (Test-Path $SettingsPath)) {
    $settingsJson = @"
{
  "schema_version": 1,
  "user": {
    "display_name": "Alertivo User",
    "onboarding_completed": false
  },
  "ui": {
    "simple_mode": true,
    "close_to_tray": false,
    "intro_enabled": true
  },
  "desktop": {
    "autostart_enabled": false
  },
  "notifications": {
    "telegram": {
      "enabled": false,
      "bot_token": "",
      "chat_id": ""
    },
    "discord": {
      "enabled": false,
      "webhook_url": ""
    },
    "windows": {
      "enabled": true,
      "app_id": "Alertivo"
    },
    "sound": {
      "enabled": true,
      "sound_file": null
    }
  },
  "integrations": {
    "distill": {
      "enabled": false,
      "token": ""
    }
  },
  "meta": {
    "created_at": "",
    "updated_at": ""
  }
}
"@
    Set-Content -Path $SettingsPath -Value $settingsJson -Encoding UTF8
}

if (-not (Test-Path $MigrationPath)) {
    $migrationJson = @"
{
  "version": 2,
  "migrated": false,
  "migrated_at": "",
  "legacy_paths": {},
  "settings_path": "$($SettingsPath.Replace("\", "\\"))",
  "trackers_dir": "$($TrackersDir.Replace("\", "\\"))",
  "imported_trackers": [],
  "unmapped_sources": []
}
"@
    Set-Content -Path $MigrationPath -Value $migrationJson -Encoding UTF8
}

exit 0
