# Distill-Checkliste pro Shop

Die aktuelle App erzeugt Distill-Snippets direkt im Control Center. Diese Checkliste beschreibt nur noch den generischen Ablauf.

## Globale Distill-Einstellungen
- Modus: `Local Monitor`
- Browser: normaler Windows-Browser mit aktiver Session
- Benachrichtigung: `Webhook`
- Webhook-URL: `http://127.0.0.1:8787/webhook/distill`
- Header: `X-Webhook-Token` nur setzen, wenn im Control Center ein Distill-Token hinterlegt ist
- Trigger: sofort bei Aenderung

## Beobachtungsstil
- Bei Such- und Kategorie-Seiten einzelne Produktkarten statt den kompletten Seitenbody waehlen
- Wenn moeglich Titel, Preis, Verfuegbarkeit und URL getrennt extrahieren
- Nur so viele Karten ueberwachen, wie fuer den Tracker fachlich sinnvoll sind

## Minimalablauf
1. Tracker im Control Center anlegen
2. Distill-faehigen Shop im Tracker aktivieren
3. Im Bereich `Distill Snippets` den JSON-Block kopieren
4. In Distill URL, Header und Body uebernehmen
5. Testlauf mit einer lokalen Aenderung oder einem manuellen Webhook-Call pruefen

## Beispiel fuer sinnvolle Shop-Klassen
- Suchseiten grosser Haendler
- Kategorie-Seiten mit schneller Sicht auf neue Listings
- einzelne Produktseiten nur dann, wenn ein Shop keine brauchbare Suche hat

## Wann Distill sinnvoll ist
- Shop liefert Cloudflare-, Captcha- oder Anti-Bot-Seiten
- Trefferliste wird erst im Browser gerendert
- eingeloggte Session oder Standortkontext beeinflusst Preis oder Bestand

## Wann direkter HTTP-/Command-Collector reicht
- HTML ist serverseitig stabil und direkt parsebar
- keine Anti-Bot-Blockaden im praktischen Betrieb
- 20-60 Sekunden Intervall sind ausreichend
