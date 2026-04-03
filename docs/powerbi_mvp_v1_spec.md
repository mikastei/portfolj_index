# Power BI MVP v1-spec

## Syfte

Detta dokument ar en konkret byggspec for en forsta Power BI-rapport ovanpa `data/portfolio_bi_data.xlsx`.

Scope for v1:

- endast `Overview`
- endast `Performance`
- inga upstream-andringar om de inte ar tydligt nodvandiga
- ingen direktlasning av `transaktioner.xlsx`
- kategori-serier ska inte exponeras i rapportytan
- `REAL` ar standardvariant
- KPI-period ar separat fran datumslider
- datumslider far bara styra tidsserievisuals pa `Performance`

Miljon i denna trad kan inte bygga en faktisk `.pbix`, sa detta dokument ar avsett som direkt underlag for nasta PBIX-steg.

## Verifierat nulage i `portfolio_bi_data.xlsx`

Verifierad workbookstruktur:

- `Dim_Date` med 572 rader
- `Dim_Portfolio` med 2 rader
- `Dim_Series` med 23 rader
- `Dim_Instrument` med 68 rader
- `Fact_Series_Daily` med 13138 rader
- `Fact_Series_KPI` med 92 rader
- `Fact_Portfolio_Alloc_Snapshot` med 78 rader

Verifierade portfoljer:

- `EGEN`
- `PA`

Verifierade varianter i huvudserier:

- `CUR`
- `REAL`
- `TGT`

Verifierade benchmarkserier:

- `BM_Emerging_Markets`
- `BM_Global_Large`
- `BM_Intermediate_Core_Bond`
- `BM_Nordnet_Balanserad`
- `BM_Nordnet_Offensiv`
- `BM_OMX_Stockholm_GI`

Verifierade KPI-perioder:

- `30D`
- `YTD`
- `1Y`
- `Since_Start`

Verifierade flaggor i `Dim_Series`:

- `Is_Main_Portfolio_Series = TRUE`: 6 serier
- `Is_Category_Series = TRUE`: 11 serier
- `Is_Benchmark = TRUE`: 6 serier
- `Is_Overview_Eligible = TRUE`: 12 serier
- `Is_Performance_Eligible = TRUE`: 23 serier

Praktisk tolkning for v1:

- synligt analysuniversum bor vara de 12 `Is_Overview_Eligible`-serierna
- dessa bestar av 6 huvudserier och 6 benchmarkserier
- kategori-serierna finns i modellen men ska hallas helt dolda i v1-ytan

Verifierade relationer i datat:

- `Fact_Series_Daily.Series_ID` matchar fullt ut `Dim_Series.Series_ID`
- `Fact_Series_Daily.Date` matchar fullt ut `Dim_Date.Date`
- `Fact_Series_KPI.Series_ID` matchar fullt ut `Dim_Series.Series_ID`
- `Fact_Portfolio_Alloc_Snapshot` matchar fullt ut `Dim_Portfolio`, `Dim_Series` och `Dim_Instrument`

Verifierad datumtackning:

- modellens datumspann ar `2024-01-01` till `2026-03-13`
- huvudserierna startar i praktiken `2024-01-02`
- tva benchmarkserier startar `2024-01-05`

## Rekommenderad Power BI-v1-modell

### Aktiva tabeller i rapporten

Tabeller som ska anvandas aktivt i `Overview` och `Performance`:

- `Dim_Date`
- `Dim_Series`
- `Fact_Series_Daily`
- `Fact_Series_KPI`

Tabeller som kan importeras men hallas dolda i v1:

- `Dim_Portfolio`
- `Dim_Instrument`
- `Fact_Portfolio_Alloc_Snapshot`

Skal:

- de senare behovs inte for synlig v1-yta
- de kan ligga kvar for framtida `Structure` utan att storra nuvarande MVP

### Rekommenderade relationer

Aktiva relationer:

- `Dim_Date[Date]` 1:* `Fact_Series_Daily[Date]`
- `Dim_Series[Series_ID]` 1:* `Fact_Series_Daily[Series_ID]`
- `Dim_Series[Series_ID]` 1:* `Fact_Series_KPI[Series_ID]`
- `Dim_Portfolio[Portfolio_Key]` 1:* `Dim_Series[Portfolio_Key]`
- `Dim_Portfolio[Portfolio_Key]` 1:* `Fact_Portfolio_Alloc_Snapshot[Portfolio_Key]`
- `Dim_Series[Series_ID]` 1:* `Fact_Portfolio_Alloc_Snapshot[Series_ID]`
- `Dim_Instrument[Instrument_Key]` 1:* `Fact_Portfolio_Alloc_Snapshot[Instrument_Key]`

Rekommendation:

