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
- Bygger `data/portfolio_bi_data.xlsx`
- Publicerar atomiskt till SharePoint `03_Utdata/portfolio_bi_data.xlsx` för Power BI-konsumtion

Viktigt: BI-spåret läser **enbart** upstream-outputen, aldrig indatafilerna direkt.

---

## Bryggintegration (2026-04-28)

Detta projekt körs inte fristående i drift – det triggas av VBA-knapp i
`Fondanalys.xlsm` (Modul5) via SharePoint-bryggan:

```
VBA i Fondanalys.xlsm
   └─► _Bridge/triggers/portfoljindex_<unix>_<id>.json
                  │
                  ▼
       launchd-poller på Mac-AI (var 30 s)
                  │
                  ▼
       bash run_all.sh   (src.main → src.bi_prep)
                  │
                  ├─► _Bridge/status/portfoljindex.json
                  └─► 03_Utdata/portfolio_bi_data.xlsx (atomic publish)
```

Bryggans orkestrering (poller, jobs, status, heartbeat, scheduled, logrotation) ligger i Fondanalys-repots `apps/bridge_orchestrator/` – inte i detta repo. Manuell körning på Mac-AI med `run_*.sh`-skripten fungerar parallellt och används primärt vid felsökning.

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
- Skrivningar till `_Bridge/` eller `03_Utdata/` använder atomic publish-mönstret
- Commit gjord med tydligt meddelande
- Antaganden är redovisade
