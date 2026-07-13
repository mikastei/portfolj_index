# Portfoljindex

Det har projektet bygger ett portfoljindex (bas 100) for en eller flera portfoljer samt benchmarkserier, baserat pa transaktioner och prisdata fran Yahoo Finance.

Projektet har nu tva spar:

1. gemensamt upstream-spar som bygger den delade kallsanningen
2. BI-spar som bygger ett separat Power BI-underlag fran den delade kallsanningen

## Gemensamt upstream-spar

### Syfte

Det gemensamma sparet bygger den delade kallsanningen for downstream-konsumenter.

Kor:

```bash
bash run_main.sh
```

Input:

- `transaktioner.xlsx`
- `fonder.xlsx`

Viktiga inputtabeller i `transaktioner.xlsx`:

- `Transactions`
- `Mapping`
- `Portfolio_Metadata`
- `Benchmarks`

Viktiga regler:

- `KOP` = negativt belopp
- `SALJ` = positivt belopp
- varje ISIN i `Transactions` maste finnas i `Mapping`
- varje ISIN i `Transactions` maste ha en giltig `Category` i `Mapping`
- for `REAL`-serier anvands `Affarsdag` som transaktionsdatum
- om `Affarsdag` saknar rad i pris-/varderingsindex mappas transaktionen till nasta tillgangliga varderingsdag
- samma effektiva datum anvands for bade positionsuppdatering och cashflow i `REAL` for att undvika datumglapp

Output:

- `data/portfolio_output_timeseries.xlsx`

Workbooken innehaller:

- `Series_Definition`
- `Portfolio_Series_Map`
- `Master_TimeSeries_Long`
- `Run_Config`

Nuvarande gemensamt materialiserad metadata omfattar bland annat:

- portfolj: `Portfolio_Name`, `Index_Start_Date`, `Initial_Index_Value`
- serie: `Series_ID`, `Series_Type`, `Variant`, `Benchmark_ID`
- instrument/serie: `Yahoo_Ticker`, `ISIN`, `Display_Name`, `Price_Currency`, `Instrument_Type`, `Category`
- korning: `Timestamp`, paths, `BASE_CURRENCY`, `RF_RATE_ANNUAL`, `TRADING_DAYS_PER_YEAR`
- struktur-snapshot: `Portfolio_Series_Map` med aktuella vikter per `Series_ID` och ticker

`Master_TimeSeries_Long` ar huvudtabellen for downstream-tidsserier:

- `Date`
- `Series_ID`
- `RET`
- `IDX`
- `DD`

Serietyper:

- `REAL` = faktisk portfoljutveckling fran transaktioner
- `CUR` = modellportfolj baserad pa aktuella vikter
- `TGT` = modellportfolj baserad pa malvikter

  CUR/TGT viktas per dag och normeras om over de fonder som faktiskt har ett pris den
  dagen ([AL1], 2026-07). En fond som saknar pris innan den startade exkluderas de
  dagarna och dess vikt fordelas proportionellt om over ovriga fonder. Tidigare sattes
  avkastningen tyst till 0 % vid full vikt, vilket spade ut portfoljavkastningen under
  fondens for-startperiod och omviktade ovriga utan flagga. Exkluderade fond/periodspann
  loggas som `CUR/TGT-viktning: fond=… saknar pris fore start …`.
- `BM` = benchmarkserie
- `AST` = underliggande tillgangsserie som anvands internt i motorn

Kategoriunika REAL-serier byggs per portfolj och kategori och skrivs till `Series_Definition` samt `Master_TimeSeries_Long`.

## BI-spar

### Syfte

BI-sparet bygger ett separat datakontrakt for Power BI utan att lasa indatafilerna direkt.

Kor:

```bash
bash run_bi.sh
```

Principer for BI v1:

- laser gemensam kalla: `data/portfolio_output_timeseries.xlsx`
- bygger egen downstream-artefakt och skriver den till den lokala dataroten,
  `/Users/mikael/Fondanalys-Data/03_Utdata/portfolio_bi_data.xlsx` (styrs av `bi_data_local_output`
  i `config.toml`); en nattlig backup speglar filen vidare till OneDrive/SharePoint for Power BI
- raknar KPI:er i Python, inte i DAX
- ateranvander inte Excel/dashboard-artefakter

Nuvarande minimal kodstruktur for BI-sparet:

- `src/bi_prep.py`
- `src/bi_io.py`
- `src/bi_metrics.py`

