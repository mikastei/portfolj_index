# Dashboard - konceptdesign

## Syfte

Dashboarden ska ge en snabb och tydlig bild av:

- hur portfoljerna utvecklas
- hur mycket risk de har
- hur de star sig mot benchmark
- hur portfoljerna ar uppbyggda
- hur portfoljerna har presterat inom olika kategorier

Den ska fungera som huvudvy for portfoljanalys och som konsumtionslager ovanpa `portfolio_dashboard_data.xlsx`.

## Projektets nulage i korthet

Projektet har nu en fungerande tva-stegspipeline:

1. `Portfolio_index`
   - laser transaktioner, mapping, portfoljmetadata, benchmarks och modellvikter
   - hamtar prisdata
   - bygger `PORT_*`, `BM_*` och interna `AST_*`
   - skriver `data/portfolio_output_timeseries.xlsx`

2. `Dashboard_prep`
   - laser `portfolio_output_timeseries.xlsx`
   - bygger dashboardklara tabeller i `data/portfolio_dashboard_data.xlsx`
   - anvander analysuniversumet `PORT_*` + `BM_*`
   - exkluderar `AST_*` fran analysen
   - inkluderar nu aven kategoriunika `REAL`-serier for portfoljerna

Nuvarande dashboarddata innehaller:

- `KPI_Summary`
- `Period_Returns`
- `Chart_IDX_Wide`
- `Chart_DD_Wide`
- `Correlation_Long`
- `Allocation_Snapshot`
- `Dashboard_Config`
- `Build_Info`

## Viktiga beslut som redan ar tagna

- Dashboarden ska byggas ovanpa `portfolio_dashboard_data.xlsx`, inte direkt pa radatan.
- `Dashboard_prep` ar ett separat steg fran `Portfolio_index`.
- `AST_*` anvands internt men ska inte inga i dashboardanalysen.
- `Display_Name` hanteras i kod, inte i inputfiler.
- Korrelationstabellen innehaller endast unika seriepar.
- Kategoriunika serier byggs bara for `REAL`.
- Kategoriunika serier foljer med som analysserier till dashboardunderlaget.

## Overgripande struktur

Dashboarden bor konceptuellt besta av sex delar:

1. Portfoljoversikt
2. Utveckling
3. Risk
4. Jamforelse
5. Struktur
6. Kategorianalys

Den viktigaste justeringen mot tidigare koncept ar att kategoriunika `REAL`-serier nu bor fa en egen plats i dashboarden i stallet for att bara blandas in overallt.

## 1. Portfoljoversikt

Syfte:

- snabb sammanfattning av hur huvudserierna presterar

Visar centrala nyckeltal for:

- portfoljer
- benchmark

Exempel pa nyckeltal:

- CAGR
- Volatilitet
- Sharpe
- Sortino
- Max drawdown
- Calmar

Rekommendation:

- denna vy bor som standard fokusera pa huvudserier, inte kategori-REAL-serier

## 2. Utveckling

Syfte:

- visa hur huvudportfoljerna utvecklas over tid

Visuellt fokus:

- indexutveckling
- jamforelse mot benchmark
- eventuell jamforelse mellan `REAL`, `CUR`, `TGT`

Typiska grafer:

- tillvaxtgraf
- relativ utveckling mot vald benchmark

Rekommendation:

- kategori-REAL-serier bor inte vara med har som standard
- de kan vara valbara, men inte default

## 3. Risk

Syfte:

- visa hur stora nedgangar och risker portfoljerna haft

Typiska analyser:

- drawdown over tid
- risk/return-diagram

Visualiseringar:

- drawdown-graf
- risk/return scatter

Rekommendation:

- fokus bor vara pa huvudserier och benchmark i standardlaget

## 4. Jamforelse

Syfte:

- visa hur portfoljer och benchmark samvarierar

Analys:

- korrelation mellan serier
- korrelation mot benchmark
- diversifiering och riskkluster

Visualisering:

- korrelationsheatmap

Rekommendation:

- denna del behover sannolikt ett filter for seriegrupp, till exempel:
  - huvudserier
  - kategori-REAL-serier
  - benchmark
  - alla

## 5. Struktur

Syfte:

- visa hur portfoljen ar uppbyggd

Innehall:

- vilka tillgangar som ingar
- deras vikter
- eventuell gruppering per portfolj

Visualiseringar:

- tabell
- staplar eller annan enkel viktfordelning

Rekommendation:

- denna del bor baseras pa `Allocation_Snapshot`
- hall isar faktisk struktur och historiska kategoriserier

## 6. Kategorianalys

Syfte:

- visa hur portfoljen faktiskt har presterat inom olika kategorier over tid

Innehall:

- kategoriunika `REAL`-serier
- kategori-KPI:er
- kategoriutveckling
- eventuell kategori-drawdown

Rekommendation:

- detta bor vara en egen sektion eller flik

## Analysuniversum i dashboarden

Dashboarden analyserar i praktiken:

- huvudserier:
  - vanliga `PORT_*`
  - `BM_*`
- undergrupp inom `PORT_*`:
  - huvudportfoljserier
  - kategoriunika `REAL`-serier

Serier som borjar med `AST_*`:

- anvands endast internt i berakningen
- ska inte inga i dashboardanalyser

Viktig justering:

Det racker inte langre att bara tala om `PORT_*` och `BM_*`.
Dashboardens design bor ocksa skilja mellan:

- huvudportfoljer
- kategoriportfoljer
- benchmark

## Designprinciper

Dashboarden ska vara:

- Enkel
  - fa men tydliga huvudvyer
- Robust
  - fungera nar nya portfoljer, benchmark eller kategoriserier tillkommer
- Automatiserad
  - uppdateras nar Python-korningarna uppdaterar data
- Filtrerbar
  - kunna skilja mellan huvudserier och kategori-REAL-serier

## Oppna fragor for fortsatt planering

- Vilka vyer ska finnas i forsta versionen av dashboarden, och vilka kan vanta?
- Ska alla analysserier visas direkt, eller behovs tydliga standardfilter?
- Hur ska standardurval fungera:
  - default-portfolj
  - default-variant
  - default-period
  - default-benchmark
- Hur ska benchmark valjas i jamforelsevyer:
  - manuellt i Excel
  - via dashboardlogik
- Hur ska kategori-REAL-serier visas:
  - som fullvardiga serier overallt
  - eller i en egen kategorisektion med egna filter
- Vilken Excel-arkitektur ar bast:
  - pivottabeller
  - formler mot databladen
  - hjalptabeller i workbooken

## Nasta prioriterade steg

1. definiera vilka dashboardvyer som ska visa huvudserier som default
2. definiera hur kategori-REAL-serier ska filtreras eller visas separat
3. definiera anvandarval och filter
4. synka Excel-designen mot de faktiska tabellerna i `portfolio_dashboard_data.xlsx`
5. bryta ner implementationen i tydliga arbetstradar