- enkelriktad filtrering fran dimension till fakta
- inga dubbelriktade relationer i v1
- undvik att bygga rapportlogik pa `Fact_Portfolio_Alloc_Snapshot` i denna fas

### PBIX-lokala urvalstabeller

For att kunna valja primarserie, benchmark och extra jamforelse oberoende av varandra bor PBIX:en ha sma frikopplade urvalstabeller.

Rekommenderade urvalstabeller i PBIX:

- `Sel_Primary_Portfolio`
- `Sel_Primary_Variant`
- `Sel_KPI_Period`
- `Sel_Benchmark`
- `Sel_Compare_Extra`

Dessa ska vara frikopplade, utan relationer till faktatabellerna.

Skal:

- en vanlig slicer pa `Dim_Series` racker inte for tre separata urvalsspar
- benchmark ska vara fritt valbart
- extra jamforelse ska kunna vara annan portfolj eller annan variant

### Rekommenderad urvalslogik

Primarserie:

- valjs via `Sel_Primary_Portfolio[Portfolio_Name]`
- valjs via `Sel_Primary_Variant[Variant]`
- resolvas mot exakt en rad i `Dim_Series`
- maste filtreras till `Dim_Series[Is_Main_Portfolio_Series] = TRUE`

Benchmark:

- valjs via `Sel_Benchmark`
- maste filtreras till `Dim_Series[Is_Benchmark] = TRUE`
- ar frivillig men bor ha en enkel default, exempelvis tom eller `BM_Global_Large`

Extra jamforelse:

- valjs via `Sel_Compare_Extra`
- maste filtreras till `Dim_Series[Is_Overview_Eligible] = TRUE`
- far vara annan portfolj, annan variant eller benchmark

Pragmatisk v1-regel:

- om extra jamforelse blir samma serie som primar eller benchmark ska visualen visa blank rad i stallet for dublett

### Rekommenderade slicers

Slicers som ska finnas i v1:

- `Primar portfolj`
- `Variant`
- `KPI-period`
- `Benchmark`
- `Extra jamforelse`

Slicer som bara ska finnas pa `Performance`:

- `Datumintervall`

Standardlage:

- `Variant = REAL`
- `KPI-period = 1Y`
- `Benchmark = tom`
- `Extra jamforelse = tom`
- primarportfolj = en vald standard eller forsta alfabetiska

### Hur kategori-serier halls dolda i v1

Kategori-serierna ska inte exponeras i nagon synlig slicer eller visual i v1.

Rekommenderad losning:

- bygg alla synliga urvalstabeller fran `Dim_Series` dar `Is_Overview_Eligible = TRUE`
- lagg en sidfilterregel pa bade `Overview` och `Performance` som exkluderar `Is_Category_Series = TRUE`
- hall `Category`-kolumnen dold i falthanteringen for v1

Viktig konsekvens:

- `Is_Performance_Eligible` ska inte styra den synliga v1-ytan
- den flaggan blir forst relevant nar en separat `Category`-sida byggs

### Praktisk etikettlogik i PBIX

`Dim_Series` saknar idag anvandarvanliga serienamn.

Detta bor losas direkt i PBIX med en lokal etikettkolumn, till exempel:

- benchmark: rensad version av `Benchmark_ID`
- huvudserie: `Portfolio_Name + " " + Variant`
- kategori: inte synlig i v1

Detta ar ett rapportlagerproblem, inte ett blockerande BI-sporsgap.

## Sida: Overview

| Visual | Syfte | Datakalla | Filterpaverkan | Risk / workaround |
| --- | --- | --- | --- | --- |
| Slicerband overst | Samla primarurval och jamforelser pa en plats | PBIX-lokala urvalstabeller | `Primar portfolj`, `Variant`, `KPI-period`, `Benchmark`, `Extra jamforelse` styr alla Overview-visuals | Frikopplade slicers kravs; los med selektionsmeasures i stallet for direkta relationer |
| KPI-kort for primarserie | Snabb statusbild for vald huvudserie | `Fact_Series_KPI` via `Dim_Series` | Styrs av primarserie och `KPI-period`, men inte av datumslider | Kort maste peka pa exakt en serie; visa blankt om primarvalet inte resolvas entydigt |
| Jamforelsetabell med 3 rader | Jamfor primar, benchmark och extra serie i samma period | `Fact_Series_KPI` via `Dim_Series` | Styrs av primarserie, benchmark, extra jamforelse och `KPI-period` | Dubbletter kan uppsta om samma serie valjs flera ganger; visa blank rad for dublett |
| Data freshness-kort | Visa senaste datadag och ge tillit till rapporten | `Fact_Series_Daily` eller `Dim_Date` | Oberoende av `KPI-period`, bor inte styras av datumslider | Ingen sarskild risk; anvand maxdatum i modellen |

