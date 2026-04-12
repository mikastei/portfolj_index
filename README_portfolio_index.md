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
py -m src.main
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
- `BM` = benchmarkserie
- `AST` = underliggande tillgangsserie som anvands internt i motorn

Kategoriunika REAL-serier byggs per portfolj och kategori och skrivs till `Series_Definition` samt `Master_TimeSeries_Long`.

## BI-spar

### Syfte

BI-sparet bygger ett separat datakontrakt for Power BI utan att lasa indatafilerna direkt.

Kor:

```bash
py -m src.bi_prep
```

Principer for BI v1:

- laser gemensam kalla: `data/portfolio_output_timeseries.xlsx`
- bygger egen downstream-artefakt: `data/portfolio_bi_data.xlsx`
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
- `data/portfolio_bi_data.xlsx`

Viktig princip:

- upstream bygger delad kallsanning
- BI-sparet konsumerar endast denna kalla
- inget kvarvarande steg ska bero pa tidigare Excel/dashboard-artefakter

## Batchkorning

`Portföljindex.bat` kor nu standardflodet sekventiellt:

```bash
py -m src.main
py -m src.bi_prep
```

`src.bi_prep` kors bara om `src.main` lyckas. BI-sparet finns fortfarande kvar som separat entry point for manuell felsokning eller om BI-underlaget ska byggas om fran befintlig upstream-fil.

## Tester och hjalpskript

Aktiva projektskript:

- `py -m src.main`
- `py -m src.bi_prep`
- `Portföljindex.bat`

Projektet har nu ingen separat `dev/`-mapp langre. Hjalpskript och verifiering ligger under `tests/`.

Kvarvarande filer i `tests/`:

- automatiserade tester for upstream-logik
- `tests/smoke_test_prices.py` for manuellt tekniskt smoketest av prisnedladdning

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

Senast uppdaterad: 2026-04-12
