# Windows Live Setup

## 1. Vorbereitung
- Python 3.12 installieren.
- Projekt in einen beliebigen Ordner legen. Feste Pfade wie `C:\GPU` sind nicht mehr erforderlich.
- Im Projektordner `.\scripts\setup_ready.ps1` ausfuehren.

## 2. Start
```powershell
.\scripts\start_alertivo.ps1
```

Danach laeuft das lokale Control Center unter:
- `http://127.0.0.1:8787/control-center`

## 3. Erstes Onboarding
Im Control Center:
1. Anzeigename setzen.
2. Telegram-/Discord-Daten eintragen.
3. Optional Distill-Token aktivieren.
4. Ersten Tracker anlegen.
5. Benachrichtigungen mit der Testfunktion pruefen.

Die Daten werden automatisch unter `%APPDATA%\Alertivo` gespeichert:
- `settings.json`
- `trackers\*.json`
- `data\alerts.sqlite`
- `logs\`

## 4. Distill anbinden
Fuer JS-lastige Shops:
1. Im Control Center den gewuenschten Tracker oeffnen.
2. Das generierte Distill-Snippet kopieren.
3. In Distill einen lokalen Monitor anlegen.
4. URL, Header und Body aus dem Snippet uebernehmen.

Der Webhook ist lokal unter `http://127.0.0.1:8787/webhook/distill` erreichbar.

## 5. Alarmkette testen
```powershell
.\scripts\send_test_webhook.ps1
```

Optional gezielt fuer einen Tracker:
```powershell
.\scripts\send_test_webhook.ps1 -TrackerId ps5-pro
```

## 6. Dauerbetrieb
- Die App kann ueber das Tray oder das Control Center gesteuert werden.
- Autostart ist als Einstellung vorgesehen und darf nicht mehr ueber manuell gepflegte `.env`- oder YAML-Dateien erzwungen werden.

## 7. Legacy-Import
Wenn im Installationsverzeichnis noch alte Dateien unter `config\` liegen, importiert Alertivo sie beim ersten Start automatisch in die neue JSON-Struktur. Danach ist `%APPDATA%\Alertivo` die aktive Quelle.
