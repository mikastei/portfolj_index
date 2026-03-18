# Power BI-spar plan v1

## Syfte

Detta dokument definierar ett forsta BI-datakontrakt och en enkel separation mellan Excel/dashboard-sparet och ett nytt Power BI-spar.

Fokus i denna trad:

- hall arbetet inkrementellt
- lat Excel-sparet leva vidare oforandrat
- bygg inte Power BI-rapporten annu
- gor inga stora omskrivningar av pipelinen

## Nulage

Gemensam downstream-kalla finns redan:

- `data/portfolio_output_timeseries.xlsx`

Nuvarande gemensamma blad:

- `Series_Definition`
- `Portfolio_Series_Map`
- `Master_TimeSeries_Long`
- `Run_Config`

Excel-sparet bygger vidare darifran:

- `data/portfolio_dashboard_data.xlsx`
- `data/portfolio_dashboard.xlsx`

Power BI har nu en egen artefakt och en egen prep-modul:

- `src/bi_prep.py`
- `data/portfolio_bi_data.xlsx`

## Lasta beslut

- Power BI ska ha en egen downstream-artefakt
- Power BI ska inte lasa `transaktioner.xlsx` direkt i v1
- nodvandig instrument-, portfolj- och seriemetadata ska materialiseras vidare till BI-underlaget
- KPI:er for v1 ska raknas i Python, inte i DAX
- forsta Power BI-versionen ska bara omfatta `Overview` och `Performance`
- datamodellen ska anda kunna bara framtida `Structure` och `Category`
- Excel-sparet ska fortsatt anvanda:
  - `src/dashboard_prep.py`
  - `src/dashboard_workbook.py`
  - `data/portfolio_dashboard_data.xlsx`
  - `data/portfolio_dashboard.xlsx`

## Kartlaggning av redan materialiserade affarsbegrepp

### `Series_Definition`

Materialiserar redan:

- serieidentitet: `Series_ID`
- serieklass: `Series_Type`
- portfoljkoppling: `Portfolio_Name`
- variant: `Variant`
- benchmarkkoppling: `Benchmark_ID`
- instrumentkoppling for `AST` och benchmark: `Yahoo_Ticker`
- instrumentmetadata: `ISIN`, `Display_Name`, `Price_Currency`
- instrumentmetadata: `Instrument_Type`
- kategoribegrepp: `Category`
- tidsstartregler: `Include_From_Date`, `Index_Start_Date`
- indexbas: `Initial_Index_Value`

Kommentar:

- `Category` finns redan pa serieniva for kategoriunika `REAL`-serier och `AST_*`
- `Structure` finns inte som eget begrepp eller attribut

### `Portfolio_Series_Map`

Materialiserar redan:

- portfolj: `Portfolio_Name`
- serie: `Series_ID`
- instrument: `Yahoo_Ticker`
- instrumentmetadata: `ISIN`, `Display_Name`, `Price_Currency`
- nuvarande vikt: `Weight`
- viktsource: `Weight_Source`

Kommentar:

- bra for framtida `Structure`
- saknar nyckel till instrumentdimension utom ticker
- saknar instrumentmetadata som namn, ISIN, kategori, strukturklass
- ar ett snapshot, inte historisk struktur

### `Master_TimeSeries_Long`

Materialiserar redan:

- datum: `Date`
- serie: `Series_ID`
- daglig avkastning: `RET`
- indexniva: `IDX`
- drawdown: `DD`

Kommentar:

- bra som faktatabell for `Overview` och `Performance`
- saknar explicita fremmande nycklar till portfolj-, benchmark- eller seriedimensioner utover `Series_ID`

### `Run_Config`

Materialiserar redan:

- korningstid: `Timestamp`
- input/output-pathar
- `RF_RATE_ANNUAL`
- `BASE_CURRENCY`
- `TRADING_DAYS_PER_YEAR`
- `FORWARD_FILL`
- `NO_REBALANCING`

Kommentar:

- bra som teknisk metadata
- bor inte bli central analysdimension i BI-modellen

## Vad som saknas for en bra BI-modell

Minsta viktiga luckor:

- stabil portfoljdimension med en rad per portfolj
- stabil seriedimension med tydlig flaggning av huvudserie kontra kategori-serie
- instrumentdimension med mer metadata an bara ticker
- explicit kategori- och framtida strukturklassning pa instrumentniva
- enklare filtreringsflaggor for vilka serier som hor till `Overview` och `Performance`
- Python-materialiserade KPI-tabeller sa att Power BI v1 slipper tung DAX-logik

Sarskilt for framtida `Structure` och `Category`:

- `Structure` krav: instrumentmetadata per portfoljallokering
- `Category` krav: tydlig koppling mellan kategoriunika serier och deras kategori
- framtida strukturklass bor kunna ligga pa instrumentdimensionen, inte endast bakas in i ett serieslug

