# Windows Live Setup

## 1. Dateien vorbereiten
- Projekt nach `C:\GPU` oder einen anderen festen Pfad legen.
- Optional zuerst alles automatisch vorbereiten:

```powershell
.\scripts\setup_ready.ps1 -ConfigPath config/monitor.yaml -EnvPath config/alerts.env.ps1
```

- Danach nur noch Telegram-/Discord-Werte in `config\alerts.env.ps1` eintragen.

## 2. Direkte Poller starten
Diese sind in [monitor.yaml](/mnt/c/Users/Ivo/Desktop/GPU/config/monitor.yaml) schon aktiv:
- `Geizhals` für Flint 2
- `Geizhals` für RTX-5070-Ti-Referenz
- `Alternate` für neue GPU-Listings / Preisdrops
- `Mindfactory` für neue GPU-Listings / Preisdrops

## 3. Distill für die schnellen Blocker-Shops
In Distill lokal je einen Monitor anlegen für:
- `Amazon` RTX 5070 Ti Suchseite
- `Amazon` GL-MT6000 / Flint 2 Suchseite oder Produktseite
- `Caseking` RTX 5070 Ti Suche
- `Notebooksbilliger` RTX 5070 Ti Suche
- `Cyberport` RTX 5070 Ti Suche
- `Galaxus` RTX 5070 Ti Suche
- `MediaMarkt` RTX 5070 Ti Suche
- `Saturn` RTX 5070 Ti Suche
- `Proshop` RTX 5070 Ti Suche
- `Computeruniverse` RTX 5070 Ti Suche
- `ASUS Store` RTX 5070 Ti Suche/Kategorie

Webhook in Distill:
- URL: `http://127.0.0.1:8787/webhook/distill`
- Header: `X-Webhook-Token: <WEBHOOK_TOKEN>`
- Intervall:
  - `15s` für Amazon, Caseking, MediaMarkt, Saturn
  - `20s` für NBB, Cyberport, Galaxus, Proshop, Computeruniverse, ASUS Store

## 4. Start unter Windows
PowerShell im Projektordner:

```powershell
.\scripts\start_monitor.ps1 -ConfigPath config/monitor.yaml
```

## 5. Alarmkette testen
Lokalen Webhook testen:

```powershell
py -3.12 .\scripts\send_test_webhook.py --token $env:WEBHOOK_TOKEN
```

Wenn alles richtig ist, bekommst du:
- Konsolen-Output
- Windows-Toast
- Sound
- Telegram
- Discord

## 6. Dauerbetrieb
Task Scheduler registrieren:

```powershell
.\scripts\register_tasks.ps1 -TaskName GPUPriceAlerts -ConfigPath config/monitor.yaml
```

## 7. Empfohlene Live-Reihenfolge
1. `Alternate` und `Mindfactory` direkt laufen lassen.
2. Distill für `Amazon`, `Caseking`, `MediaMarkt`, `Saturn`.
3. Danach `NBB`, `Cyberport`, `Galaxus`, `Proshop`, `Computeruniverse`, `ASUS Store`.
4. Community-Layer parallel abonnieren: `FE PartAlert`, `Notify-FE`, `mydealz`.