BI-artefakten innehaller:

- `Dim_Date`
- `Dim_Portfolio`
- `Dim_Series`
- `Dim_Instrument`
- `Fact_Series_Daily`
- `Fact_Series_KPI`
- `Fact_Portfolio_Alloc_Snapshot`

Foreslaget BI-datakontrakt och rapportspec finns i:

- `docs/powerbi_spar_plan.md`
- `docs/powerbi_mvp_v1_spec.md`
- `docs/powerbi_dax_v1.md`

## Policyreferenser (passiva tvabucketsindex)

Upstream bygger passiva policyreferenser per portfolj (`POLICY_EGEN` 90/10,
`POLICY_PA` 85/15) i `src/policy.py`, konfigurerade i `config.toml` under
`[policy]`:

- Tva buckets: Aktier = MSCI ACWI inkl. EM (UCITS-ETF `IUSQ.DE`, EUR->SEK) och
  Rantor = kort foretagsobligation (Carnegie Corporate Bond 3 SEK Cap).
  Proxytickers pekas ut via rader i Benchmarks-tabellen i transaktioner.xlsx.
- Fasta strategivikter med arsvis ombalansering: reset till strategivikterna
  1 januari, fri drift inom aret. Viktsumman kontrolleras mot 1,0 varje dag.
- Serierna gar genom BI-sparet till `Dim_Series`/`Fact_Series_Daily`/
  `Fact_Series_KPI` (Series_Type `POLICY`), och fond-rapporten redovisar
  Beta/Alfa/R2 for REAL mot respektive referens (R2-sparr 0,70, preliminar-
  markering tills fonstret rymmer 3 ars historik).
- Oberoende verifiering: `python -m tools.fond_rapport.verify_policy` korskor
  indexnivaerna mot en direkt prisberakning (buy-and-hold-identiteten inom aret).

Referensen speglar det enda avsiktliga strategivalet (aktier/rantor-nivan) -
geografi-, EM- och tematiska val hamnar i alfa. OBS: 4-bucket-mappningen
(Rantor & Lagrisk -> Rantor; Tillvaxtmarknader -> Tillvaxt; geografi Sverige ->
Sverige; ovrigt -> Global) ar en framtida analysdimension for allokerings-
attribution och anvands INTE i referensindexen.

## Hur sparen halls isar

Gemensamt upstream-spar:

- `src/main.py`
- `src/io_excel.py`
- `src/portfolio.py`
- `src/outputs.py`
- `data/portfolio_output_timeseries.xlsx`

BI-spar:

- `src/bi_prep.py`
- `src/bi_io.py`
- `src/bi_metrics.py`
- `/Users/mikael/Fondanalys-Data/03_Utdata/portfolio_bi_data.xlsx` (lokal datarot, styrs av `bi_data_local_output` i `config.toml`)

Viktig princip:

- upstream bygger delad kallsanning
- BI-sparet konsumerar endast denna kalla
- inget kvarvarande steg ska bero pa tidigare Excel/dashboard-artefakter

## Integration med Fondanalys.xlsm (vag B, sedan cutover 2026-06-30)

Den gamla SharePoint-bryggan (`_Bridge/`-triggerfiler, launchd-poller, status-JSON) ar avvecklad
sedan juni 2026 och finns inte langre i drift. Skarp korning triggas nu synkront: VBA-knappen
"Uppdatera Power BI data" i `Fondanalys.xlsm` (`Modul_Bridge.UppdateraPowerBI`) anropar
`AppleScriptTask FaBI.scpt` och vantar in resultatet. Scriptet kor `fa-bi.sh`, som i sin tur kor
`bash run_all.sh` i detta repo (`src.main` -> `src.bi_prep`), loggar till
`Fondanalys-Data/_exchange/logs/` och skriver BI-filen lokalt till `03_Utdata/`.

Utover knapptriggern kor launchd-jobbet `com.emsek.fondanalys.scheduled` en full pipeline
nattligt (06:00), oberoende av VBA-knappen. Ett separat nattligt backup-jobb
(`com.emsek.fondanalys.backup`, 02:30) speglar `03_Utdata/portfolio_bi_data.xlsx` till
OneDrive/SharePoint for Power BI Desktop pa Windows — detta sker automatiskt, inte som ett
manuellt steg. Bade schemaläggning och backup-jobb ligger i Fondanalys-repots
`apps/bridge_orchestrator/` respektive `apps/backup/`, inte i detta repo.