## Metadata fran upstream som maste folja med

Maste folja med i BI-v1:

- `Portfolio_Name`
- `Series_ID`
- `Series_Type`
- `Variant`
- `Benchmark_ID`
- `Category`
- `Yahoo_Ticker`
- `ISIN`
- `Display_Name`
- `Price_Currency`
- `Instrument_Type`
- `Index_Start_Date`
- `Include_From_Date`
- `Initial_Index_Value`
- `Weight`
- `Weight_Source`
- `Date`
- `RET`
- `IDX`
- `DD`
- `BASE_CURRENCY`
- `RF_RATE_ANNUAL`
- `TRADING_DAYS_PER_YEAR`
- teknisk korningstid `Timestamp`

Bor folja med om de redan finns i upstreamtabellerna utan stor extra kostnad:

- portfolj-ID om `Portfolio_Metadata` faktiskt har `Portfolio_ID`

## Vad som inte behover folja med i BI v1

Behover inte folja med i BI-v1:

- direkta rader fran `Transactions`
- hela `transaktioner.xlsx`
- `AST_*`-serier som analysdata
- dashboardspecifika blad som `Chart_IDX_Wide`, `Chart_DD_Wide`, `Dashboard_Config`
- Excel-workbooklogik, named ranges eller presentationsmetadata
- korrelationsmatris for v1 om fokus ar `Overview` och `Performance`
- historisk instrument-allokering om endast nuvarande struktur ska forberedas senare

## Foreslaget BI-datakontrakt v1

Rekommenderad artefakt:

- `data/portfolio_bi_data.xlsx`

Skal:

- lagst friktion i nulaget
- enkel att generera med befintlig teknik
- tydlig parallell till Excel-sparets dataartefakt

Alternativ pa sikt:

- Parquet ar battre for storlek, typer och Power BI-prestanda
- v1 bor anda borja med Excel eller eventuellt CSV-set for enkelhet och liten andringsyta

### Dimensioner

#### `Dim_Portfolio`

Kolumner:

- `Portfolio_Key` som stabil slug eller `Portfolio_Name`
- `Portfolio_Name`
- `Portfolio_ID` nullable
- `Index_Start_Date`
- `Initial_Index_Value`

Nyckel:

- primarnyckel: `Portfolio_Key`

#### `Dim_Series`

Kolumner:

- `Series_ID`
- `Series_Type`
- `Portfolio_Key` nullable for benchmark
- `Portfolio_Name` nullable
- `Variant`
- `Benchmark_ID`
- `Category`
- `Yahoo_Ticker` nullable
- `Instrument_Type` nullable
- `Include_From_Date`
- `Index_Start_Date`
- `Initial_Index_Value`
- `Is_Main_Portfolio_Series`
- `Is_Category_Series`
- `Is_Benchmark`
- `Is_Overview_Eligible`
- `Is_Performance_Eligible`

Nyckel:

- primarnyckel: `Series_ID`

Kommentar:

- denna dimension blir central filtertabell i Power BI v1

#### `Dim_Instrument`

Kolumner:

- `Instrument_Key` rekommenderat `Yahoo_Ticker` i v1
- `Yahoo_Ticker`
- `ISIN` nullable
- `Display_Name` nullable
- `Instrument_Type`
- `Category`
- `Structure` nullable
- `Price_Currency` nullable

Nyckel:

- primarnyckel: `Instrument_Key`

Kommentar:

- `Structure` ar reserverad framtidskolumn
- om upstream saknar strukturklass ska kolumnen materialiseras som tom

#### `Dim_Date`

Kolumner:

- `Date`
- `Year`
- `Month`
- `Month_Name`
- `Quarter`
- `YearMonth`
- `Is_YTD_Latest_Flag` valfri

Nyckel:

- primarnyckel: `Date`

Kommentar:

- kan byggas i Python eller i Power BI
- rekommendation: bygg i Python om man vill ha ett helt explicit datakontrakt

### Fakta

#### `Fact_Series_Daily`

Kolumner:

- `Date`
- `Series_ID`
- `RET`
- `IDX`
- `DD`

Nycklar:

- naturlig nyckel: `Date` + `Series_ID`

Relationer:

- `Fact_Series_Daily.Series_ID` -> `Dim_Series.Series_ID`
- `Fact_Series_Daily.Date` -> `Dim_Date.Date`

#### `Fact_Series_KPI`

Kolumner:

- `Series_ID`
- `Period`
- `Start_Date`
- `End_Date`
- `Obs_Days`
- `Return_Total`
- `CAGR`
- `Vol`
- `Sharpe`
- `Sortino`
- `Max_DD`
- `Calmar`
- `DD_Duration_Max_Days`
- `Positive_Days_Pct`

Nycklar:

- naturlig nyckel: `Series_ID` + `Period`

Relationer:

