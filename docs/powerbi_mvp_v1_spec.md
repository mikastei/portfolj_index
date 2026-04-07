# Power BI MVP v1-spec

## Syfte

Detta dokument beskriver den faktiska Power BI-v1 som nu byggs ovanpa `data/portfolio_bi_data.xlsx`.

Dokumentet ska fungera som:

- aktuell specifikation for den faktiska PBIX-modellen
- gemensam referens for rapportlager, DAX-objekt och avgransningar
- underlag for att fardigstalla `Overview` och `Performance`

Detta dokument ar alltsa inte primart en bygginstruktion langre, utan en nulages- och malspec for den Power BI-v1 som nu etablerats.

## Scope for v1

Ingaar i v1:

- `Overview`
- `Performance`
- import av hela `portfolio_bi_data.xlsx`
- liten och stabil datamodell
- separat urval for primarserie, benchmark och extra jamforelse
- KPI-period separat fran datumurval
- kategori-serier kvar i modellen men dolda i v1-ytan

Ingaar inte i v1:

- direktlasning av `transaktioner.xlsx`
- hardkopplad benchmark per portfolj
- `Structure`-sida
- `Category`-sida
- kategori-serier i synliga slicers eller visuals
- DAX-berakning av v1-KPI:er som redan finns materialiserade i Python

## Verifierad grunddata

Verifierad workbookstruktur i `data/portfolio_bi_data.xlsx`:

- `Dim_Date` med 574 rader
- `Dim_Portfolio` med 2 rader
- `Dim_Series` med 23 rader
- `Dim_Instrument` med 68 rader
- `Fact_Series_Daily` med 13184 rader
- `Fact_Series_KPI` med 92 rader
- `Fact_Portfolio_Alloc_Snapshot` med 78 rader

Verifierat om datakontraktet:

- modellen har ett litet och fungerande stjarnschema for `Overview` och `Performance`
- `Fact_Series_Daily` ar huvudfakta for tidsserievisuals
- `Fact_Series_KPI` ar huvudfakta for KPI-visuals
- `Dim_Series` ar central dimension for serieselection och rapportlogik
- kategori-serier finns materialiserade men ska inte exponeras i v1-ytan

Verifierat om innehall pa overgripande niva:

- flera huvudserier finns for portfoljer och varianter
- benchmarkserier finns som eget universum
- KPI-perioder finns materialiserade i faktat
- relationell integritet mellan dimensioner och fakta ar verifierad i arbetsboken
- aktuell datumtackning i modellen ar `2024-01-01` till `2026-03-17`

Viktig princip:

- urvalsvarden i slicers ska fortsatt komma fran modellens tabeller
- dokumentationen ska inte hardkoda en viss lista med valbara portfoljer, varianter, benchmark eller extra jamforelser

## Faktisk modell i PBIX

### Importomfang

Alla tabeller i `portfolio_bi_data.xlsx` ar importerade till PBIX:en.

Detta ar accepterat i v1 eftersom:

- andringsytan ar liten
- modellen fortfarande ar overskadlig
- framtida `Structure` kan byggas utan ny importfas

### Aktiva och inaktiva relationer

Nuvarande relationer i PBIX ska vara:

- aktiv: `Dim_Date[Date]` -> `Fact_Series_Daily[Date]`
- aktiv: `Dim_Series[Series_ID]` -> `Fact_Series_Daily[Series_ID]`
- aktiv: `Dim_Series[Series_ID]` -> `Fact_Series_KPI[Series_ID]`
- aktiv: `Dim_Portfolio[Portfolio_Key]` -> `Dim_Series[Portfolio_Key]`
- aktiv: `Dim_Series[Series_ID]` -> `Fact_Portfolio_Alloc_Snapshot[Series_ID]`
- aktiv: `Dim_Instrument[Instrument_Key]` -> `Fact_Portfolio_Alloc_Snapshot[Instrument_Key]`
- inaktiv: `Dim_Portfolio[Portfolio_Key]` -> `Fact_Portfolio_Alloc_Snapshot[Portfolio_Key]`
- inaktiv: `Dim_Series[Yahoo_Ticker]` -> `Dim_Instrument[Yahoo_Ticker]`

Motivering:

- Power BI tillater inte samtidigt tva aktiva filtervagar mellan `Fact_Portfolio_Alloc_Snapshot` och `Dim_Portfolio`
- relationen via `Dim_Series` ar den renare primarvagen
- den direkta kopplingen mellan `Dim_Series` och `Dim_Instrument` behovs inte for v1

Rekommenderad fortsatt princip:

- enkelriktad filtrering fran dimension till fakta
- inga dubbelriktade relationer i v1

## Rapportlager i PBIX

Det faktiska rapportlagret i PBIX bestar nu av:

- en extra beraknad etikettkolumn i `Dim_Series`
- fem frikopplade slicertabeller
- en separat measure-tabell
- tio selector-measures
- ett KPI-lager for generiska KPI-measures
- ett separat KPI-lager for primarseriens KPI-kort

Dessa objekt ar ett medvetet rapportlager ovanpa BI-datakontraktet och utgor den praktiska grunden for `Overview` och `Performance`.

Full DAX-referens for dessa objekt dokumenteras i:

- `docs/powerbi_dax_v1.md`

## Beraknad kolumn i `Dim_Series`

### `Series_Label`

Syfte:

- ge en anvandarvanlig etikett for serier i rapporten
- skilja huvudserier, benchmark och framtida kategoriserier tydligare
- undvika att rapportytan visar tekniska `Series_ID`

Logik:

- benchmarkserier visas med en rensad etikett baserad pa benchmarkidentitet
- huvudserier visas som portfolj plus variant
- kategoriserier visas som portfolj plus variant plus kategori

Konsekvens:

- v1 kan anvanda samma etikettkolumn for framtida utbyggnad
- kategoriinformation finns redan forberedd i etiketten, utan att kategori-serier behover exponeras i v1

## Frikopplade slicertabeller

Samtliga slicertabeller ar frikopplade, det vill saga utan relationer till modellens fakta- eller dimensionstabeller.

Skal:

- primarserie, benchmark och extra jamforelse maste kunna valjas oberoende av varandra
- vanlig filterpropagering via relationer racker inte for den logiken
- selector-measures ska styra vilka serier som faktiskt visas i visuals

### `Sel_Primary_Portfolio`

Syfte:

- styr val av primar portfolj i rapporten
- ska representera huvudseriernas portfoljuniversum

Notering:

- tillgangliga val ska folja modellens data

### `Sel_Primary_Variant`

Syfte:

- styr val av primar variant for vald huvudserie

Notering:

- tillgangliga val ska folja modellens data
- standardlaget i v1 ar `REAL`

### `Sel_KPI_Period`

Syfte:

- styr vilken materialiserad KPI-period som ska anvandas i KPI-visuals
- ska vara logiskt separat fran datumurvalet i tidsserievisuals

Notering:

- denna tabell har explicita sorteringsregler for periodordningen
- standardlaget i v1 ar `1Y`

### `Sel_Benchmark`

Syfte:

- styr val av fri benchmarkserie som jamforelse

Notering:

- benchmark ar inte hardkopplad per portfolj
- ingen benchmark ar forvald i v1
- slicern ska stodja flerval
- inget benchmarkval motsvaras av att slicern ar ovald
- tillgangliga benchmarkval ska folja modellens data

### `Sel_Compare_Extra`

Syfte:

- styr val av en extra jamforelseserie utover benchmark

Notering:

- ingen extra jamforelse ar forvald i v1
- slicern ska stodja flerval
- inget extra jamforelseval motsvaras av att slicern ar ovald
- den extra jamforelsen ska valjas endast ur huvuduniversumet
- benchmarkserier ska inte finnas i denna slicer

## Measure-tabell

En separat tabell har skapats for measures.

Nuvarande tabell:

- `Measure_Hub`

Syfte:

- samla rapportens DAX-measures pa en tydlig plats
- undvika att selector-measures sprids over modellens dimensioner och fakta

## Faktiskt skapade selector-measures

Foljande tio measures ar skapade i PBIX och testade.

### Grundurval

#### `Selected Primary Portfolio`

Syfte:

- lasar valt primarportfoljurval fran slicern

#### `Selected Primary Variant`

Syfte:

- lasar vald primarvariant fran slicern
- hanterar standardlage for variant

#### `Selected KPI Period`

Syfte:

- lasar vald KPI-period fran slicern
- hanterar standardlage for KPI-period

