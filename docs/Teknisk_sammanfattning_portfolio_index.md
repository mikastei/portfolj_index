# Teknisk sammanfattning for Portfolio_index och BI_prep

## 1. Relevanta filer och mappar

```text
Portfoljindex/
├─ src/
│  ├─ main.py
│  ├─ bi_prep.py
│  ├─ bi_io.py
│  ├─ bi_metrics.py
│  ├─ config.py
│  ├─ io_excel.py
│  ├─ portfolio.py
│  ├─ prices.py
│  ├─ outputs.py
│  ├─ bootstrap.py
│  └─ __init__.py
├─ data/
│  ├─ cache_prices.parquet
│  ├─ portfolio_output_timeseries.xlsx
│  └─ portfolio_bi_data.xlsx
├─ docs/
├─ logs/
├─ Portföljindex.bat
├─ README_portfolio_index.md
├─ tests/
└─ requirements.txt
```

## 2. Entry points och korordning

Primara entry points:

- `src/main.py` -> `py -m src.main`
- `src/bi_prep.py` -> `py -m src.bi_prep`

Rekommenderad korordning:

1. kor `py -m src.main`
2. kor `py -m src.bi_prep`

Batchkorning via `Portföljindex.bat`:

- aktiverar `.venv`
- kor `py -m src.main`
- kor `py -m src.bi_prep` om steg 1 lyckas
- loggar korningen till `logs/`

## 3. Modulansvar i `src`

Upstream:

- `main.py`: orchestration for gemensamt upstream-steg
- `io_excel.py`: lasning och validering av inputtabeller
- `portfolio.py`: bygger portfolio-, benchmark- och interna asset-serier
- `prices.py`: Yahoo-download, FX och returserier
- `outputs.py`: bygger och skriver `portfolio_output_timeseries.xlsx`
- `bootstrap.py`: SSL-init for Windows

BI:

- `bi_prep.py`: orchestration for separat BI-datakontrakt
- `bi_io.py`: inlasning och validering av upstream-workbooken
- `bi_metrics.py`: periodlogik och KPI-berakningar

Gemensamt:

- `config.py`: paths och runtimekonstanter

## 4. Steg 1 - Portfolio_index

Inputkallor:

- `config.PATH_TRANSAKTIONER`
- `config.PATH_FONDER`

Lasning:

- `load_inputs` i `src/io_excel.py`

Viktiga inputtabeller:

- `Transactions`
- `Mapping`
- `Portfolio_Metadata`
- `Benchmarks`
- `Fondertabell`

Output:

- `data/portfolio_output_timeseries.xlsx`

Workbooken skrivs med bladen:

- `Series_Definition`
- `Portfolio_Series_Map`
- `Master_TimeSeries_Long`
- `Run_Config`

Datumhantering for `REAL`:

- `Affarsdag` ar grunddatum for transaktioner i `REAL`
- om `Affarsdag` saknar rad i pris-/varderingsindex flyttas transaktionen till nasta tillgangliga varderingsdag
- samma effektiva datum anvands for bade positionsuppdatering och cashflow i `REAL` for att undvika att innehav och kassafloden hamnar ur synk

Seriekonventioner:

- `PORT_{slug(portfolio_name)}_{REAL|CUR|TGT}`
- `PORT_{slug(portfolio_name)}_REAL_CAT_{slug(category)}`
- `BM_{slug(Benchmark_ID)}`
- `AST_{slug(Yahoo_Ticker)}`

## 5. Steg 2 - BI_prep

Input:

- `data/portfolio_output_timeseries.xlsx`

Lasning och validering:

- `load_portfolio_output` i `src/bi_io.py`
- `extract_run_parameters` i `src/bi_io.py`

Output:

- `data/portfolio_bi_data.xlsx`

Workbooken skrivs med bladen:

- `Dim_Date`
- `Dim_Portfolio`
- `Dim_Series`
- `Dim_Instrument`
- `Fact_Series_Daily`
- `Fact_Series_KPI`
- `Fact_Portfolio_Alloc_Snapshot`

## 6. KPI- och periodlogik

Perioder:

- `Since_Start`
- `YTD`
- `30D`
- `1Y`

Minimiobservationer:

- `Since_Start`: 2
- `YTD`: 20
- `30D`: 20
- `1Y`: 126

Riskmatt kraver minst 20 giltiga dagliga `RET`.

KPI-logik:

- `Return_Total`
- `CAGR`
- `Vol`
- `Sharpe`
- `Sortino`
- `Max_DD`
- `Calmar`
- `DD_Duration_Max_Days`
- `Positive_Days_Pct`

Period- och KPI-logik finns i `src/bi_metrics.py`.

## 7. Viktiga designprinciper i nulaget

- upstream-sparet ar kallsanningen for tidsserier och metadata
- BI-sparet gor endast downstream-transformering for Power BI
- ingen ny prisnedladdning sker i BI-steget
- inga kvarvarande steg far bero pa tidigare Excel/dashboard-artefakter
- batchfilen haller upstream-korningen separat fran BI-korningen

## 8. Reproducerbarhet och felsokning

For felsokning ar dessa artefakter viktigast:

- `logs/run_*.log`
- `data/portfolio_output_timeseries.xlsx`
- `data/portfolio_bi_data.xlsx`
- `Run_Config` i upstream-workbooken
- `tests/smoke_test_prices.py` for separat tekniskt pris-smoketest

BI-sparet kan kors separat via:

- `py -m src.bi_prep`

---

Senast uppdaterad: 2026-04-12