- `Fact_Series_KPI.Series_ID` -> `Dim_Series.Series_ID`

Kommentar:

- detta ar huvudfakta for `Overview`
- KPI:er raknas i Python i BI-sparet

#### `Fact_Portfolio_Allocation_Snapshot`

Kolumner:

- `Portfolio_Key`
- `Series_ID`
- `Instrument_Key`
- `ISIN`
- `Display_Name`
- `Price_Currency`
- `Weight`
- `Weight_Source`
- `Snapshot_Date`

Nycklar:

- naturlig nyckel: `Series_ID` + `Instrument_Key` + `Snapshot_Date`

Relationer:

- `Series_ID` -> `Dim_Series`
- `Portfolio_Key` -> `Dim_Portfolio`
- `Instrument_Key` -> `Dim_Instrument`

Kommentar:

- behovs inte for Power BI-ytan i v1
- bor anda inga direkt i datakontraktet eftersom den bar framtida `Structure`

### Fakta kontra dimensioner

Fakta:

- `Fact_Series_Daily`
- `Fact_Series_KPI`
- `Fact_Portfolio_Allocation_Snapshot`

Dimensioner:

- `Dim_Portfolio`
- `Dim_Series`
- `Dim_Instrument`
- `Dim_Date`

## Rekommenderad minimal kodstruktur

Nuvarande BI-spar i kod:

- `src/bi_prep.py`

Ansvar for `src/bi_prep.py`:

- lasa `data/portfolio_output_timeseries.xlsx`
- bygga BI-dimensioner och faktatabeller
- berakna KPI-tabell i Python
- skriva separat BI-artefakt

Senare, endast om behov uppstar:

- `src/bi_io.py`
- `src/bi_tables.py`
- `src/bi_metrics.py`

Rekommendation:

- borja med en fil for att minimera andringsyta
- bryt upp forst nar BI-sparet blivit tillrackligt stort

## Hur sparen ska hallas isar

Gemensamma filer:

- `src/main.py`
- `src/io_excel.py`
- `src/portfolio.py`
- `src/outputs.py`
- `src/config.py`

Excel/dashboard-sparet:

- `src/dashboard_prep.py`
- `src/dashboard_io.py`
- `src/dashboard_tables.py`
- `src/dashboard_metrics.py`
- `src/dashboard_workbook.py`
- `data/portfolio_dashboard_data.xlsx`
- `data/portfolio_dashboard.xlsx`

BI-sparet:

- `src/bi_prep.py`
- `data/portfolio_bi_data.xlsx`

Gemensam dataartefakt:

- `data/portfolio_output_timeseries.xlsx`

Viktig regel:

- Excel-sparet ska inte konsumera BI-artefakten
- BI-sparet ska inte konsumera Excel-artefakterna
- bada downstream-spaaren ska lasa samma gemensamma kalla

## Antaganden

- `Mapping` kan innehalla fler kolumner an de som idag hardvalideras
- `Structure` finns inte som stabil upstream-kolumn i nulaget
- `Portfolio_Series_Map` ar tillrackligt som forsta struktur-snapshot
- `Overview` och `Performance` i Power BI v1 kan baseras pa serie- och KPI-fakta utan extra transaktionslager

## Risker och oppna fragor

Risker:

- kategori ligger delvis pa serieniva och delvis implicit pa instrumentniva; detta bor goras tydligare i BI-dimensionerna
- om `Yahoo_Ticker` inte ar stabilt unikt over tid kan en framtida riktig `Instrument_Key` behovas

Oppna fragor:

- finns ett verkligt upstream-falt for framtida `Structure`, eller maste det laggas till senare?
- ska BI-v1 inkludera benchmark i KPI-fakta fullt ut eller endast i daily performance?
- nar ar det vart att byta BI-artefakten fran Excel till Parquet eller CSV-set?

## Rekommenderad riktning

Den enklaste korrekta riktningen ar:

1. behall gemensamt spar oforandrat
2. introducera ett separat `src/bi_prep.py`
3. lat BI-sparet lasa `portfolio_output_timeseries.xlsx`
4. bygg ett litet stjarnschema i egen artefakt
5. berakna v1-KPI:er i Python
6. lat `Fact_Portfolio_Allocation_Snapshot` folja med redan i v1 for framtida `Structure`

## Rekommenderat nasta implementationsteg

Datakontraktet ar nu implementerat i `src/bi_prep.py`, som skriver:

- `Dim_Date`
- `Dim_Portfolio`
- `Dim_Series`
- `Dim_Instrument`
- `Fact_Series_Daily`
- `Fact_Series_KPI`
- `Fact_Portfolio_Alloc_Snapshot`

Nasta prioriterade steg bor darfor vara att definiera eller bygga en forsta Power BI-MVP for:

- `Overview`
- `Performance`

med `Structure` fortsatt datamassigt forberett via snapshot-faktan.
