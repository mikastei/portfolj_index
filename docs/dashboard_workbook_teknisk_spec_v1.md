# Teknisk spec - separat Excel-dashboard workbook v1

## Syfte

Detta dokument beskriver en konkret teknisk v1-spec for hur den framtida Excel-dashboarden bor inforas som en separat workbook i projektet.

Målet ar att ge ett direkt underlag for nasta implementationstrad utan att gora en stor omskrivning av nuvarande pipeline.

Specen utgar fran:

- `docs/dashboard_konceptspec.md`
- `docs/dashboard_wireframe_v1.md`
- nuvarande pipeline med `Portfolio_index` och `Dashboard_prep`

## Bakgrund och nulage

Projektet har idag en fungerande tva-stegspipeline:

1. `Portfolio_index`
   - bygger kallsanningen `portfolio_output_timeseries.xlsx`
2. `Dashboard_prep`
   - laser steg 1
   - bygger dashboardunderlaget `portfolio_dashboard_data.xlsx`

Detta innebar att dashboardunderlaget redan finns som en separat maskinell artefakt.

Nasta steg ar att bygga en separat, anvandarorienterad Excel-dashboard ovanpa detta underlag.

Det ar viktigt att halla isar:

- maskinellt dashboardunderlag
- fardig dashboard-workbook for anvandare

## Designprincip for v1

Den enklaste robusta losningen ar att behalla tre tydliga ansvarsnivaer:

1. `Portfolio_index`
2. `Dashboard_prep`
3. framtida `dashboard_workbook`-steg

Dataflodet bor vara:

```text
inputfiler
  ->
portfolio_output_timeseries.xlsx
  ->
portfolio_dashboard_data.xlsx
  ->
portfolio_dashboard.xlsx
```

Detta ar en inkrementell utbyggnad av befintlig struktur, inte en omskrivning.

## Ansvarsfordelning

### 1. `Portfolio_index`

Ansvar:

- lasa inputfiler
- hamta prisdata
- bygga tidsserier och benchmarkserier
- skriva `portfolio_output_timeseries.xlsx`

Ska inte ansvara for:

- dashboardlayout
- dashboardformler
- dashboarddiagram
- output-path for fardig dashboard-workbook

Kommentar:

`Portfolio_index` ska fortsatt vara kallan for grundserier och tidsseriedata.

### 2. `Dashboard_prep`

Ansvar:

- lasa `portfolio_output_timeseries.xlsx`
- bygga dashboardklara tabeller
- filtrera analysuniversum
- exkludera `AST_*`
- skriva `portfolio_dashboard_data.xlsx`

Ska inte ansvara for:

- att bygga anvandargranssnitt i Excel
- att skapa synliga dashboardflikar
- att lagga diagram, styles eller kontrollpaneler i slutworkbooken

Kommentar:

`Dashboard_prep` ska fortsatt vara ett rent downstream-datasteg.

### 3. Framtida dashboard-workbook-steg

Ansvar:

- lasa `portfolio_dashboard_data.xlsx`
- validera att nodvandiga blad finns
- skapa separat dashboard-workbook
- bygga tekniska hjalpblad
- bygga synliga dashboardflikar
- spara workbooken till konfigurerad output-path

Ska inte ansvara for:

- prisnedladdning
- seriebyggande
- KPI-berakning som redan hor hemma i `Dashboard_prep`

Kommentar:

Detta steg ska vara enda komponenten som kanner till dashboardens layout och slutliga workbook-path.

## Rekommenderad modul for framtida workbook-byggande

Workbook-byggandet bor inforas som en separat modul:

- `src/dashboard_workbook.py`

Skal:

- namnet ar konsekvent med befintlig dashboardstruktur
- ansvaret blir tydligt separerat fran `src/dashboard_prep.py`
- steget kan koras fristaende
- det blir enklare att testa, felsoka och vidareutveckla

Rekommenderad entry point:

```bash
py -m src.dashboard_workbook
```

## Rekommenderad plats i pipelinen

Nuvarande pipeline bor behallas och utokas med ett tredje steg:

1. `py -m src.main`
2. `py -m src.dashboard_prep`
3. `py -m src.dashboard_workbook`

Praktisk rekommendation:

- steg 3 ska initialt vara separat och frivilligt under utveckling
- batchfilen behover inte byggas om direkt
- nar workbook-steget ar stabilt kan det laggas till efter `Dashboard_prep`

Detta minimerar risk och gor infasningen enkel.

## Rekommenderad config-modell i `src/config.py`

Config-migreringen ar nu genomford i kodbasen. `src/config.py` anvander de tydligare huvudnamnen for pipelineartefakterna, medan de aldre namnen fortfarande finns kvar som temporara alias for att undvika en halvmigrerad config-yta.

