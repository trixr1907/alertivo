# Alertivo Desktop

Lokale Windows-Desktop-App fuer Alerts und Monitoring mit:
- `GL.iNet Flint 2 / GL-MT6000`
- `Nvidia RTX 5070 Ti` inklusive AIB-Varianten

Die Kernlogik ist absichtlich nicht auf historische Tiefstpreise ausgelegt. Ein Alert entsteht nur dann, wenn ein neu erkannter Preis unter dem zuletzt gesehenen Preis liegt oder wenn ein neues Listing unter der letzten bekannten Shop-Referenz auftaucht.

## Features
- SQLite-State pro `shop + canonical_model + offer_url`
- Dedupe für identische `shop + canonical_model + price`
- Re-Alert nach Zwischenpreisänderung
- Produkt-Matching für `GL-MT6000` und `RTX 5070 Ti`
- Polling für HTML-Seiten mit CSS-Selektoren
- Webhook-Endpunkt für Distill oder andere lokale Browser-Monitore
- Lokales Control Center mit Live-Status, Event-/Offer-Ansicht und editierbaren Quellenregeln
- Notifier für Telegram, Discord, Windows-Toast, Sound und Konsole

## Projektstruktur
- `src/gpu_alerts/collectors/`: HTML-Poller
- `src/gpu_alerts/matcher.py`: Titel-Normalisierung und Canonical-Mapping
- `src/gpu_alerts/engine.py`: Preislogik, Dedupe, Restock
- `src/gpu_alerts/storage.py`: SQLite
- `src/gpu_alerts/notifiers.py`: Alert-Kanäle
- `src/gpu_alerts/webhook.py`: lokaler Webhook für Distill
- `config/monitor.example.yaml`: Startkonfiguration
- `config/http-sources.example.yaml`: konkrete HTTP-Profile für Geizhals, Alternate, Mindfactory
- `config/distill-profiles.example.yaml`: konkrete Distill-Profile für blockige/JS-lastige Shops
- `docs/shop-matrix.md`: Shop-Matrix mit Strategie und Intervallen
- `scripts/*.ps1`: Windows-Start und Task Scheduler

## Schnellstart unter Windows
1. Python 3.12 installieren.
2. Projektordner öffnen.
3. Optional zuerst alles vorbereiten:

```powershell
.\scripts\setup_ready.ps1 -ConfigPath config/monitor.yaml -EnvPath config/alerts.env.ps1
```

4. In `config/alerts.env.ps1` nur noch Telegram- und Discord-Daten ergänzen.
5. In PowerShell starten:

```powershell
.\scripts\start_alertivo.ps1 -ConfigPath config/monitor.yaml
```

Danach ist das lokale Control Center unter `http://127.0.0.1:8787/control-center` erreichbar.

Eine konkrete Windows-Startanleitung liegt in [windows-live-setup.md](/mnt/c/Users/Ivo/Desktop/GPU/docs/windows-live-setup.md).

## EXE Build (Windows)
Du kannst eine eigenstaendige `Alertivo.exe` bauen:

```powershell
.\scripts\build_exe.ps1
```

Ergebnis:
- `dist\windows\bundle\Alertivo.exe`
- `dist\windows\bundle\run-alertivo.bat`
- `dist\windows\bundle\start-alertivo-hidden.ps1`

`run-alertivo.bat` startet die Desktop-App im Hintergrund (ohne sichtbares Dauer-CMD).
Beim ersten Start erscheint ein minimales KISS-Setup ohne Pflicht-Webhook.

Der Launcher verwendet:
- `config\monitor.yaml`
- `config\alerts.env.ps1`
- `config\user-profile.json`
- `config\monitor-config.json`

Relativ zum Bundle-Ordner. Passe davor `config\alerts.env.ps1` an.

## Distill-Integration für 10-30s Shop-Checks
Die schnellsten direkten Shopchecks solltest du in Distill lokal konfigurieren und das Ergebnis an den lokalen Webhook schicken:

- URL: `http://127.0.0.1:8787/webhook/distill`
- Header: `X-Webhook-Token: <dein WEBHOOK_TOKEN>`
- Body als JSON:

```json
{
  "shop": "mindfactory",
  "source": "shop",
  "scope": "shop_search",
  "title": "ASUS GeForce RTX 5070 Ti TUF OC",
  "url": "https://www.mindfactory.de/product_info.php/...",
  "price": "879,00 €",
  "in_stock": "lagernd",
  "product_hint": "rtx-5070-ti"
}
```

Für `GL.iNet Flint 2`:

```json
{
  "shop": "amazon",
  "source": "shop",
  "scope": "shop_product",
  "title": "GL.iNet GL-MT6000 (Flint 2)",
  "url": "https://www.amazon.de/dp/...",
  "price": "163,99 €",
  "in_stock": "Auf Lager",
  "product_hint": "glinet-flint-2"
}
```

Zum Testen der kompletten lokalen Webhook-Kette:

```powershell
py -3.12 .\scripts\send_test_webhook.py --token $env:WEBHOOK_TOKEN
```

## Konkrete Shopprofile
- Direkte HTTP-Profile: [http-sources.example.yaml](/mnt/c/Users/Ivo/Desktop/GPU/config/http-sources.example.yaml)
- Distill-Profile: [distill-profiles.example.yaml](/mnt/c/Users/Ivo/Desktop/GPU/config/distill-profiles.example.yaml)
- Shop-Matrix und Strategie: [shop-matrix.md](/mnt/c/Users/Ivo/Desktop/GPU/docs/shop-matrix.md)
- konkrete Distill-Checkliste: [distill-checklist.md](/mnt/c/Users/Ivo/Desktop/GPU/docs/distill-checklist.md)
- schnelle Arbeitsliste: [30min-setup-checklist.md](/mnt/c/Users/Ivo/Desktop/GPU/docs/30min-setup-checklist.md)

Empfohlener Minimalbetrieb:
- `Alternate`, `Geizhals` und `Mindfactory` direkt über den Python-Poller
- `Mindfactory` im Repo bewusst über lokalen `curl`-Command-Collector statt normalem HTTP-Client
- `Amazon`, `Caseking`, `NBB`, `Cyberport`, `Galaxus`, `MediaMarkt`, `Saturn`, `Proshop`, `Computeruniverse`, `ASUS Store` über Distill -> Webhook

## Entscheidungslogik
- Bestehendes Angebot:
  - Alert bei `new_price < last_seen_price`
  - Kein erneuter Alert bei identischem Preis, solange dazwischen kein anderer Preis gesehen wurde
- Neues Angebot:
  - Alert bei `new_price < reference_price`
  - `reference_price` ist zuerst der letzte bekannte Preis derselben Canonical-Variante im Shop, sonst der niedrigste bekannte Familienpreis im Shop
- Restock:
  - Optionaler separater Alert bei `out_of_stock -> in_stock`

## Tests

```powershell
py -3.12 -m pip install -e ".[dev]"
py -3.12 -m pytest
```

Abgedeckt sind:
- einfacher Preisdrop
- Dedupe bei gleichem Preis
- erneuter Alert nach Zwischenpreisänderung
- neues günstigeres Listing im selben Shop
- Flint-2-Matching
- RTX-5070-Ti-Canonicalisierung

## Hinweise zum realen Betrieb
- Nutze `Geizhals` und `idealo` als breite Discovery-Layer mit 60-180s Intervall.
- Nutze Distill lokal für 3-8 kritische Shopseiten mit 10-30s Intervall.
- Für GPU-Restocks zusätzlich `FE PartAlert`, `Notify-FE`, `mydealz` und Discord-/Telegram-Dropkanäle abonnieren.
- Bei JS-lastigen Shops ist Distill oft robuster als ein reiner HTML-Poller.
- Viele große Shops liefern aktuell bei direkten Requests `403`, `503` oder Captcha/Challenge. Diese Shops sind bewusst als `Distill-only` dokumentiert statt mit fragilen Poller-Regeln.