Rekommenderade KPI-kort:

- `Return_Total`
- `CAGR`
- `Vol`
- `Sharpe`
- `Max_DD`
- `Calmar`

Rekommenderade kolumner i jamforelsetabellen:

- `Series_Label`
- `Return_Total`
- `CAGR`
- `Vol`
- `Sharpe`
- `Sortino`
- `Max_DD`
- `Calmar`

Pragmatisk layoutsammanfattning:

- overst: slicerband
- mitten: 6 KPI-kort for primarserien
- nederst: en jamforelsetabell
- liten statusyta till hoger med senaste datadatum

## Sida: Performance

| Visual | Syfte | Datakalla | Filterpaverkan | Risk / workaround |
| --- | --- | --- | --- | --- |
| Slicerband overst | Ateranvand samma urvalslogik som pa `Overview` | PBIX-lokala urvalstabeller | Styr bada linjediagrammen och KPI-tabellen | Hall samma standardval som pa `Overview` for konsekvens |
| Datumslider | Styra bara tidsserievisuals | `Dim_Date` -> `Fact_Series_Daily` | Ska bara paverka index- och drawdowndiagram | Anvand `Edit interactions` sa att den inte filtrerar KPI-tabellen |
| Linjediagram: Indexutveckling | Visa primarserie mot benchmark och extra jamforelse over tid | `Fact_Series_Daily[IDX]` via `Dim_Series` | Styrs av primarserie, benchmark, extra jamforelse och datumslider | Serierna startar inte exakt samma dag; lat visualen visa naturliga blanks fore forsta observation |
| Linjediagram: Drawdown | Visa riskbanan for samma tre serier | `Fact_Series_Daily[DD]` via `Dim_Series` | Samma filter som indexdiagrammet | Samma issue med olika startdatum; samma workaround |
| KPI-tabell for vald period | Ge snabb avlasning under diagrammen utan att blanda in datumslider | `Fact_Series_KPI` via `Dim_Series` | Styrs av primarserie, benchmark, extra jamforelse och `KPI-period`, men inte av datumslider | Kraver tydlig etikett i rubrik, till exempel `KPI-period: 1Y` |

Rekommenderade kolumner i KPI-tabellen:

- `Series_Label`
- `Return_Total`
- `CAGR`
- `Vol`
- `Sharpe`
- `Max_DD`

Pragmatisk layoutsammanfattning:

- overst: slicerband plus datumslider
- mitten: stort indexdiagram
- under: drawdowndiagram
- nederst: kompakt KPI-tabell for vald period

## Vad som ingar nu

Ingaar i Power BI-v1:

- import av befintligt `portfolio_bi_data.xlsx`
- liten och stabil modell for `Overview` och `Performance`
- separat val av primarserie, benchmark och extra jamforelse
- standardvariant `REAL`
- separat `KPI-period`
- datumslider endast pa tidsserievisuals i `Performance`
- kategori-serier dolda i all synlig yta

## Vad som skjuts till senare

Skjuts till senare:

- faktisk `Structure`-sida
- faktisk `Category`-sida
- fler an en extra jamforelseserie
- hardkopplad benchmark per portfolj
- avancerad DAX-logik for KPI:er
- korrelation, scatter, drillthrough eller annan v2-analys

## Kritiska gap

### Rapportgap som kan losas i Power BI direkt

- `Dim_Series` saknar anvandarvanlig etikettkolumn
- frikopplade urvalstabeller behovs for tre separata urvalsspar
- datumslider maste explicit avgransas med `Edit interactions`

Dessa gap kraver ingen andring i BI-sparet.

### Datamodellgap som faktiskt kraver andring i BI-sparet

Inga blockerande datamodellgap ar identifierade for just `Overview` och `Performance` v1.

Foljdnotering for senare faser:

- `Dim_Instrument` har i nulaget tomma falt for `Instrument_Type`, `Category` och `Structure`
- det ar inte blockerande nu, men blir relevant nar `Structure` eller framtida kategorimodell ska byggas

## Rekommenderat nasta steg

1. Skapa en ny PBIX som laser `data/portfolio_bi_data.xlsx`.
2. Satt relationerna enligt denna spec.
3. Skapa de fem frikopplade urvalstabellerna i PBIX.
4. Bygg `Overview` och `Performance` med exakt urvalslogik ovan.
5. Lasa standardlaget till `REAL`, `1Y` och tom benchmark/extra jamforelse via bookmark eller sparad rapportsession.
6. Validera med minst dessa urval:
   - `EGEN` + `REAL`
   - benchmark `BM_Global_Large`
   - extra jamforelse `PA REAL`
   - `KPI-period = 1Y`

Om detta fungerar behovs ingen andring i upstream eller BI-sparet for att leverera en forsta Power BI-MVP.
