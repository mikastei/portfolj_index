# Portfoljindex

Det har projektet bygger ett portfoljindex (bas 100) for en eller flera portfoljer samt benchmarkserier, baserat pa transaktioner och prisdata fran Yahoo Finance.

Projektet har nu ett gemensamt upstream-spar och tva separata downstream-spar:

1. gemensamt spar som bygger `data/portfolio_output_timeseries.xlsx`
2. dashboard/Excel-spar som bygger dashboardunderlag och workbook
3. BI-spar som bygger en separat BI-artefakt for Power BI

## Gemensamt spar

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

## Dashboard/Excel-spar

### Syfte

Excel-sparet lever vidare oforandrat och ska fortsatt vara separat fran framtida BI-konsumtion.

Kor dataunderlaget:

```bash
py -m src.dashboard_prep
```

Nuvarande Excel/dashboard-filer:

- `src/dashboard_prep.py`
- `src/dashboard_workbook.py`
- `data/portfolio_dashboard_data.xlsx`
- `data/portfolio_dashboard.xlsx`

Dataflode:

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
            |
            v
 py -m src.dashboard_workbook
            |
            v
   portfolio_dashboard.xlsx
```

`portfolio_dashboard_data.xlsx` innehaller:

- `KPI_Summary`
- `Period_Returns`
- `Chart_IDX_Wide`
- `Chart_DD_Wide`
- `Correlation_Long`
- `Allocation_Snapshot`
- `Dashboard_Config`
- `Build_Info`

Excel-sparet ansvarar for dashboardspecifik KPI-logik, tabellberedning och workbookpresentation. Det ska inte blandas ihop med framtida BI-artefakter.

## BI-spar

### Syfte

BI-sparet ar ett nytt downstream-spar for Power BI. Det ska inte lasa `transaktioner.xlsx` direkt i v1 och ska inte ateranvanda Excel-dashboardens artefakter som datakontrakt.

Principer for BI v1:

- egen downstream-artefakt
- laser gemensam kalla: `data/portfolio_output_timeseries.xlsx`
- KPI:er for `Overview` och `Performance` raknas i Python, inte i DAX
- datakontraktet ska redan kunna bara framtida `Structure` och `Category`
- Excel-sparet ska inte storas

Nuvarande BI-artefakt:

- `data/portfolio_bi_data.xlsx`

Nuvarande minimal kodstruktur for BI-sparet:

- `src/bi_prep.py`

Mojlig senare uppdelning nar sparet vuxit:

- `src/bi_io.py`
- `src/bi_tables.py`
- `src/bi_metrics.py`

Foreslaget BI-datakontrakt v1 dokumenteras i:

- `docs/powerbi_spar_plan.md`

## Hur sparen halls isar

Gemensamt spar:

- `src/main.py`
- `src/io_excel.py`
- `src/portfolio.py`
- `src/outputs.py`
- `data/portfolio_output_timeseries.xlsx`

Dashboard/Excel-spar:

- `src/dashboard_prep.py`
- `src/dashboard_io.py`
- `src/dashboard_tables.py`
- `src/dashboard_metrics.py`
- `src/dashboard_workbook.py`
- `data/portfolio_dashboard_data.xlsx`
- `data/portfolio_dashboard.xlsx`

BI-spar:

- `src/bi_prep.py`
- `data/portfolio_bi_data.xlsx`

Viktig princip:

- gemensamt spar bygger delad kallsanning
- Excel-sparet konsumerar denna for dashboardbehov
- BI-sparet konsumerar samma kalla men bygger egen BI-artefakt
- inget downstream-spar ska lasa det andra sparrets output

## Batchkorning

`Portföljindex.bat` kor idag det gemensamma sparet och dashboard/Excel-sparet. BI-sparet finns nu som separat steg men bor fortsatt hallas utanfor ordinarie batch tills rapportsparet ar mer stabilt.

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

Senast uppdaterad: 2026-03-16
