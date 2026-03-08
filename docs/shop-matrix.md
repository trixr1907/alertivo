# Shop-Matrix und operative Profile

Diese Matrix ist jetzt generisch formuliert. Die aktuelle App arbeitet mit Trackern im Control Center; die Matrix beschreibt nur noch die typischen Strategien pro Shop-Typ.

## Grundprinzip
- Suchseiten und Kategorie-Seiten sind fuer neue Listings meist besser als einzelne Produktseiten.
- Serverseitig parsebare Shops koennen direkt per HTTP oder Command-Collector laufen.
- JS-lastige oder challenge-geschuetzte Shops sollten lokal ueber Distill und den Alertivo-Webhook laufen.

## Typische Einordnung
| Shop-Typ | Strategie | Intervall | Begründung |
|---|---|---:|---|
| Aggregatoren wie Geizhals oder billiger.de | HTTP | 60-180s | Gute Discovery-Layer, stabile HTML-Struktur |
| Shops mit statischer Suche/Kategorie | HTTP oder Distill | 20-60s | Direkt parsebar, Distill als Fallback |
| Shops mit Cloudflare, Captcha oder starker Client-Logik | Distill | 10-30s | Browser-Kontext ist robuster als direkter Request |
| Shops mit restriktiven User-Agent-/Bot-Regeln | Command oder Distill | 20-60s | Curl/Browser ist oft stabiler als normaler HTTP-Client |

## Felder fuer den lokalen Webhook
Das Control Center erzeugt diese Werte heute automatisch pro Tracker und Shop. Falls du den Body manuell nachvollziehen willst, besteht er aus:

```json
{
  "shop": "amazon",
  "source": "shop",
  "scope": "shop_search",
  "title": "Sample Console Pro",
  "url": "https://example.com/product",
  "price": "499,00 EUR",
  "in_stock": "Auf Lager",
  "product_hint": "console-pro",
  "include_title_terms": ["console", "pro"],
  "exclude_title_terms": ["bundle", "gebraucht"],
  "price_ceiling": 549,
  "new_listing_price_below": null
}
```

## Auswahlhilfe fuer neue Tracker
1. Zuerst 1-2 breite Discovery-Quellen auswaehlen.
2. Danach 2-4 schnelle Distill-Monitore fuer kritische Shops ergaenzen.
3. Exclude-Terms direkt im Tracker pflegen, statt auf implizite Produktlogik zu bauen.
4. Preisobergrenzen und `new_listing_price_below` nur dort setzen, wo sie fachlich sinnvoll sind.
