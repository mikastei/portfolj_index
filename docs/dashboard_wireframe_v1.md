# Dashboard Wireframe V1

Detta dokument beskriver en konkret, beslutsbar v1-spec for en separat Excel-dashboard ovanpa `portfolio_dashboard_data.xlsx`.

Syftet ar att ge en enkel, robust och utbyggbar grund for senare implementation, utan att blanda in v2-funktionalitet for tidigt.

## 1. Rekommenderad workbook-struktur

Synliga flikar i v1:

- `Overview`
- `Performance`
- `Structure`
- `Category`

Tekniska hjalpflikar i den framtida dashboard-workbooken:

- `Control`
- `Lists`
- `Calc_Main`
- `Calc_Category`
- `Source_*` eller lankade tabeller fran `portfolio_dashboard_data.xlsx`

Pragmatisk rekommendation:

- Bygg v1 med en gemensam central kontrollmodell i `Control`.
- Visa bara en tunn statusrad overst pa varje synlig flik som laser samma kontrollceller.
- Hall `Category` delvis separat med egna kategorikontroller, eftersom dess universum skiljer sig fran huvudserierna.

Analysuniversum i v1:

- Huvuduniversum: huvudportfoljserier + benchmark
- Separat universum: kategoriunika `REAL`-serier
- Exkludera helt: `AST_*`

## 2. Anvandarlogik i v1

Global huvudlogik for `Overview`, `Performance`, `Structure`:

- `Primar portfolj`: valj `Portfolio_Name`
- `Primar variant`: valj `REAL`, `CUR`, `TGT`
- `Period`: valj `30D`, `YTD`, `1Y`, `Since_Start`
- `Jamforelse 1-3`: valj upp till 3 valfria serier ur huvuduniversumet
- Jamforelseserier far vara benchmark, andra portfoljer eller andra portfoljvarianter
- Kategori-REAL far inte finnas i dessa jamforelsefalt

Separat logik for `Category`:

- `Portfolj`: valj `Portfolio_Name`
- `Period`: valj `30D`, `YTD`, `1Y`, `Since_Start`
- `Kategori 1-3`: valj upp till 3 kategoriunika `REAL`-serier for vald portfolj
- Variant ska vara last till `REAL` i denna flik

Rekommenderad standardlogik i v1:

- Defaultvariant: `REAL`
- Defaultperiod: `1Y`
- Antal jamforelseserier: 3
- Jamforelsefalt: tomma som standard
- Primarserie vid oppning: en definierad standardportfolj i `Control` eller forsta alfabetiska huvudportfolj om ingen explicit default satts

Motivering:

- `1Y` ar battre dashboard-default an `Since_Start` for snabb lasbarhet
- tomma jamforelsefalt haller forsta intrycket rent
- max 3 jamforelser ar tillrackligt for v1 utan att diagrammen kollapsar visuellt

## 3. Wireframe per flik

### `Overview`

Syfte:

- Ge en snabb, beslutsmassig sammanfattning av vald primarserie med latt jamforelse mot nagra fa andra serier.

Placering av kontrollpanel:

- Overst till vanster, horisontell kompakt panel
- Innehall: Primar portfolj, primar variant, period, jamforelse 1-3
- Till hoger om panelen: aktiv statusrad med vald serie och data-end-date

Wireframe:

```text
+----------------------------------------------------------------------------------+
| OVERVIEW                                                                         |
| [Primar portfolj] [Variant] [Period] [Jmf 1] [Jmf 2] [Jmf 3]   [Senast data-dag] |
+----------------------------------------------------------------------------------+
| KPI-kort primarserie                                                             |
| Return | CAGR | Vol | Sharpe | Max DD | Calmar                                   |
+----------------------------------------------------------------------------------+
| Jamforelsetabell                                                                  |
| Serie | Typ | Period | Return | CAGR | Vol | Sharpe | Max DD | Sortino | Calmar |
+----------------------------------------------------------------------------------+
| Mini-panel: Periodreturer                                                         |
| Serie | 30D | YTD | 1Y | Since_Start                                             |
+----------------------------------------------------------------------------------+
| Kort kommentar-/tolkningsyta (valfri, statisk text i v1)                         |
+----------------------------------------------------------------------------------+
```

Visuella block:

- KPI-kort for primarserie
- Jamforelsetabell for primar + valda jamforelser
- Periodreturstabell
- Enkel informationsrad om datum/intervall

KPI:er/tabeller/diagram:

- KPI-kort: `Return_Total`, `CAGR`, `Vol`, `Sharpe`, `Max_DD`, `Calmar`
- Jamforelsetabell: samma KPI:er + `Sortino`
- Periodreturer: `30D`, `YTD`, `1Y`, `Since_Start`

Datakallor:

