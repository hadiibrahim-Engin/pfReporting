# freischaltung – Automatische Freischaltungsbewertung

Python-Paket zur automatischen Bewertung von Schalthandlungen (Freischaltungen) in PowerFactory.
Erzeugt nach einer Quasi-Dynamic-Simulation einen vollständig portablen, interaktiven HTML-Report.

---

## Schnellstart

```bash
# Abhängigkeiten installieren
uv sync

# Vendor-JS für Offline-Betrieb herunterladen
uv run python scripts/download_assets.py

# Demo-Report erzeugen (kein PowerFactory erforderlich)
uv run freischaltung-report generate --mock --output-dir ./output
```

---

## Paketstruktur

```
freischaltung_report/
├── pyproject.toml
├── cli.py                         Typer-CLI (freischaltung-report)
├── run_in_powerfactory.py         PF-IntScript-Einstieg
├── scripts/
│   └── download_assets.py        Lädt Chart.js-Vendor-Dateien herunter
├── tests/                         pytest-Testsuite
└── freischaltung/
    ├── config.py                  Konfiguration (Pydantic v2)
    ├── models.py                  Ergebnismodelle (Pydantic v2)
    ├── reader.py                  PowerFactory-API-Wrapper
    ├── analysis.py                Grenzwertanalyse
    ├── _mock_data.py              Demo-Daten (--mock / Tests)
    └── report/
        ├── builder.py             Datensammlung (ReportData)
        ├── generator.py           HTML-Generierung (Jinja2)
        ├── assets/                CSS, JS, Vendor-Dateien
        └── templates/             Jinja2-Templates
```

---

## Verwendung in PowerFactory

1. Paket in das PF-Python-Verzeichnis kopieren oder installieren:
   ```bash
   pip install -e .  # oder: uv pip install -e .
   ```

2. `run_in_powerfactory.py` als IntScript in PowerFactory anlegen.

3. Grenzwerte und Visualisierungen in der `CONFIG`-Variable anpassen.

4. Skript ausführen – der Report wird automatisch gespeichert.

---

## Konfiguration

Alle Parameter werden über `FreischaltungConfig` gesteuert (Pydantic v2):

```python
from freischaltung.config import FreischaltungConfig, VizRequest

config = FreischaltungConfig(
    voltage={"lower_warning": 0.95, "lower_violation": 0.90,
             "upper_warning": 1.05, "upper_violation": 1.10},
    thermal={"warning_pct": 80.0, "violation_pct": 100.0},
    report={"output_dir": r"C:\PF_Reports", "company": "Mein Unternehmen"},
    visualizations=[
        VizRequest(element_class="ElmLne", variable="c:loading",
                   label="Auslastung", unit="%",
                   warn_hi=80.0, violation_hi=100.0, heatmap=True),
        VizRequest(element_class="ElmLne", variable="m:P:bus1",
                   label="Wirkleistung", unit="MW"),
        # weitere Zeitreihen nach Bedarf …
    ],
)
```

Oder als JSON-Datei übergeben:
```bash
freischaltung-report generate --config meine_config.json
```

### Verfügbare Zeitreihenvariablen (PowerFactory)

| Variable       | Beschreibung          | Einheit |
|----------------|-----------------------|---------|
| `c:loading`    | Thermische Auslastung | %       |
| `m:u`          | Spannung              | p.u.    |
| `m:i1:bus1`    | Strom                 | kA      |
| `m:P:bus1`     | Wirkleistung          | MW      |
| `m:Q:bus1`     | Blindleistung         | Mvar    |

Jede `VizRequest` erzeugt einen eigenen Linien-Chart-Abschnitt im Report.
Mit `heatmap=True` wird zusätzlich eine Heatmap (Elemente × Zeit) angezeigt.

---

## CLI

```
freischaltung-report generate [OPTIONEN]

Optionen:
  --config  PATH      JSON-Konfigurationsdatei
  --output-dir PATH   Ausgabeverzeichnis
  --mock              Demo-Report ohne PowerFactory
  --pdf               Zusätzlicher PDF-Export (pip install freischaltung[pdf])
```

---

## Tests

```bash
uv run pytest tests/ -v
```

---

## Abhängigkeiten

| Paket    | Version  | Zweck                    |
|----------|----------|--------------------------|
| jinja2   | ≥ 3.1    | HTML-Templates           |
| pydantic | ≥ 2.0    | Konfiguration & Modelle  |
| typer    | ≥ 0.12   | CLI                      |
| rich     | ≥ 13     | Logging & Konsolenausgabe|

Optional:
- `weasyprint ≥ 61` – PDF-Export (`pip install freischaltung[pdf]`)
