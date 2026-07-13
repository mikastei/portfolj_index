# CLAUDE.md – Portföljindex

Denna fil läses automatiskt av Claude Code vid sessionstart.

---

## Projekt

**Namn:** Portföljindex
**Syfte:** Bygger ett portföljindex (bas 100) för en eller flera portföljer samt
benchmarkserier, baserat på transaktioner och prisdata från Yahoo Finance.
Producerar även ett BI-underlag för Power BI.
**Ägare:** Mikael Steinholtz, Emsek AB

---

## Arbetssätt

- **Cowork** hanterar resonemang, kravställning och formulering av uppgifter
- **Claude Code** genomför implementation, filändringar, körning och Git
- Båda jobbar mot samma projektmapp

---

## Teknisk miljö

- **Språk:** Python 3.12
- **Venv:** `/Users/mikael/Projects/claude-env/`
- **Aktivera:** `source /Users/mikael/Projects/claude-env/bin/activate`
- **Beroenden:** se `requirements.txt`
- **OS:** macOS (Mac mini M4, "Mac-AI")
- **Kör upstream:** `bash run_main.sh`
- **Kör BI:** `bash run_bi.sh`
- **Kör båda:** `bash run_all.sh`

---

## Konfiguration

Alla sökvägar styrs av `config.toml` i projektroten.
`src/config.py` läser config.toml och exponerar sökvägar till övrig kod.
Ändra aldrig sökvägar hårdkodat i kod – uppdatera config.toml.

---

## Projektstruktur

```
Portföljindex/
  CLAUDE.md                    ← denna fil
  README_portfolio_index.md    ← beskrivning för människor
  config.toml                  ← alla sökvägar samlade här
  requirements.txt
  .gitignore
  run_main.sh                  ← kör src.main (upstream)
  run_bi.sh                    ← kör src.bi_prep (BI-underlag)
  run_all.sh                   ← kör upstream + BI sekventiellt
  src/
    config.py                  ← läser config.toml, exponerar sökvägar
    main.py                    ← upstream pipeline entry point
    portfolio.py               ← portföljlogik
    prices.py                  ← prisnedladdning från Yahoo Finance
    io_excel.py                ← Excel-läsning/skrivning
    outputs.py                 ← output-byggare
    bootstrap.py               ← bootstrapberäkningar
    bi_prep.py                 ← BI-pipeline entry point
    bi_io.py                   ← BI Excel-läsning/skrivning
    bi_metrics.py              ← KPI-beräkningar för BI
  data/
    portfolio_output_timeseries.xlsx  ← upstream output (committas ej)
    portfolio_bi_data.xlsx            ← BI output (committas ej)
  docs/                        ← teknisk dokumentation, Power BI-spec
  tests/                       ← tester och smoke tests
  logs/                        ← körningsloggar
```

---

## Flöde

**Upstream (src.main):**
- Läser `transaktioner.xlsx` (Transactions, Mapping, Portfolio_Metadata, Benchmarks)
- Läser `fonder.xlsx` (fondlista med tickers)
- Hämtar prisdata från Yahoo Finance
- Skriver `data/portfolio_output_timeseries.xlsx`

**BI (src.bi_prep):**
- Läser `data/portfolio_output_timeseries.xlsx`
- Bygger BI-arbetsboken och skriver den till den lokala dataroten,
  `/Users/mikael/Fondanalys-Data/03_Utdata/portfolio_bi_data.xlsx`
  (styrs av `bi_data_local_output` i `config.toml`)

Viktigt: BI-spåret läser **enbart** upstream-outputen, aldrig indatafilerna direkt.

---

## Integration med Fondanalys.xlsm (väg B, sedan cutover 2026-06-30)

Bryggarkitekturen (`_Bridge/`-triggerfiler, launchd-poller, `bridge_orchestrator`-status-JSON)
avvecklades i juni 2026 ([AB]-avvecklingen, se `rollback/bridge-pre-ab`-taggen). Ingen del av
den finns kvar i drift. Dagens flöde är direkt och synkront, utan mellanlagrad kö:

```
VBA i Fondanalys.xlsm (knapp "Uppdatera Power BI data", Modul_Bridge.UppdateraPowerBI)
   └─► AppleScriptTask FaBI.scpt (synkront, VBA väntar in resultatet)
                  │
                  ▼
       fa-bi.sh  →  bash run_all.sh   (src.main → src.bi_prep, i detta repo)
                  │
                  ├─► loggar till Fondanalys-Data/_exchange/logs/
                  └─► skriver lokalt till Fondanalys-Data/03_Utdata/portfolio_bi_data.xlsx
```

Indata (`transaktioner.xlsx`, `fonder.xlsx`) läses direkt från den lokala dataroten
(`02_Indata/` resp. `_exchange/`) via `config.toml` – inget separat exchange-lager i detta repo.

Utöver knapptriggern kör launchd-jobbet `com.emsek.fondanalys.scheduled` en full pipeline
nattligt (06:00) oberoende av VBA-knappen. Detta och övriga schemalagda jobb
(`usa-exposure`, `logrotation`) hanteras i Fondanalys-repots `apps/bridge_orchestrator/`
respektive `apps/backup/` – inte i detta repo. Manuell körning på Mac-AI med
`run_*.sh`-skripten fungerar parallellt och används primärt vid felsökning.

**Power BI nedlagt (2026-07-04, [AQ]):** BI-filen publiceras inte längre till OneDrive.
Den stannar lokalt i `03_Utdata/` och konsumeras enbart av fond-rapporten
(`tools/fond_rapport/` i detta repo). Nattbackupen (`apps/backup/`, 02:30) omfattar
inte BI-filen – den täcker bara masterfilen + `04_Analyser/`.

Datakontrakt: schema_version=1 enligt `_Claude_Output/260426_Design_Steg3_Kontrakt.md` i Fondanalys-OneDrive.

---

## Viktiga regler i datan

- `KOP` = negativt belopp
- `SALJ` = positivt belopp
- Varje ISIN i Transactions måste finnas i Mapping
- Varje ISIN måste ha giltig Category i Mapping

---

## Utvecklingsprinciper

- Enkla lösningar före smarta
- Läsbar kod – skriv för att underhållas
- Små fokuserade ändringar – en logisk sak per commit
- Ändra aldrig filer utanför uppgiftens scope
- Följ befintliga namn- och kodkonventioner

---

## Excel och openpyxl

- `openpyxl` beräknar **inte** Excel-formler
- Spara via openpyxl kan tömma formelcacher
- Läsning med `data_only=True` kräver att giltiga cachevärden redan finns

---

## Git-flöde

```
git pull
# gör ändringar
git add .
git commit -m "Kort beskrivning"
git push
```

---

## Definition av klart

- Koden är ändrad och fungerar som avsett
- config.toml används för alla externa sökvägar
- Inga Windows-sökvägar finns kvar
- Skrivningar till den lokala dataroten (`Fondanalys-Data/03_Utdata/` m.fl.) sker via giltiga sökvägar i `config.toml`, aldrig hårdkodat
- Commit gjord med tydligt meddelande
- Antaganden är redovisade
