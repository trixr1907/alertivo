# Alertivo Desktop

Alertivo ist eine lokale Windows-Desktop-App fuer Produkt- und Restock-Monitoring. Die App ist nicht mehr auf einzelne Produkte fest verdrahtet. Stattdessen verwaltet sie beliebige Suchprofile als Tracker mit eigenen Include-/Exclude-Filtern und Shop-Zielen.

## Kernpunkte
- generische Tracker statt hart codierter Produktlogik in der Konfiguration
- lokale App-Daten unter `%APPDATA%\Alertivo`
- Control Center unter `http://127.0.0.1:8787/control-center`
- Distill-Webhook mit automatisch generiertem JSON-Snippet pro Tracker und Shop
- Benachrichtigungen fuer Telegram, Discord, Windows-Toast, Sound und Konsole

## Konfigurationsmodell
Installationsverzeichnis:
- `system.json`

Benutzerdaten unter `%APPDATA%\Alertivo`:
- `settings.json`
- `trackers\*.json`
- `data\alerts.sqlite`
- `logs\`
- `state\migration.json`

`system.json` enthaelt technische Defaults wie Port, Logging und Speicherorte. `settings.json` enthaelt nutzerspezifische Daten wie Tokens, UI-Optionen und Distill-Webhook-Token. Jeder Tracker lebt als eigene JSON-Datei in `trackers\`.

## Schnellstart unter Windows
1. Python 3.12 installieren.
2. Im Projektordner `.\scripts\setup_ready.ps1` ausfuehren.
3. Die App mit `.\scripts\start_alertivo.ps1` starten.
4. Im Browser `http://127.0.0.1:8787/control-center` oeffnen.
5. Im Onboarding Benachrichtigungen konfigurieren und den ersten Tracker anlegen.

Es ist kein manuelles Kopieren von `.env`-Dateien und kein Bearbeiten von `monitor.yaml` mehr notwendig.

## EXE Build
```powershell
.\scripts\build_exe.ps1
```

Das Windows-Bundle enthaelt:
- `dist\windows\bundle\Alertivo.exe`
- `dist\windows\bundle\run-alertivo.bat`
- `dist\windows\bundle\start-alertivo-hidden.ps1`
- `dist\windows\bundle\system.json`

Nutzerveraenderliche Daten landen beim Start automatisch unter `%APPDATA%\Alertivo`.

## Distill-Integration
Der Distill-Webhook laeuft lokal unter:
- `http://127.0.0.1:8787/webhook/distill`

Die benoetigten Header und das passende JSON fuer jeden Tracker erzeugt das Control Center dynamisch. Das Copy-and-paste-Snippet wird aus dem gespeicherten Distill-Token, dem Tracker und dem ausgewaehlten Shop erzeugt.

Zum Testen der lokalen Webhook-Kette:
```powershell
.\scripts\send_test_webhook.ps1
```

Optional kannst du gezielt einen Tracker testen:
```powershell
.\scripts\send_test_webhook.ps1 -TrackerId ps5-pro
```

## Legacy-Migration
Beim ersten Start importiert Alertivo vorhandene Altdateien automatisch, falls sie im Installationsverzeichnis unter `config\` liegen:
- `monitor.yaml`
- `alerts.env.ps1`
- `user-profile.json`

Der Import schreibt die neue Struktur nach `%APPDATA%\Alertivo` und legt den Migrationsstatus unter `state\migration.json` ab. Die alten YAML-/PowerShell-Dateien sind danach nur noch Legacy-Eingaben, nicht mehr das aktive Konfigurationsmodell.

Im Source-Checkout wird dieser Repo-Legacy-Import standardmaessig uebersprungen, damit ein frischer Start nicht versehentlich Beispiel- oder Entwicklerdateien uebernimmt. Fuer explizite Migrationstests kann er mit `ALERTIVO_IMPORT_LEGACY_FROM_REPO=1` wieder aktiviert werden.

## Projektstruktur
- `src/gpu_alerts/config.py`: JSON-Loader, Persistenz, Shop-Katalog, Legacy-Import
- `src/gpu_alerts/control_center.py`: Web-UI und API fuer Settings, Tracker und Runtime
- `src/gpu_alerts/engine.py`: Preislogik, Dedupe, Restock
- `src/gpu_alerts/storage.py`: SQLite
- `src/gpu_alerts/webhook.py`: lokaler Distill-Webhook
- `scripts/*.ps1`: Windows-Start, Build und Hilfsskripte

## Tests
```powershell
py -3.12 -m pip install -e ".[dev]"
py -3.12 -m pytest
```

## Hinweise
- `config/*.yaml` und einige Detaildokumente im Repo bleiben als Legacy-Beispiele und fuer Migrationstests erhalten.
- Shop-spezifische Parser und Fallbacks bleiben intern im Code und werden nicht als Endnutzer-JSON exponiert.
