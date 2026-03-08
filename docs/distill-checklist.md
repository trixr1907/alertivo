# Distill-Checkliste pro Shop

Diese Checkliste ist für den schnellen Live-Aufbau gedacht. Sie priorisiert die Shops, bei denen lokale Browser-Checks auf Windows den größten Zeitvorteil bringen.

## Globale Distill-Einstellungen

Für alle Monitore:
- Modus: `Local Monitor`
- Browser: dein normaler Windows-Browser mit aktiver Session
- Benachrichtigung: `Webhook`
- Webhook-URL: `http://127.0.0.1:8787/webhook/distill`
- Header: `X-Webhook-Token: <WEBHOOK_TOKEN>`
- Trigger: sofort bei Änderung
- Beobachtungsstil:
  - bei Such-/Kategorie-Seiten immer die ersten relevanten Produktkarten
  - nicht den kompletten Seitenbody überwachen
  - Preis und Verfügbarkeit getrennt extrahieren, wenn Distill das zulässt

## Gemeinsame Payload-Felder

Jeder Distill-Monitor soll diese Informationen an den lokalen Webhook liefern:
- `shop`
- `source`
- `scope`
- `title`
- `url`
- `price`
- `in_stock`
- `product_hint`

RTX-5070-Ti-Monitore:

```json
{
  "shop": "caseking",
  "source": "shop",
  "scope": "shop_search",
  "title": "<Produktname>",
  "url": "<Produktlink>",
  "price": "<Preistext>",
  "in_stock": "<Verfügbarkeitstext>",
  "product_hint": "rtx-5070-ti"
}
```

Flint-2-Monitore:

```json
{
  "shop": "amazon",
  "source": "shop",
  "scope": "shop_product",
  "title": "<Produktname>",
  "url": "<Produktlink>",
  "price": "<Preistext>",
  "in_stock": "<Verfügbarkeitstext>",
  "product_hint": "glinet-flint-2"
}
```

eBay-RTX-5070-Ti-Monitor:

```json
{
  "shop": "ebay",
  "source": "shop",
  "scope": "shop_search",
  "title": "<Produktname>",
  "url": "<Produktlink>",
  "price": "<Preistext>",
  "in_stock": "Sofort-Kaufen",
  "product_hint": "rtx-5070-ti",
  "exclude_title_terms": ["defekt", "bastler", "reparatur", "beschädigt", "beschadigt", "ersatzteil"]
}
```

## Priorität A: zuerst anlegen

### 1. Amazon RTX 5070 Ti
- URL: `https://www.amazon.de/s?k=rtx+5070+ti`
- Intervall: `15s`
- Scope: `shop_search`
- Produkt-Hint: `rtx-5070-ti`
- Beobachten:
  - erste 10-20 Suchkarten
  - pro Karte Produktname, Preis, Lieferstatus
- Ziel:
  - neue Listings sehr früh sehen
  - Preisdrops in Suchergebnissen sofort mitnehmen
- Hinweis:
  - Falls Amazon Captcha zeigt, Browser-Session offen halten und Intervall notfalls auf `20s` erhöhen

### 2. Amazon Flint 2
- URL: `https://www.amazon.de/s?k=gl-mt6000`
- Intervall: `20s`
- Scope: `shop_search` oder `shop_product`
- Produkt-Hint: `glinet-flint-2`
- Beobachten:
  - GL-MT6000 / Flint 2 Suchkarte oder dedizierte Produktseite
  - Preis
  - `Auf Lager` / Lieferzeit

### 3. Caseking RTX 5070 Ti
- URL: `https://www.caseking.de/search?search=rtx+5070+ti`
- Intervall: `15s`
- Scope: `shop_search`
- Produkt-Hint: `rtx-5070-ti`
- Beobachten:
  - Trefferliste
  - Name, Preis, Lagerampel/Lagertext
- Hinweis:
  - Distill im eingeloggten Browser verwenden, weil direkte Requests aktuell Cloudflare-challenged sind

### 4. MediaMarkt RTX 5070 Ti
- URL: `https://www.mediamarkt.de/de/search.html?query=rtx%205070%20ti`
- Intervall: `15s`
- Scope: `shop_search`
- Produkt-Hint: `rtx-5070-ti`
- Beobachten:
  - Suchtrefferliste
  - Preis
  - Lieferstatus

### 5. Saturn RTX 5070 Ti
- URL: `https://www.saturn.de/de/search.html?query=rtx%205070%20ti`
- Intervall: `15s`
- Scope: `shop_search`
- Produkt-Hint: `rtx-5070-ti`
- Beobachten:
  - Suchtrefferliste
  - Preis
  - Lieferstatus

