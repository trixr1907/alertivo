param(
    [string]$TaskName = "Alertivo",
    [string]$ConfigPath = "system.json"
)

$ErrorActionPreference = "Stop"

Write-Warning "register_tasks.ps1 ist veraltet und erstellt keine Task-Scheduler-Eintraege mehr."
Write-Host "Autostart wird jetzt direkt im Alertivo Control Center verwaltet."
Write-Host "Pfad: Einstellungen > Autostart"
Write-Host "Keine Aktion ausgefuehrt fuer TaskName '$TaskName' und Config '$ConfigPath'."
