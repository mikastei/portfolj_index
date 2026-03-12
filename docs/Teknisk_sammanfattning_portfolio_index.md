# Teknisk sammanfattning for Portfolio_index och Dashboard_prep

## 1. Relevanta filer/mappar

```text
Portfoljindex/
├─ src/
│  ├─ main.py
│  ├─ dashboard_prep.py
│  ├─ dashboard_io.py
│  ├─ dashboard_tables.py
│  ├─ dashboard_metrics.py
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
│  └─ portfolio_dashboard_data.xlsx
├─ dev/
├─ logs/
├─ Portföljindex.bat
├─ README_portfolio_index.md
└─ requirements.txt
```

## 2. Entry points och korordning

Primara entry points:

- `src/main.py` -> `py -m src.main`
- `src/dashboard_prep.py` -> `py -m src.dashboard_prep`

Batchkorning via `Portföljindex.bat`:

1. aktiverar `.venv`
2. kor `py -m src.main`
3. kor `py -m src.dashboard_prep` endast om steg 1 lyckas
4. loggar bada stegen till en gemensam fil i `logs/`

## 3. Modulansvar i `src`

Portfolio_index:

- `main.py`: orchestration for steg 1
- `io_excel.py`: lasning och validering av inputtabeller
- `portfolio.py`: bygger `PORT_*`, `BM_*`, `AST_*` och kategoriunika `REAL`-serier
- `prices.py`: Yahoo-download, FX och returserier
- `outputs.py`: bygger och skriver `portfolio_output_timeseries.xlsx`
- `bootstrap.py`: SSL-init for Windows

Dashboard_prep:

- `dashboard_prep.py`: orchestration for steg 2
- `dashboard_io.py`: inlasning, validering och byggande av analysuniversum
- `dashboard_tables.py`: bygger dashboardtabeller
- `dashboard_metrics.py`: periodlogik, KPI-berakningar och korrelationer

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

Viktig datakontraktspunkt:

- varje ISIN i `Transactions` maste kunna kopplas till bade `Yahoo_Ticker` och `Category`
- kategori lases fran `Mapping`
- saknad kategori leder till valideringsfel i seriebyggandet

Output:

- `data/portfolio_output_timeseries.xlsx`

Workbooken skrivs i `write_output_excel` i `src/outputs.py` med bladen:

- `Series_Definition`
- `Portfolio_Series_Map`
- `Master_TimeSeries_Long`
- `Run_Config`

Viktiga kolumner:

- `Master_TimeSeries_Long`: `Date`, `Series_ID`, `RET`, `IDX`, `DD`
- `Series_Definition`: `Series_ID`, `Series_Type`, `Portfolio_Name`, `Variant`, `Benchmark_ID`, `Yahoo_Ticker`, `Instrument_Type`, `Category`, `Include_From_Date`, `Index_Start_Date`, `Initial_Index_Value`
- `Portfolio_Series_Map`: `Portfolio_Name`, `Series_ID`, `Yahoo_Ticker`, `Weight`, `Weight_Source`
- `Run_Config`: `Timestamp`, `PATH_TRANSAKTIONER`, `PATH_FONDER`, `OUTPUT_PATH`, `RF_RATE_ANNUAL`, `BASE_CURRENCY`, `TRADING_DAYS_PER_YEAR`, `FORWARD_FILL`, `NO_REBALANCING`

Seriekonventioner:

- `PORT_{slug(portfolio_name)}_{REAL|CUR|TGT}`
- `PORT_{slug(portfolio_name)}_REAL_CAT_{slug(category)}`
- `BM_{slug(Benchmark_ID)}`
- `AST_{slug(Yahoo_Ticker)}`

Kategoriunika REAL-serier:

- byggs endast for `REAL`
- bygger pa verkliga innehav och verkliga dagliga vikter
- byggs per portfolj och per kategori i faktisk portfoljhistorik
- ligger som `Series_Type = PORT`
- ligger som `Variant = REAL`
- far sin kategori i `Category`
- skrivs till bade `Series_Definition` och `Master_TimeSeries_Long`
- ar platta under perioder utan innehav i kategorin, med `RET = 0`

Viktig observation:

- `AST_*` kan finnas i `Series_Definition`
- `Master_TimeSeries_Long` skrivs nu med alla dashboardrelevanta serier:
  - huvudportfoljserier
  - kategoriunika REAL-serier
  - benchmarkserier

## 5. Steg 2 - Dashboard_prep

Input:

- `data/portfolio_output_timeseries.xlsx`

Lasning och validering:

- `load_dashboard_source` i `src/dashboard_io.py`

Analysuniversum:

- byggs fran serier som faktiskt finns i `Master_TimeSeries_Long`
- begransas till `Series_ID` som borjar med `PORT_` eller `BM_`
- omfattar darfor bade huvudportfoljserier och kategoriunika REAL-serier
- `AST_*` exkluderas uttryckligen

Output:

- `data/portfolio_dashboard_data.xlsx`

Workbooken skrivs i `src/dashboard_prep.py` med bladen:

- `KPI_Summary`
- `Period_Returns`
- `Chart_IDX_Wide`
- `Chart_DD_Wide`
- `Correlation_Long`
- `Allocation_Snapshot`
- `Dashboard_Config`
- `Build_Info`

## 6. Dashboardlogik

Perioder:

- `Since_Start`
- `YTD`
- `30D`
- `1Y`

Periodregler finns i `src/dashboard_metrics.py`.

Minimiobservationer:

- `Since_Start`: 2
- `YTD`: 20
- `30D`: 20
- `1Y`: 126
- riskmatt kraver minst 20 giltiga dagliga `RET`

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

Riskfri ranta och handelsdagar per ar lases fran `Run_Config`.

## 7. Display names och korrelationer

`Display_Name` byggs i `src/dashboard_io.py`:

- vanliga `PORT_*` -> `Portfolio_Name` + variantnamn
- kategoriunika `PORT_*_REAL_CAT_*` -> portfolj + `Real` + kategori
- variantmapping:
  - `REAL` -> `Real`
  - `CUR` -> `Current`
  - `TGT` -> `Target`
- `BM_*` -> `Benchmark_ID`

`Correlation_Long` byggs i `src/dashboard_tables.py` och `src/dashboard_metrics.py`:

- baseras pa dagliga `RET`
- perioder: `Since_Start`, `1Y`
- pairwise overlap pa gemensamma datum
- minst 20 gemensamma observationer
- endast unika seriepar, inga diagonalpar

## 8. Viktiga designprinciper i nulaget

- `Portfolio_index` ar kallsanningen for tidsserier
- `Dashboard_prep` gor endast downstream-transformering for dashboardbruk
- ingen ny prisnedladdning sker i dashboardsteget
- batchfilen kor stegen sekventiellt men kodbasen behaller dem som separata entry points
- kategoriunika REAL-serier betraktas som analysserier, inte bara intern metadata

## 9. Reproducerbarhet och felsokning

For felsokning ar dessa artefakter viktigast:

- `logs/run_*.log`
- `data/portfolio_output_timeseries.xlsx`
- `data/portfolio_dashboard_data.xlsx`
- `Run_Config` i steg 1
- `Build_Info` i steg 2

Senast uppdaterad: 2026-03-12