For att undvika sammanblandning skiljer config nu pa:

- portfolio-output
- dashboard-data-input/output
- dashboard-workbook-output

### Faktiska config-konstanter i nuvarande kod

- `PORTFOLIO_OUTPUT_PATH`
- `DASHBOARD_DATA_SOURCE_PATH`
- `DASHBOARD_DATA_OUTPUT_PATH`
- `DASHBOARD_WORKBOOK_OUTPUT_PATH`

### Betydelse

`PORTFOLIO_OUTPUT_PATH`

- output fran `Portfolio_index`
- normalt `portfolio_output_timeseries.xlsx`

`DASHBOARD_DATA_SOURCE_PATH`

- input till `Dashboard_prep`
- normalt samma som `PORTFOLIO_OUTPUT_PATH`

`DASHBOARD_DATA_OUTPUT_PATH`

- output fran `Dashboard_prep`
- normalt `portfolio_dashboard_data.xlsx`

`DASHBOARD_WORKBOOK_OUTPUT_PATH`

- output fran framtida workbook-steg
- normalt den fardiga dashboardfilen

### Faktisk config-status

```python
PORTFOLIO_OUTPUT_PATH = BASE_DIR / "data" / "portfolio_output_timeseries.xlsx"
DASHBOARD_DATA_SOURCE_PATH = PORTFOLIO_OUTPUT_PATH
DASHBOARD_DATA_OUTPUT_PATH = BASE_DIR / "data" / "portfolio_dashboard_data.xlsx"
DASHBOARD_WORKBOOK_OUTPUT_PATH = BASE_DIR / "data" / "portfolio_dashboard.xlsx"

# Temporary aliases kept to avoid a half-migrated config surface.
OUTPUT_PATH = PORTFOLIO_OUTPUT_PATH
DASHBOARD_SOURCE_OUTPUT_PATH = DASHBOARD_DATA_SOURCE_PATH
DASHBOARD_OUTPUT_PATH = DASHBOARD_DATA_OUTPUT_PATH
```

Nuvarande kodlage:

- `src.main` anvander `PORTFOLIO_OUTPUT_PATH`
- `src.dashboard_prep` anvander `DASHBOARD_DATA_SOURCE_PATH` och `DASHBOARD_DATA_OUTPUT_PATH`
- de aldre namnen finns kvar som overgangslosning och bakatkompatibla alias
- `DASHBOARD_WORKBOOK_OUTPUT_PATH` finns redan i config men ar annu inte kopplad till ett separat workbook-byggsteg

## Rekommenderad standardpath i v1

For v1 bor den fardiga dashboard-workbooken skrivas lokalt i projektet:

- `BASE_DIR / "data" / "portfolio_dashboard.xlsx"`

Motivering:

- minst friktion i utveckling
- enklare for agenter att lasa/skriva
- mindre risk for OneDrive-lasning eller sync-problem
- enklare loggning och felsokning
- konsekvent med ovriga outputfiler i projektet

## Hur extern OneDrive-path aktiveras senare

Nar workbook-steget ar stabilt kan samma losning peka om till extern path utan kodandring.

Det ska ske genom att bara andra:

- `DASHBOARD_WORKBOOK_OUTPUT_PATH`

Exempel:

```python
DASHBOARD_WORKBOOK_OUTPUT_PATH = Path(
    r"C:\Users\mikae\OneDrive - Emsek AB\...\portfolio_dashboard.xlsx"
)
```

Krav pa implementationen:

- workbook-steget ska lasa output-path fran config eller CLI-override
- ingen hardkodad OneDrive-logik ska finnas i workbookmodulen
- fel vid skrivning ska loggas tydligt med faktisk path

Detta gor att lokal projektpath kan vara standard i v1 medan extern placering senare blir ett rent configbyte.

## Vad som ska ateranvandas

Foljande ska ateranvandas direkt fran befintliga dataartefakter:

- `portfolio_output_timeseries.xlsx` som upstream-kalla till `Dashboard_prep`
- `portfolio_dashboard_data.xlsx` som enda datakalla for dashboard-workbooken

Foljande blad i `portfolio_dashboard_data.xlsx` bor anvandas som input till workbooken:

- `KPI_Summary`
- `Period_Returns`
- `Chart_IDX_Wide`
- `Chart_DD_Wide`
- `Allocation_Snapshot`
- `Dashboard_Config`
- `Build_Info`

`Correlation_Long` bor finnas kvar i underlaget men behover inte inga i dashboardens synliga v1-flikar.

## Vad som ska vara separat

Foljande ska inte byggas in i datafilen utan hora till dashboard-workbooken:

- synliga dashboardflikar
- tekniska hjalpblad
- kontrollpaneler
- dropdown-listor
- named ranges
- dashboardspecifika formler
- diagram
- formatering och layout

Det ar viktigt att dashboard-workbooken aldrig skriver tillbaka till `portfolio_dashboard_data.xlsx`.

## Rekommenderad workbook-arkitektur for v1

Utifran wireframe-specen bor workbooken pa sikt innehalla:

Synliga flikar:

- `Overview`
- `Performance`
- `Structure`
- `Category`

Tekniska hjalpflikar:

- `Control`
- `Lists`
- `Calc_Main`
- `Calc_Category`

Pragmatisk teknisk princip:

- `portfolio_dashboard_data.xlsx` ar datakontraktet
- `portfolio_dashboard.xlsx` ar presentationslagret

## Batchkorning och felhantering

Rekommenderad framtida korordning i batch:

1. kor `src.main`
2. kor `src.dashboard_prep` om steg 1 lyckas
3. kor `src.dashboard_workbook` om steg 2 lyckas

Felhantering bor folja dessa principer:

- varje steg ska faila med tydlig exit code
- workbook-steget ska logga vilken inputfil och outputfil som anvands
- skrivfel mot extern path ska inte maskera att steg 1 och 2 lyckades
- dataunderlaget ska finnas kvar aven om workbook-steget misslyckas

Detta ar viktigt for scheduler-korning och felsokning.

## Identifierade risker

### 1. Sammanblandning mellan datafil och dashboardfil

Risk:

- att `portfolio_dashboard_data.xlsx` och den fardiga dashboard-workbooken behandlas som samma artefakt
- att confignamn blir missvisande

Atgard:

- separata confignamn for data och workbook
- separata entry points
- separata filnamn

### 2. OneDrive-pathar

Risk:

- fillasning
- sync-konflikter
- intermittenta skrivfel
- mer svarfelsokta batchproblem

Atgard:

- lokal projektpath som default i v1
- extern path endast via config
- tydlig loggning av faktisk output-path

### 3. Framtida underhall

Risk:

- `Dashboard_prep` blir ett blandsteg som hanterar bade data och layout
- svagare ansvarsgraenser

Atgard:

- lat `Dashboard_prep` forbli datasteg
- lagg workbooklogik i egen modul

### 4. Batchkorning och felhantering

Risk:

- att workbook-steg gor hela korningen skorare
- att fel i extern output-path stoppar hela flodet utan tydlig diagnos

Atgard:

- separat steg med egen loggning
- tydlig input/output-validering
- stegvis korning dar varje steg ar sparbart

### 5. Agenters filskrivning och behorighetsfriktion

Risk:

- skrivning utanfor projektet kan ge onodig friktion
- OneDrive-sokvagar kan vara mer kansliga i agentmiljo

Atgard:

- skriv lokalt i projektet i v1
- hall config enkel
- aktivera extern path senare nar workbook-steget ar verifierat

## Enkel robust v1-losning

Den rekommenderade v1-losningen ar:

1. behall `Portfolio_index` oforandrat i sitt ansvar
2. behall `Dashboard_prep` som separat datasteg
3. utga fran den redan genomforda config-separationen mellan datafil och workbookfil
4. bygg senare ett separat `src/dashboard_workbook.py`
5. lat workbook-steget lasa endast `portfolio_dashboard_data.xlsx`
6. skriv workbooken lokalt till `data/portfolio_dashboard.xlsx`
7. gor extern OneDrive-path till ett senare rent configval

Detta ar den enklaste stabila losningen som:

- minimerar friktion
- passar nuvarande struktur
- ar latt att bygga vidare pa
- ar tydlig for bade manuella utvecklare och agenter

## Rekommenderade nasta implementationstradar

1. rensa bort de temporara aliasen i `src/config.py` nar hela kodbasen ar migrerad
2. skapa `src/dashboard_workbook.py` som separat entry point
3. implementera enkel workbook-skapning lokalt i projektets `data/`
4. koppla workbook-steget till `DASHBOARD_WORKBOOK_OUTPUT_PATH`
5. lagga till steg 3 i batchfilen nar implementationen ar verifierad

## Sammanfattande beslutspaket

Foljande bor lasas som teknisk riktning for v1:

- dashboarden ska byggas som separat workbook
- dashboard-workbooken ska inte blandas ihop med dashboarddatafilen
- v1 ska skriva workbooken lokalt i projektet
- extern OneDrive-path ska aktiveras senare via config
- workbook-byggandet ska ligga i egen modul
- workbook-steget ska passa in som steg 3 i nuvarande pipeline
- nuvarande pipeline ska utokas inkrementellt, inte skrivas om