### 6. eBay RTX 5070 Ti Sofort-Kaufen
- URL: `https://www.ebay.de/sch/i.html?_nkw=rtx+5070+ti+-defekt+-bastler+-reparatur+-besch%C3%A4digt&_sacat=27386&LH_BIN=1&LH_ItemCondition=1000&rt=nc&LH_PrefLoc=3`
- Intervall: `20s`
- Scope: `shop_search`
- Produkt-Hint: `rtx-5070-ti`
- Beobachten:
  - Suchtrefferliste
  - nur `Sofort-Kaufen`
  - sichtbarer Preis und Produktlink
- Hinweis:
  - eBay blockt direkte HTML-Requests, deshalb hier bewusst Distill im lokalen Browser nutzen
  - im Payload die `exclude_title_terms` mitschicken, damit Defekt-/Bastler-Angebote serverseitig verworfen werden

## Priorität B: danach anlegen

### 7. Notebooksbilliger RTX 5070 Ti
- URL: `https://www.notebooksbilliger.de/search?q=rtx+5070+ti`
- Intervall: `20s`
- Scope: `shop_search`
- Produkt-Hint: `rtx-5070-ti`
- Beobachten:
  - Trefferliste
  - Produktname, Preis, Verfügbarkeit

### 8. Cyberport RTX 5070 Ti
- URL: `https://www.cyberport.de/search.html?query=rtx+5070+ti`
- Intervall: `20s`
- Scope: `shop_search`
- Produkt-Hint: `rtx-5070-ti`
- Beobachten:
  - Trefferliste oder einzelne PDPs der wichtigsten Modelle
  - Preis
  - Verfügbarkeit

### 9. Galaxus RTX 5070 Ti
- URL: `https://www.galaxus.de/de/search?q=rtx%205070%20ti`
- Intervall: `20s`
- Scope: `shop_search`
- Produkt-Hint: `rtx-5070-ti`
- Beobachten:
  - gerenderte Trefferliste
  - Preis
  - Lieferstatus
- Hinweis:
  - Direkte Requests landen aktuell auf Captcha, Browserweg ist Pflicht

### 10. Proshop RTX 5070 Ti
- URL: `https://www.proshop.de/?s=rtx%205070%20ti`
- Intervall: `20s`
- Scope: `shop_search`
- Produkt-Hint: `rtx-5070-ti`
- Beobachten:
  - Trefferliste
  - Preis
  - Verfügbarkeit

### 11. Computeruniverse RTX 5070 Ti
- URL: `https://www.computeruniverse.net/de/search?query=rtx%205070%20ti`
- Intervall: `20s`
- Scope: `shop_search`
- Produkt-Hint: `rtx-5070-ti`
- Beobachten:
  - Trefferliste
  - Preis
  - Lieferstatus

### 12. ASUS Store RTX 5070 Ti
- URL: `https://webshop.asus.com/de/`
- Intervall: `20s`
- Scope: `shop_search`
- Produkt-Hint: `rtx-5070-ti`
- Beobachten:
  - Suche oder dedizierte GPU-Kategorie
  - Preis
  - Verfügbarkeit

## Was du in Distill konkret auswählen sollst

### Such-/Kategorie-Seiten
- erst die Produktliste eingrenzen
- dann je Karte:
  - `title`: sichtbarer Produktname
  - `price`: sichtbarer Preis
  - `in_stock`: sichtbarer Lager-/Liefertext
  - `url`: Produktlink

### Produktdetailseiten
- `title`: H1 oder Produkttitel
- `price`: Hauptpreis
- `in_stock`: Buy-Box-/Lagertext
- `url`: aktuelle Seiten-URL

## Was du nicht tun solltest
- nicht die ganze Seite ohne Eingrenzung überwachen
- keine Werbebanner, Countdown-Elemente oder Popups einschließen
- keine Empfehlungsslider überwachen
- keine Sortier- oder Filterelemente als Triggerquelle nehmen

## Empfohlene Reihenfolge für 30 Minuten Setup
1. Amazon RTX 5070 Ti
2. Amazon Flint 2
3. Caseking RTX 5070 Ti
4. MediaMarkt RTX 5070 Ti
5. Saturn RTX 5070 Ti
6. eBay RTX 5070 Ti Sofort-Kaufen
7. Notebooksbilliger RTX 5070 Ti
8. Cyberport RTX 5070 Ti
9. Galaxus RTX 5070 Ti
10. Proshop RTX 5070 Ti
11. Computeruniverse RTX 5070 Ti
12. ASUS Store RTX 5070 Ti

## Nachkontrolle nach dem Anlegen
- Test-Webhook senden
- prüfen, ob in Telegram und Discord derselbe Alert ankommt
- einen Dummy-Preiswechsel simulieren oder einen bestehenden Payload erneut mit geändertem Preis schicken
- bei Shops mit zu vielen False Positives nur die Kartenliste enger markieren
