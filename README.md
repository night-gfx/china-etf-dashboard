# China ETF Index Dashboard

Streamlit-Dashboard zum Vergleich von China-Indizes über in Europa verfügbare UCITS-ETF-Proxys.

## Kernlogik

- **Indizes vergleichen:** pro Index wird automatisch der ETF mit dem frühesten Fonds-Auflegungsdatum verwendet, sofern Yahoo Finance für einen hinterlegten Börsenticker historische Daten liefert.
- **ETFs innerhalb eines Index vergleichen:** mehrere ETFs desselben Index können direkt miteinander verglichen werden.
- Beschriftung immer als **`ETF-Name (Indexname)`**.
- **Total Return:** Yahoo `Adj Close` als Näherung für eine wiederangelegte Ausschüttungs-/Split-bereinigte Wertentwicklung.
- **EUR-Basis:** bevorzugt Xetra/EUR; Fallback-Listings werden nach Möglichkeit über Yahoo-FX in EUR umgerechnet.
- **Steueransicht:** vereinfachter deutscher Nach-Steuer-Liquidationswert, standardmäßig 25 % Kapitalertragsteuer + 5,5 % Soli darauf und 30 % Teilfreistellung für Aktienfonds = 18,4625 % effektiver Satz auf positive Gewinne. Alle Parameter sind im Dashboard veränderbar.

## Layout

Oben nebeneinander:

1. **Indexierte Wertentwicklung** (Start = 100)
2. **Drawdown**

Darunter nebeneinander:

3. **P.a. / Jahresperformance & Information Ratio**
4. **Gesamtperiode – Performance- und Risikokennzahlen**

Die Information Ratio wird relativ zum ältesten in der aktuellen Auswahl verfügbaren ETF-Proxy berechnet.

## Start lokal

```bash
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

## Datenquellen

- ETF-/Index-Zuordnung und Fonds-Auflegungsdaten: justETF bzw. Anbieter-Factsheets (siehe `data_etfs.csv`, Spalte `index_url`).
- Historische Marktpreise: Yahoo Finance über `yfinance`.

## Wichtige Einschränkungen

### ETF-Proxy statt offizieller Indexserie

Das Dashboard zeigt die realisierte Marktwertentwicklung der ETF-Proxys, nicht die offizielle Index-Total-Return-Serie. TER, Tracking Difference, Handelsplatz, Bid/Ask-Effekte und ggf. FX-Effekte können daher Abweichungen zum Index erzeugen.

### Steueransicht

Die Nach-Steuer-Serie ist eine **Szenariorechnung**: positive kumulierte Gewinne werden so behandelt, als würde an jedem Datum vollständig liquidiert und der eingestellte effektive Steuersatz fällig. Nicht modelliert werden insbesondere Vorabpauschale, Sparer-Pauschbetrag, Kirchensteuer, individuelle Verlustverrechnung und die exakte Besteuerung jeder Ausschüttung.

### Yahoo Finance

Yahoo-Ticker können sich ändern oder zeitweise keine Daten liefern. `data_etfs.csv` enthält deshalb mehrere Ticker-Kandidaten. Der erste funktionierende Kandidat wird verwendet.

## Deployment auf Streamlit Community Cloud

1. Dieses Verzeichnis in ein GitHub-Repository pushen.
2. In Streamlit Community Cloud `app.py` als Entry Point auswählen.
3. Keine Secrets sind erforderlich.