## Sekventiell korning (manuell)

For manuell korning av hela flodet:

```bash
bash run_all.sh
```

Skriptet kor `src.main` foljt av `src.bi_prep`. BI-steget kors bara om upstream lyckas. `run_main.sh` och `run_bi.sh` finns kvar som separata entry points for felsokning.

Den gamla Windows-batchfilen `Portföljindex.bat` ar inte i drift langre och ska stadas bort fran Windows-laptopen (oppen punkt: ta bort gamla obsoleta Python-projektkopior pa Windows-laptopen).

## Tester och hjalpskript

Aktiva projektskript:

- `bash run_main.sh`
- `bash run_bi.sh`
- `bash run_all.sh`

Projektet har nu ingen separat `dev/`-mapp langre. Hjalpskript och verifiering ligger under `tests/`.

Kvarvarande filer i `tests/`:

- automatiserade tester for upstream-logik
- `tests/smoke_test_prices.py` for manuellt tekniskt smoketest av prisnedladdning

## Miljövariabler (strict/debug-lägen)

Fyra flaggor styr strikthet och loggning i upstream-pipelinen. Alla läses via `os.getenv`
vid modulimport, sätts alltså i skalet före `python -m src.main` (t.ex.
`PORTFOLIO_STRICT=1 bash run_main.sh`):

| Variabel | Default | Effekt |
|---|---|---|
| `PRICE_COVERAGE_STRICT` | `1` (strikt) | I `src/prices.py`: om nagon tickers NaN-andel i prisfonstret overstiger 25 % kastas `ValueError`. NaN-andelen mats pa **radata fore forward-fill** ([AX], 2026-07): tidigare kordes ffill (produktionsdefault) forst, vilket fyllde igen interna prisluckor innan den strikta kontrollen hann se dem — kontrollen kunde da i praktiken aldrig losa ut. Fonstret raknas fran varje tickers forsta giltiga kurs, sa ledande luckor innan en fond startade raknas inte (endast luckor *inom* fondens aktiva period). Satt till `0` for att nedgradera till en logg-varning istallet (anvands vid felsokning av enstaka glesa serier). |
| `STRICT_EXTREME_RET` | `1` (strikt) | I `src/portfolio.py`: en extrem daglig avkastning (TWR-utstickare) kastar `ValueError` med fulla diagnostik i loggen. Satt till `0` for att, enbart nar orsaken ar saknade prisdata (`missing_price_tickers`), satta `ret_t=0` for den dagen istallet for att avbryta korningen. |
| `PORTFOLIO_STRICT` | av (ej strikt) | I `src/portfolio.py`: saknad `price_base` for en aktiv REAL-position loggas som varning och vardebidraget blir 0. Satt till `1` for att i stallet kasta `ValueError` direkt. |
| `PORTFOLIO_DEBUG` | av | Slar pa detaljerad varderingsdebugloggning per position. Vilka datum som loggas styrs av `PORTFOLIO_DEBUG_DATES` (kommaseparerad lista, t.ex. `2026-02-18,2026-02-19`; tom = inga datum loggas). Anvands vid felsokning, inte i skarp drift. |

**Stallningstagande (AL3):** `PRICE_COVERAGE_STRICT` och `STRICT_EXTREME_RET` failar redan
hogt som standard, men `PORTFOLIO_STRICT` gor det inte — asymmetriskt. Principiellt bor alla
tre "hard fail on bad data"-flaggorna vara strikta som standard for att undvika tysta
felvarderingar. Vi flippar INTE `PORTFOLIO_STRICT`-defaulten i denna lagrisk-batch, eftersom
det skulle kunna gora en tyst varning i dagens produktionskorning till ett hart fel utan att vi
forst har verifierat hur ofta `missing_price_base`-varningen faktiskt trigger pa skarp data.
Rekommendation: kor en produktionsvecka med `PORTFOLIO_STRICT=1` manuellt och granska loggen
innan defaulten andras i kod.

## Vanliga fel

### Saknad mapping

`Missing Mapping for ISIN`

### Saknad kategori i mapping

`Missing Category for ISIN(s)`

### Fel Yahoo-ticker

Ger saknade prisserier eller tom data.

### Fel tecken pa belopp

- `KOP` ska vara negativt
- `SALJ` ska vara positivt

Fel tecken kan skapa stora hopp i indexserierna.

---

Senast uppdaterad: 2026-04-29
