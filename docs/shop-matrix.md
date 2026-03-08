# Shop-Matrix und operative Profile

## Ziel
Diese Matrix priorisiert die Quellen für die frühesten Alerts auf Windows und legt fest, ob ein Shop direkt per HTTP oder besser per lokalem Distill-Monitor überwacht wird.

## Aktuelle Einordnung
| Shop | Produktfokus | Strategie | Intervall | Begründung |
|---|---|---|---:|---|
| Geizhals | Flint 2, RTX 5070 Ti | HTTP | 90s | Stabiler Discovery-Layer, gute Händlerabdeckung |
| Alternate | RTX 5070 Ti | HTTP oder Distill | 20-30s | Aktuell gut serverseitig parsebar |
| Mindfactory | RTX 5070 Ti | Command-Collector oder Distill | 20-30s | HTML parsebar, aber normaler HTTP-Client kann 403 bekommen |
| Amazon | Flint 2, RTX 5070 Ti | Distill | 15-20s | Direkte Requests liefern Anti-Bot/503 |
| Caseking | RTX 5070 Ti | Distill | 15-20s | Cloudflare-Challenge |
| NBB | RTX 5070 Ti | Distill | 20s | Direkte Requests aktuell 403 |
| Cyberport | RTX 5070 Ti | Distill | 20s | HTML im Test nicht stabil parsebar |
| Galaxus | RTX 5070 Ti | Distill | 20s | Captcha-Seite bei direktem Request |
| Proshop | RTX 5070 Ti | Distill | 20s | Cloudflare-Challenge |
| Computeruniverse | RTX 5070 Ti | Distill | 20s | Cloudflare-Challenge |
| MediaMarkt | RTX 5070 Ti | Distill | 20s | Cloudflare-Challenge |
| Saturn | RTX 5070 Ti | Distill | 20s | Cloudflare-Challenge |
| ASUS Store | RTX 5070 Ti | Distill | 20s | Shopstruktur variiert, Browserweg robuster |

## Direkt parsebare Quellen
### Alternate
- URL: `https://www.alternate.de/Grafikkarten/NVIDIA-Grafikkarten/RTX-5070-Ti`
- Aktuell brauchbare Selektoren:
  - `item_selector`: `a.card.productBox`
  - `title_selector`: `.product-name`
  - `price_selector`: `.price`
  - `stock_selector`: `.delivery-info`
- Eignung:
  - gut für neue Listings
  - gut für Preisänderungen
  - Verfügbarkeit ist auf der Kategorieseite sichtbar

### Mindfactory
- URL: `https://www.mindfactory.de/search_result.php?search_query=rtx+5070+ti`
- Aktuell brauchbare Selektoren:
  - `item_selector`: `div.p`
  - `title_selector`: `.pname`
  - `price_selector`: `.pprice`
  - `link_selector`: `a.phover-complete-link, a.p-complete-link`
  - `stock_selector`: `.pshipping span`
- Hinweise:
  - `Lagernd` ist direkt sichtbar
  - `Zum Warenkorb` kann zusätzlich als positiver Stock-Hinweis dienen
  - Im Repo ist Mindfactory bewusst als `command`-Collector via lokalem `curl` konfiguriert, nicht als normaler `aiohttp`-Fetcher

### Geizhals
- Produkt-PDPs mit Händlerliste sind gut für Discovery und sekundäre Preisbestätigung.
- Aktuell brauchbare Selektoren:
  - `title_selector`: `h1.variant__header__headline`
  - `price_selector`: `#pricerange-min .gh_price, .offer__price .gh_price`
  - `stock_selector`: `.offer__delivery-time, #pricerange-no-offers`

## Distill-Standardprofil pro Shop
Für alle Distill-Shops gilt derselbe minimale JSON-Body an den lokalen Webhook:

```json
{
  "shop": "caseking",
  "source": "shop",
  "scope": "shop_search",
  "title": "MSI GeForce RTX 5070 Ti Gaming Trio OC",
  "url": "https://www.caseking.de/...",
  "price": "1039,00 €",
  "in_stock": "Auf Lager",
  "product_hint": "rtx-5070-ti"
}
```

Für Flint 2:

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

## Praktische Distill-Regeln
- Für RTX 5070 Ti immer zuerst Such-/Kategorie-Seiten überwachen, nicht nur einzelne PDPs.
- Pro Shop 10-20 relevante Karten überwachen, nicht die komplette Seite visuell.
- Preis und Stock als getrennte Extraktionsfelder definieren.
- Bei Shops mit Captcha/Challenge immer die lokale Browser-Session eingeloggt und warm halten.
- Wenn ein Shop häufig Soft-Blocks auslöst, Intervall von `15s` auf `25-30s` erhöhen.

## Priorisierung für den Live-Betrieb
1. Distill auf `Amazon`, `Caseking`, `MediaMarkt`, `Saturn`, `Galaxus`, `Cyberport`.
2. Direkter Poller für `Alternate`, `Mindfactory`, `Geizhals`.
3. Community-Layer zusätzlich auf `FE PartAlert`, `Notify-FE`, `mydealz`.