- `KPI_Summary`
- `Period_Returns`
- `Build_Info`
- eventuellt `Dashboard_Config` for defaultvarden

Kommentar:

- Ingen graf har i v1. `Overview` ska vara tabell- och KPI-tung for snabb scanning.

### `Performance`

Syfte:

- Visa hur primarserien utvecklats over tid relativt jamforelser.

Placering av kontrollpanel:

- Ingen separat full kontrollpanel om gemensam `Control` anvands
- Overst: tunn statusrad som visar aktivt urval och ev. knapp/indikering "styrt fran Control"
- Om man vill forenkla implementation: duplicera samma kontrollfalt som i `Overview`

Wireframe:

```text
+----------------------------------------------------------------------------------+
| PERFORMANCE                                                                      |
| Primar: [Egen | REAL]  Period: [1Y]  Jmf: [BM1] [Portfolj B REAL] [Portfolj C TGT]|
+----------------------------------------------------------------------------------+
| Diagram 1: Indexutveckling                                                        |
| Primarserie + upp till 3 jamforelseserier                                        |
+----------------------------------------------------------------------------------+
| Diagram 2: Drawdown                                                                |
| Samma serier som ovan                                                             |
+----------------------------------------------------------------------------------+
| Tabell: Periodreturer och risk                                                    |
| Serie | 30D | YTD | 1Y | Since_Start | Vol | Max DD | Sharpe                     |
+----------------------------------------------------------------------------------+
```

Visuella block:

- Huvuddiagram: indexutveckling
- Sekundardiagram: drawdown
- Sammanfattande tabell under diagrammen

KPI:er/tabeller/diagram:

- Linjediagram pa `IDX`
- Linjediagram pa `DD`
- Tabell med periodreturer + karnriskmatt

Datakallor:

- `Chart_IDX_Wide`
- `Chart_DD_Wide`
- `Period_Returns`
- `KPI_Summary`

Kommentar:

- Lagg inte in separat risk-scatter eller korrelationsheatmap i v1.
- `Performance` absorberar den enklaste riskvyn genom drawdown-blocket.

### `Structure`

Syfte:

- Visa aktuell portfoljstruktur for vald primar portfolj/variant, utan att blanda in historiska kategori-REAL-serier.

Placering av kontrollpanel:

- Overst: `Primar portfolj`, `Primar variant`
- Period behovs inte funktionellt for denna flik och bor darfor visas som read-only status, inte aktiv kontroll

Wireframe:

```text
+----------------------------------------------------------------------------------+
| STRUCTURE                                                                        |
| [Primar portfolj] [Variant]                                      [As-of snapshot] |
+----------------------------------------------------------------------------------+
| Diagram: Viktfordelning                                                           |
| Toppinnehav som horisontella staplar                                              |
+----------------------------------------------------------------------------------+
| Tabell: Full allokering                                                           |
| Yahoo_Ticker | Weight | Weight_Source                                             |
+----------------------------------------------------------------------------------+
| Enkel sammanfattning                                                              |
| Antal innehav | Summa vikt | Ev. avvikelse fran 100%                              |
+----------------------------------------------------------------------------------+
```

Visuella block:

- Stapeldiagram for storsta innehaven
- Full detaljerad allokeringstabell
- Kontrollrad med snapshot-info

KPI:er/tabeller/diagram:

- Topp 10 eller topp 15 innehav som staplar
- Full allocation-tabell
- Enkel kontrollsumma

Datakallor:

- `Allocation_Snapshot`
- eventuellt `Build_Info` for metadata
- eventuell filterlogik fran `Dashboard_Config`

Kommentar:

- Ingen kategorisering eller sektorgruppering i v1 om det inte redan finns i underlaget.
- Fokus ska vara robust visning av nuvarande viktbild.

### `Category`

Syfte:

- Ge separat drilldown for kategoriunika `REAL`-serier utan att blanda dem med huvudvyerna.

Placering av kontrollpanel:

- Egen kontrollpanel hogst upp
- Falt: `Portfolj`, `Period`, `Kategori 1`, `Kategori 2`, `Kategori 3`
- Ingen variantkontroll; last till `REAL`

Wireframe:

```text
+----------------------------------------------------------------------------------+
| CATEGORY                                                                         |
| [Portfolj] [Period] [Kategori 1] [Kategori 2] [Kategori 3]   [Variant: REAL]     |
+----------------------------------------------------------------------------------+
| KPI-tabell kategori                                                               |
| Kategori | Return | CAGR | Vol | Sharpe | Max DD                                 |
+----------------------------------------------------------------------------------+
| Diagram 1: Kategoriutveckling                                                     |
| Upp till 3 valda kategoriserier                                                   |
+----------------------------------------------------------------------------------+
| Diagram 2: Kategori-drawdown                                                      |
| Upp till 3 valda kategoriserier                                                   |
+----------------------------------------------------------------------------------+
| Tabell: Periodreturer kategori                                                    |
| Kategori | 30D | YTD | 1Y | Since_Start                                          |
+----------------------------------------------------------------------------------+
```

