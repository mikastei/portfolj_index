# Portfoljindex

Det har projektet bygger ett portfoljindex (bas 100) for en eller flera portfoljer samt benchmarkserier, baserat pa transaktioner och prisdata fran Yahoo Finance.

Projektet innehaller nu tva separata steg:

1. `Portfolio_index` bygger kallsanningen `portfolio_output_timeseries.xlsx`
2. `Dashboard_prep` laser den outputen och bygger `portfolio_dashboard_data.xlsx` for Excel-dashboarden

## Oversikt - dataflode

```text
transaktioner.xlsx + fonder.xlsx
            |
            v
      py -m src.main
            |
            v
portfolio_output_timeseries.xlsx
            |
            v
  py -m src.dashboard_prep
            |
            v
portfolio_dashboard_data.xlsx
```

`Portföljindex.bat` kor bada stegen i denna ordning och loggar till `logs/`.

## Indata

### `transaktioner.xlsx`

Excelarbetsbok med:

- `Transactions`
- `Mapping`
- `Portfolio_Metadata`
- `Benchmarks`

Viktiga regler:

- `KOP` = negativt belopp
- `SALJ` = positivt belopp
- varje ISIN i `Transactions` maste finnas i `Mapping`
- varje ISIN i `Transactions` maste ha en giltig `Category` i `Mapping`

### `fonder.xlsx`

Genereras i projektet Fondanalys och anvands som input for modellportfoljer:

- `CUR`
- `TGT`

## Steg 1 - Portfolio_index

Kor:

```bash
py -m src.main
```

Detta steg:

1. laser inputtabeller fran Excel
2. hamtar prisdata fran Yahoo Finance
3. bygger vanliga `PORT_*`, `BM_*` och interna `AST_*` serier
4. bygger kategoriunika `REAL`-serier for portfoljernas faktiska innehav
5. skriver `data/portfolio_output_timeseries.xlsx`

### Output: `portfolio_output_timeseries.xlsx`

Workbooken innehaller:

- `Series_Definition`
- `Portfolio_Series_Map`
- `Master_TimeSeries_Long`
- `Run_Config`

`Master_TimeSeries_Long` ar huvudtabellen for dashboardrelevanta tidsserier:

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

### Kategoriunika REAL-serier

Projektet bygger nu aven kategoriunika REAL-serier for varje portfolj, baserat pa `Category` i `Mapping`.

Exempel pa `Series_ID`:

- `PORT_EGEN_REAL_CAT_GLOBAL_BREDA_FONDER`
- `PORT_EGEN_REAL_CAT_R_NTOR_L_GRISK`

Egenskaper:

- de byggs endast for `REAL`
- de bygger pa verkliga innehav och verkliga dagliga vikter
- de finns i bade `Series_Definition` och `Master_TimeSeries_Long`
- `Series_Type` ar fortsatt `PORT`
- `Variant` ar fortsatt `REAL`
- kategorin uttrycks via `Series_ID` och `Category`
- under perioder utan innehav i kategorin ar serien platt med `RET = 0`

## Steg 2 - Dashboard_prep

Kor:

```bash
py -m src.dashboard_prep
```

Detta steg:

1. laser `portfolio_output_timeseries.xlsx`
2. bygger ett analysuniversum fran `PORT_*` och `BM_*`
3. exkluderar `AST_*` fran dashboardanalysen
4. inkluderar bade huvudportfoljserier och kategoriunika `REAL`-serier
5. skriver `data/portfolio_dashboard_data.xlsx`

### Output: `portfolio_dashboard_data.xlsx`

Workbooken innehaller:

- `KPI_Summary`
- `Period_Returns`
- `Chart_IDX_Wide`
- `Chart_DD_Wide`
- `Correlation_Long`
- `Allocation_Snapshot`
- `Dashboard_Config`
- `Build_Info`

Perioder i dashboardsteget:

- `Since_Start`
- `YTD`
- `30D`
- `1Y`

Notera:

- `Correlation_Long` innehaller endast unika seriepar
- portfoljernas `Display_Name` skrivs som `Real`, `Current`, `Target`
- kategoriunika REAL-serier far egna displaynamn baserade pa portfolj + kategori
- benchmarknamn hamtas fran `Benchmark_ID`

## Batchkorning

Kor hela pipelinen via:

```bat
Portföljindex.bat
```

Batchfilen:

1. aktiverar `.venv`
2. kor `py -m src.main`
3. kor `py -m src.dashboard_prep` om steg 1 lyckas
4. skriver logg till `logs/run_YYYYMMDD_HHMMSS.log`

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

Senast uppdaterad: 2026-03-12
