# Power BI-spar plan

## Syfte

Detta dokument beskriver det kvarvarande BI-sparet efter att Excel/dashboard-sparet har avvecklats ur projektet.

Fokus:

- behall upstream-sparet stabilt
- hall BI-sparet separat och tydligt
- bygg vidare pa ett litet, explicit datakontrakt

## Aktiv struktur

Gemensam upstream-kalla:

- `data/portfolio_output_timeseries.xlsx`

BI-artefakt:

- `data/portfolio_bi_data.xlsx`

Aktiva BI-moduler:

- `src/bi_prep.py`
- `src/bi_io.py`
- `src/bi_metrics.py`

## Lasta beslut

- Power BI ska ha en egen downstream-artefakt
- Power BI ska inte lasa `transaktioner.xlsx` direkt
- BI-sparet ska lasa den gemensamma upstream-artefakten
- KPI:er for v1 ska raknas i Python
- BI-datakontraktet ska redan kunna bara framtida `Structure` och `Category`

## Upstream som BI bygger pa

`portfolio_output_timeseries.xlsx` innehaller:

- `Series_Definition`
- `Portfolio_Series_Map`
- `Master_TimeSeries_Long`
- `Run_Config`

Viktiga affarsbegrepp som redan materialiseras upstream:

- portfoljidentitet via `Portfolio_Name`
- serieidentitet via `Series_ID`
- variant och benchmarkkoppling
- instrumentmetadata via `Yahoo_Ticker`, `ISIN`, `Display_Name`, `Price_Currency`, `Instrument_Type`
- kategori pa serie- och instrumentnara niva
- daglig tidsserie via `RET`, `IDX`, `DD`
- aktuellt struktur-snapshot via `Portfolio_Series_Map`

## BI-datakontrakt v1

Artefakt:

- `data/portfolio_bi_data.xlsx`

Dimensioner:

- `Dim_Date`
- `Dim_Portfolio`
- `Dim_Series`
- `Dim_Instrument`

Fakta:

- `Fact_Series_Daily`
- `Fact_Series_KPI`
- `Fact_Portfolio_Alloc_Snapshot`

## Modulansvar

`src/bi_prep.py`

- orkestrerar BI-korningen
- bygger dimensioner och faktatabeller
- skriver BI-artefakten

`src/bi_io.py`

- laser och validerar `portfolio_output_timeseries.xlsx`
- extraherar runtimeparametrar fran `Run_Config`

`src/bi_metrics.py`

- innehaller periodlogik
- beraknar Python-materialiserade KPI:er

## Viktiga regler

- BI-sparet ska inte ha egna beroenden till tidigare Excel/dashboard-filer
- upstream ska inte skrivas om for presentationsbehov
- framtida BI-utbyggnad ska ske inkrementellt ovanpa datakontraktet

## Rekommenderad korordning

1. kor `py -m src.main`
2. kor `py -m src.bi_prep`

`Portföljindex.bat` kor nu bada stegen sekventiellt och stoppar om steg 1 misslyckas. `src.bi_prep` finns fortfarande kvar som separat entry point for felsokning eller om BI-artefakten ska byggas om utan ny upstream-korning.

## Relevanta kompletterande dokument

- `docs/powerbi_mvp_v1_spec.md`
- `docs/powerbi_dax_v1.md`
- `docs/Teknisk_sammanfattning_portfolio_index.md`

---

Senast uppdaterad: 2026-04-07