#### `Selected Benchmark Series ID`

Syfte:

- lasar vald benchmarkseries tekniska ID
- returnerar entydigt ID endast nar exakt ett benchmark ar valt
- returnerar blankt nar inget benchmark ar valt eller nar flera benchmark ar valda

#### `Selected Extra Series ID`

Syfte:

- lasar vald extra jamforelseseries tekniska ID
- returnerar entydigt ID endast nar exakt en extra jamforelse ar vald
- returnerar blankt nar ingen extra jamforelse ar vald eller nar flera extra jamforelser ar valda

### Resolvering av primarserie

#### `Selected Primary Series ID`

Syfte:

- oversatter kombinationen primar portfolj plus variant till exakt en huvudserie i `Dim_Series`
- ar den centrala resolveringen for primarlogiken i rapporten

Viktig regel:

- resolveringen ska ske endast mot huvudserier
- kategori-serier ska inte kunna bli primarserie i v1

### Visuellt urval

#### `Is Selected Overview Series`

Syfte:

- markerar om en viss serie ska visas i ett v1-visual
- styr de serier som far inga i `Overview` och `Performance`

Nuvarande avsedd logik:

- primarserie inkluderas alltid
- alla valda benchmark inkluderas om benchmark slicern har urval
- alla valda extra jamforelser inkluderas om extra slicern har urval

Praktisk effekt:

- samma visual kan begransas till exakt de serier som rapportens slicerlogik avser

#### `Overview Series Sort Rank`

Syfte:

- ger en dynamisk sortgrupp for jamforelsetabellen pa `Overview`

Avsedd logik:

- primarserie sorteras forst
- valda extra jamforelser sorteras darrefter
- valda benchmark sorteras sist

Praktisk notering:

- denna measure anvands som teknisk sorteringskolumn i tabellvisualen
- losningen valdes eftersom ordningen beror pa aktuella slicerval och darfor inte kan styras stabilt med en statisk modellkolumn

### Etiketter for kontroll och felsokning

#### `Selected Primary Label`

Syfte:

- visar anvandarvanlig etikett for resolverad primarserie

#### `Selected Benchmark Label`

Syfte:

- visar anvandarvanliga etiketter for valda benchmark
- visar ett tydligt textlage nar ingen benchmark ar vald

#### `Selected Extra Label`

Syfte:

- visar anvandarvanliga etiketter for valda extra jamforelser
- visar ett tydligt textlage nar ingen extra jamforelse ar vald

## KPI-lager i DAX

Utifran det byggda rapportlagret finns nu tva nivaer av KPI-measures i PBIX-arbetet:

- generiska KPI-measures som fungerar i tabeller och annan radkontext
- `Primary KPI`-measures som alltid ska folja primarserien i KPI-korten

Syfte med uppdelningen:

- undvika att klick i jamforelsetabeller skriver over kortens primarlogik
- kunna ateranvanda samma KPI-grund i flera visuals

Dokumenterade DAX-definitioner for detta lager finns i:

- `docs/powerbi_dax_v1.md`

## Faktisk filtermodell for v1-ytan

V1-ytan bygger nu pa tva lager:

1. modellrelationer for grundlaggande fakta-dimension-koppling
2. selector-measures for att styra vilka serier som faktiskt ska visas

Detta innebar:

- slicertabellerna filtrerar inte faktat direkt via relationer
- visuals maste i stallet anvanda selector-measures som visualfilter eller i motsvarande measurelogik
- kategori-serier kan hallas dolda trots att de finns i modellen

## Faktisk sidlogik for v1

### `Overview`

Syfte:

- ge en snabb beslutsmassig oversikt for vald primarserie
- mojliggora fri jamforelse mot benchmark och en extra serie

Avsedd filterlogik:

- styrs av primar portfolj
- styrs av variant
- styrs av KPI-period
- styrs av benchmark
- styrs av extra jamforelse

Viktig regel:

- ingen datumstyrning ska paverka KPI-ytan pa `Overview`
- KPI-korten for primarserien ska fortsatt styras av `Primary KPI`-measures och inte skrivas over av klick i jamforelsetabellen

### `Performance`

Syfte:

- visa tidsserieutveckling for primarserie och valda jamforelseserier

Avsedd filterlogik:

- samma serieurval som pa `Overview`
- separat datumurval endast for tidsserievisuals

Notering:

- datumslicer for `Performance` ar identifierad som del av v1 men ar annu inte tillagd i den faktiska rapporten

## Avstamning mot tidigare specifikation

Foljande delar fran tidigare specifikation galler fortfarande:

- `Overview` och `Performance` ar fortsatt enda sidor i v1-scope
- KPI:er ska fortsatt lasas fran `Fact_Series_KPI`
- tidsserier ska fortsatt lasas fran `Fact_Series_Daily`
- benchmark ska fortsatt vara ett fritt val
- kategori-serier ska fortsatt vara dolda i v1-ytan
- KPI-period ska fortsatt vara separat fran datumurval

Foljande delar har konkretiserats eller justerats under PBIX-arbetet:

- alla tabeller ar importerade i PBIX, inte bara de som anvands synligt i v1
- en faktisk rapportetikettkolumn har lagts till i `Dim_Series`
- faktiska frikopplade slicertabeller har skapats
- faktisk measure-tabell har skapats
- faktiskt paket av selector-measures har skapats och testats
- relationsmodellen har justerats till vad Power BI faktiskt tillater, med tva inaktiva relationer i stallet for att forsoka ha bada aktiva

## Kritiska gap

Inga blockerande datamodellgap ar identifierade for att fardigstalla `Overview` och `Performance` i v1.

Foljande kvarvarande gap ligger i rapportlagret, inte i BI-sparet:

- slutlig validering av KPI-lagret i visuals
- tidsseriemeasures eller visuallogik for `IDX` och `DD`
- datumslicer pa `Performance`
- faktisk layout och visualbyggnation for sidorna
- eventuell synkronisering av slicers mellan `Overview` och `Performance`

Foljdnotering for senare faser:

- `Dim_Instrument` ar fortfarande tunn och blir forst relevant nar `Structure` ska byggas

## Aterstaende arbete

For att stanga Power BI-v1 aterstar i huvudsak foljande:

### 1. Slutlig validering av KPI-lagret

Det finns nu en dokumenterad DAX-bas for:

- generiska KPI-measures
- `Primary KPI`-measures for korten

Det som aterstar ar att sakerstalla att de anvands konsekvent i visuals:

- kort ska anvanda `Primary KPI`
- jamforelsetabeller ska anvanda generiska `KPI`
- oonskade visualinteraktioner ska vara avstangda dar det behovs

### 2. Tidsserievisuals for `Performance`

Behovs for att visa:

- indexutveckling baserad pa `Fact_Series_Daily[IDX]`
- drawdown baserad pa `Fact_Series_Daily[DD]`

Minimikrav i v1:

- visuals som endast visar valda serier
- selector-logiken ska begransa serieurvalet

### 3. Datumslicer pa `Performance`

Behovs for att uppfylla last beslut om tidsstyrning.

Regel:

- datumslicern ska bara styra tidsserievisuals pa `Performance`
- den ska inte styra KPI-period eller KPI-tabeller

Detta krav ar identifierat men inte annu implementerat.

### 4. Faktisk sidlayout

Behovs for att fa en komplett v1-rapport:

- `Overview` med slicers, KPI-kort och jamforelsetabell
- `Performance` med slicers, datumslicer, indexgraf, drawdowngraf och KPI-tabell

### 5. Slutlig validering

Behovs innan v1 kan betraktas som klar:

- verifiera att primarserie resolveras korrekt
- verifiera att benchmark kan vara inget val, ett val eller flera val
- verifiera att extra jamforelse kan vara inget val, ett val eller flera val
- verifiera att samma serie inte visas dubbelt i visuals nar valen overlappar
- verifiera att jamforelsetabellen sorterar primarserie fore extra jamforelse och benchmark
- verifiera att datumslicern endast paverkar tidsserievisuals pa `Performance`

## Sammanfattning

Power BI-v1 har nu en faktisk och fungerande grund:

- datamodellen ar etablerad
- rapportlagret med etikettkolumn, slicertabeller och selector-measures ar pa plats
- relationerna ar justerade efter vad Power BI faktiskt tillater

Det som aterstar for att stanga v1 ar framst visual- och measurelagret, inte nya upstream- eller BI-sporsandringar.
