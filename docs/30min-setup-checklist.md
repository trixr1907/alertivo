# 30-Minuten-Setup-Checkliste

## Minute 0-5
- Projekt nach `C:\GPU` legen.
- PowerShell im Projektordner öffnen.
- `config\alerts.env.ps1.example` nach `config\alerts.env.ps1` kopieren.
- In `config\alerts.env.ps1` eintragen:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
  - `DISCORD_WEBHOOK_URL`
  - `WEBHOOK_TOKEN`
  - optional `ALERT_SOUND_FILE`

## Minute 5-8
- Monitor starten:

```powershell
.\scripts\start_monitor.ps1 -ConfigPath config/monitor.yaml
```

- Prüfen, dass der lokale Webhook auf `127.0.0.1:8787` läuft.

## Minute 8-10
- Test-Alert senden:

```powershell
py -3.12 .\scripts\send_test_webhook.py --token $env:WEBHOOK_TOKEN
```

- Prüfen:
  - Windows-Toast
  - Sound
  - Telegram
  - Discord

## Minute 10-18
- Distill lokal öffnen.
- Diese Monitore zuerst anlegen:
  - Amazon RTX 5070 Ti
  - Amazon Flint 2
  - Caseking RTX 5070 Ti
  - MediaMarkt RTX 5070 Ti
  - Saturn RTX 5070 Ti

- Für jeden Monitor:
  - `Local Monitor`
  - Webhook auf `http://127.0.0.1:8787/webhook/distill`
  - Header `X-Webhook-Token`
  - Produktkarten statt kompletter Seite markieren
  - `15s` bei Amazon, Caseking, MediaMarkt, Saturn
  - `20s` bei Flint 2 auf Amazon

## Minute 18-25
- Danach diese Monitore ergänzen:
  - Notebooksbilliger RTX 5070 Ti
  - Cyberport RTX 5070 Ti
  - Galaxus RTX 5070 Ti
  - Proshop RTX 5070 Ti
  - Computeruniverse RTX 5070 Ti
  - ASUS Store RTX 5070 Ti

- Für alle:
  - `20s`
  - Produktname, Preis, Verfügbarkeit, Produktlink extrahieren

## Minute 25-27
- Direkte Poller prüfen:
  - `Geizhals`
  - `Alternate`
  - `Mindfactory`

- Test:

```powershell
py -3.12 -m gpu_alerts.main --config config/monitor.yaml --check-once
```

## Minute 27-30
- Autostart registrieren:

```powershell
.\scripts\register_tasks.ps1 -TaskName GPUPriceAlerts -ConfigPath config/monitor.yaml
```

- Community-Layer parallel abonnieren:
  - FE PartAlert
  - Notify-FE
  - mydealz Such-/Deal-Alarme

## Fertig, wenn
- Test-Webhook lokal ankommt
- Telegram und Discord denselben Test-Alert zeigen
- Windows-Toast und Sound ausgelöst wurden
- Distill-Monitore aktiv sind
- Task Scheduler registriert ist
