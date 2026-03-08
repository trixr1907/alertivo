# 30-Minuten-Setup-Checkliste

## Minute 0-5
- Python 3.12 installieren.
- Projektordner oeffnen.
- `.\scripts\setup_ready.ps1` ausfuehren.

## Minute 5-8
- App starten:

```powershell
.\scripts\start_alertivo.ps1
```

- Control Center unter `http://127.0.0.1:8787/control-center` oeffnen.

## Minute 8-12
- Im Onboarding:
  - Anzeigename setzen
  - Telegram Bot Token und Chat ID eintragen
  - Discord Webhook URL eintragen
  - optional Distill-Token setzen

## Minute 12-18
- Ersten Tracker anlegen:
  - Produktname
  - Suchbegriff
  - Include Terms
  - Exclude Terms
  - Shops

## Minute 18-22
- Test-Alert senden:

```powershell
.\scripts\send_test_webhook.ps1
```

- Pruefen:
  - Windows-Toast
  - Sound
  - Telegram
  - Discord

## Minute 22-27
- Fuer JS-lastige Shops im Control Center das Distill-Snippet kopieren.
- In Distill pro Shop einen lokalen Monitor anlegen.
- URL, Header und JSON-Body aus dem Snippet uebernehmen.

## Minute 27-30
- Tracker pruefen und ggf. weitere Produkte anlegen.
- Laufende App ueber Tray oder Control Center verwalten.

## Fertig, wenn
- `settings.json` unter `%APPDATA%\Alertivo` existiert
- mindestens eine Datei unter `%APPDATA%\Alertivo\trackers` existiert
- Test-Webhook lokal ankommt
- Benachrichtigungen wie erwartet ausgeloest werden