Visuella block:

- KPI-tabell for valda kategorier
- Kategori-indexgraf
- Kategori-drawdown
- Periodreturstabell

KPI:er/tabeller/diagram:

- Samma karn-KPI:er som for huvudserier, men endast for kategoriunika `REAL`
- Max tre kategorier samtidigt for tydlighet

Datakallor:

- `KPI_Summary`
- `Period_Returns`
- `Chart_IDX_Wide`
- `Chart_DD_Wide`

Kommentar:

- Inga benchmark i `Category`
- Inga `CUR`/`TGT` har
- Denna separering ar central for att undvika begreppsforvirring

## 4. Kontrollpanel och filter

Rekommendation:

- En gemensam faktisk kontrollpanel i `Control`
- En visuell statusrad pa varje synlig flik
- En separat liten kontrollsektion for `Category`, eftersom dess urvalslogik skiljer sig

Falt i `Control`:

- `Selected_Portfolio`
- `Selected_Variant`
- `Selected_Period`
- `Selected_Compare_1`
- `Selected_Compare_2`
- `Selected_Compare_3`
- `Selected_Category_Portfolio`
- `Selected_Category_1`
- `Selected_Category_2`
- `Selected_Category_3`
- `Default_Portfolio`

Listor i `Lists`:

- huvudserier for primarval
- huvudserier for jamforelseval
- kategoriserier per portfolj
- periodlista
- variantlista

Praktisk filterregel:

- Primarval ska bara kunna landa i huvudportfoljserier
- Jamforelseval ska bara kunna landa i huvudportfoljer eller benchmark
- Kategorival ska bara kunna landa i kategoriunika `REAL`-serier for vald portfolj

## 5. Tydlig avgransning mot v2

Bygg inte detta i v1:

- Ingen korrelationsheatmap
- Ingen fri multi-select bortom 3 jamforelseserier
- Ingen automatisk benchmarkkoppling per portfolj
- Ingen avancerad drillthrough mellan flikar
- Ingen risk/return-scatter
- Ingen historisk strukturanalys over tid
- Ingen kategori-analys blandad in i `Overview` eller `Performance`
- Ingen makrostyrd avancerad UI-logik om det gar att losa med formler, named ranges och vanliga diagram

## 6. Praktiska Excel-designrekommendationer

Gemensam eller flikspecifik kontrollpanel:

- Valj gemensam kontrollpanel som sann kalla
- Visa tunna, flikspecifika statusfalt for lasbarhet
- Undantag: `Category` far egen kontrollsektion

Hur layouten halls enkel och robust:

- Max 2 diagram per flik
- Max 1 huvudtabell per flik
- Fasta blockhojder och bredder
- Samma plats for kontroll/status overst pa alla flikar
- Undvik pivottunga losningar om vanliga tabeller racker
- Bygg diagram mot kontrollerade hjalpomraden, inte direkt mot rablad

Hur kategori-REAL halls separerat:

- Egen flik
- Egna dropdown-listor
- Tydlig etikett: "Category analysis (REAL only)"
- Ingen kategori i huvudjamforelselistan
- Garna egen accentfarg eller rubrikstil for `Category`

## 7. Rekommenderat beslutspaket for att lasa v1

Jag rekommenderar att foljande lasses nu:

- Synliga v1-flikar: `Overview`, `Performance`, `Structure`, `Category`
- Defaultvariant: `REAL`
- Defaultperiod: `1Y`
- Jamforelseserier i huvudvyer: max 3
- Jamforerelsefalt: tomma vid oppning
- `Category` ar helt separat och `REAL`-last
- Ingen korrelationsvy i v1
- Ingen dedikerad `Risk`-flik i v1; drawdown ligger i `Performance`
- Gemensam kontrollmodell i `Control`, med hjalpblad for listor och kalkylomraden

Detta ar den enklaste robusta v1-losningen och gar latt att bryta ned i separata implementationstradar:

1. kontrollmodell och listlogik
2. `Overview`
3. `Performance`
4. `Structure`
5. `Category`
6. workbook-output och config-koppling

## 8. Valideringsnotering

Specen ar framtagen utifran kod- och dokumentlasning i repo:

- `docs/dashboard_konceptspec.md`
- `docs/Teknisk_sammanfattning_portfolio_index.md`
- `src/dashboard_io.py`
- `src/dashboard_metrics.py`
- `src/dashboard_tables.py`
- `src/dashboard_prep.py`

Direkt inspeektion av workbookinnehall kunde inte koras fullt ut i denna miljo, sa exakt lista over nuvarande portfoljnamn och serier aterstar att verifiera vid implementation.
