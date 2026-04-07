# Dashboard - konceptdesign

## Syfte

Dashboarden ska ge en snabb och tydlig bild av:

- hur portfoljerna utvecklas
- hur mycket risk de har
- hur de star sig mot benchmark
- hur portfoljerna ar uppbyggda
- hur portfoljerna har presterat inom olika kategorier

Den ska fungera som huvudvy for portfoljanalys och som konsumtionslager ovanpa `portfolio_dashboard_data.xlsx`.

Dashboarden ska pa sikt materialiseras som en separat Excel-workbook ovanpa detta underlag.
Output-path for den workbooken bor vara konfigurerbar i `src/config.py`, inte hardkodad i sjalva dashboardbyggandet.

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
- Benchmark ar inte hardkopplade till en enskild portfolj i dashboarden.
- Jamforelser i dashboarden ska kunna goras fritt mellan:
  - portfoljer
  - portfoljvarianter
  - benchmark

## Overgripande struktur

Dashboarden bor konceptuellt besta av sex delar:

1. Portfoljoversikt
2. Utveckling
3. Risk
4. Jamforelse
5. Struktur
6. Kategorianalys

I v1 bor detta konkretiseras till fyra arbetsflikar:

1. `Overview`
2. `Performance`
3. `Structure`
4. `Category`

Den viktigaste justeringen mot tidigare koncept ar att kategoriunika `REAL`-serier ska ha en egen plats i dashboarden i stallet for att blandas in i huvudlagret.

## 1. Portfoljoversikt

Syfte:

- snabb sammanfattning av hur huvudserierna presterar

Visar centrala nyckeltal for:

- vald primarserie
- valfria jamforelseserier

Exempel pa nyckeltal:

- CAGR
- Volatilitet
- Sharpe
- Sortino
- Max drawdown
- Calmar

Rekommendation:

- denna vy ska som standard fokusera pa huvudserier, inte kategori-REAL-serier
- benchmark och andra portfoljer ska kunna laggas till som fria jamforelser

## 2. Utveckling

Syfte:

- visa hur huvudportfoljerna utvecklas over tid

Visuellt fokus:

- indexutveckling
- jamforelse mot valfria benchmark eller andra portfoljer
- eventuell jamforelse mellan `REAL`, `CUR`, `TGT`

Typiska grafer:

- tillvaxtgraf
- relativ utveckling mot vald jamforelseserie
- drawdown-graf

Rekommendation:

- kategori-REAL-serier ska inte vara med har som standard
- de kan vara valbara senare, men inte i huvudlogiken for v1
- anvandaren bor kunna valja flera jamforelseserier fritt inom huvuduniversumet

## 3. Risk

Syfte:

- visa hur stora nedgangar och risker portfoljerna haft

Typiska analyser:

- drawdown over tid
- risk/return-diagram
- periodbaserade riskmatt

Visualiseringar:

- drawdown-graf
- senare eventuellt risk/return scatter

Rekommendation:

- fokus ska vara pa huvudserier och benchmark i standardlaget
- en enklare riskdel kan inga i `Performance` i v1
- mer avancerad riskvy kan komma i v2

## 4. Jamforelse

Syfte:

- visa hur portfoljer och benchmark samvarierar
- mojliggora fri visuell och tabellar jamforelse

Analys:

- jamforelse mellan valfria portfoljer, varianter och benchmark
- senare korrelation, diversifiering och riskkluster

Visualisering:

- i v1 framst via KPI-tabeller, periodreturer och gemensamma diagram
- korrelationsheatmap kan vanta till v2

Rekommendation:

- denna del ska inte forutsatta en fast benchmarkkoppling per portfolj
- jamforelse ska bygga pa ett primarval plus valfria tillaggsserier
- antal samtidiga jamforelseserier bor begransas i v1 for enkelhetens skull

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

- denna del ska baseras pa `Allocation_Snapshot`
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

- detta ska vara en egen flik eller sektion
- kategori-REAL ska inte vara default i huvudoversikten
- denna del ska fungera som ett tydligt drilldown-lage

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
- Jamforbar
  - lata anvandaren valja fri jamforelse mellan portfoljer, portfoljvarianter och benchmark
- Utbyggbar
  - ge en tydlig grund for framtida v2-forbattringar utan att v1 maste goras om

## Foreslagen anvandarlogik

Dashboarden bor utga fran ett tydligt primarval och ett fritt jamforelselager.

### Primarval

Anvandaren valjer:

- primar portfolj
- primar variant
- period

Primarserien ska i v1 avse huvudserier, inte kategori-REAL.

### Jamforelselager

Anvandaren ska kunna lagga till upp till nagra valfria jamforelseserier, till exempel:

- benchmark
- andra portfoljer
- andra portfoljvarianter

I v1 bor detta begransas till ett litet antal fasta val, till exempel:

- `Jamforelse 1`
- `Jamforelse 2`
- `Jamforelse 3`

Detta ger en enklare och mer generell logik an att forsoka koppla ett standardbenchmark till varje portfolj.

### Seriegruppslogik

- huvudserier som standard i `Overview` och `Performance`
- kategori-REAL i separat `Category`-flik
- benchmark som fritt valbar jamforelseserie

## Rekommenderad v1-struktur

V1 bor innehalla foljande flikar:

1. `Overview`
   - KPI-kort for primarserien
   - enkel jamforelsetabell mot valda serier
   - snabb statusbild

2. `Performance`
   - indexgraf for primarserie och jamforelseserier
   - drawdown-graf
   - periodreturer

3. `Structure`
   - portfoljens nuvarande struktur utifran `Allocation_Snapshot`

4. `Category`
   - kategori-KPI
   - kategoriutveckling
   - enkel drilldown per portfolj

## Standardval for v1

Rekommenderade standardval:

- default-variant: `REAL`
- default-period i dashboardvyn: `1Y`
- `Since_Start` ska fortsatt vara valbart
- jamforelseserier ar tomma som standard eller satta till ett mycket enkelt startlage
- huvudserier ar standarduniversum
- kategori-REAL visas separat

## Excel-arkitektur

For v1 bor dashboarden byggas med fokus pa enkelhet och robusthet.

Rekommenderad arkitektur:

- separat dashboard-workbook
- configstyrd output-path
- formler och hjalptabeller som primar teknik
- diagram kopplade till kontrollerade hjalpomraden
- pivottabeller endast om de ger tydlig nytta

Det bor vara enkelt att felsoka workbooken och enkelt att lagga till nya vyer i v2.

## Oppna fragor for fortsatt planering

- Vilken default-portfolj ska visas nar workbooken oppnas?
- Ska perioddefault i sjalva dashboarden vara `1Y` eller `Since_Start`?
- Hur manga jamforelseserier ska visas samtidigt i v1?
- Ska jamforelseserier valjas via fasta kontrollceller eller via nagon enklare tabellstyrning i Excel?
- Hur mycket kategori-analys ska inga i v1:
  - bara tabell
  - eller aven graf och KPI
- Ska korrelationsvyn inga i v1 eller skjutas till v2?

## Nasta prioriterade steg

1. lasa v1-scope och flikstruktur
2. lasa kontrollfalten for primarserie, variant, period och jamforelser
3. definiera output-path och workbookansvar i `src/config.py`
4. ta fram en konkret wireframe for varje v1-flik
5. bryta ner implementationen i separata arbetstradar
