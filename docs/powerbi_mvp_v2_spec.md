# Power BI v2-spec

## Syfte

Detta dokument beskriver den pragmatiska scope-bilden for Power BI-v2 ovanpa `data/portfolio_bi_data.xlsx`.

Dokumentet ska fungera som:

- arbetsgrund for Power BI-v2
- gemensam referens for scope, avgransningar och beroenden
- underlag for separata arbetstradar per sida

Detta dokument ar alltsa inte en full detaljspec an, utan en kompakt och styrande v2-ram som kan fyllas pa efterhand.

## Utgangspunkt i v1

Power BI-v1 betraktas som en liten och stabil grund med:

- `Overview` for KPI-kort och jamforelsetabell
- `Performance` for lokal datumstyrning, rebased `IDX` och `DD`
- Python-materialiserade KPI:er i BI-sparet
- kategori-serier kvar i modellen men dolda i v1-ytan

V2 ska bygga vidare inkrementellt pa denna grund och inte starta om rapportupplagget.

## Scope for v2

Ingaar i v2:

- fortsatt anvandning av `data/portfolio_bi_data.xlsx`
- fortsatt liten och stabil modell ovanpa befintligt BI-datakontrakt dar det ar mojligt
- forbattrad `Overview` med tydligare rollmarkering i jamforelsetabellen
- `Performance` med snabbval for datumintervall
- ny `Structure`-sida som visar snapshot per `Category` for vald portfolj
- jamforelse mellan `CUR` och `TGT` i `Structure`
- innehavslista i `Structure` som kan visa samtliga innehav och filtreras via kategori

Ingaar inte i v2:

- direktlasning av `transaktioner.xlsx`
- stor omskrivning av rapportlager eller datamodell utan tydligt behov
- DAX-omlaggning av KPI:er som redan ar materialiserade i Python
- hardkopplad benchmark per portfolj
- begransningslogik som hindrar anvandaren fran att valja manga benchmark eller extra jamforelseserier
- historisk struktur
- anvandning av `REAL` i `Structure`
- separat `Category`-sida
- koncentrationspaket eller fordjupad kategorianalys utover enkel analyskontext

## Verifierad grund for v2

V2 utgar fortsatt fran samma importerade arbetsbok som v1:

- `Dim_Date`
- `Dim_Portfolio`
- `Dim_Series`
- `Dim_Instrument`
- `Fact_Series_Daily`
- `Fact_Series_KPI`
- `Fact_Portfolio_Alloc_Snapshot`

Nuvarande dokumenterade baslinje fran v1:

- `Overview` och `Performance` ar redan byggda och manuellt verifierade
- befintligt rapportlager med slicertabeller och selector-measures fungerar for serieurval
- `Fact_Portfolio_Alloc_Snapshot` finns redan i modellen och ar den naturliga grunden for `Structure`

Viktig v2-princip:

- `Overview` och `Performance` ska i forsta hand utvecklas i rapportlagret
- `Structure` ska ocksa i forsta hand forsokas losas i rapportlagret, men endast om snapshot-datat racker tydligt

## Faktisk modell i PBIX

### Importomfang

Utgangspunkten for v2 ar oforandrad import av hela `portfolio_bi_data.xlsx`.

Detta ar fortfarande rimligt eftersom:

- modellen ar liten
- v1 redan ar stabil ovanpa denna import
- `Structure` sannolikt kan byggas ovanpa redan importerade tabeller

### Relationer

V2 ska initialt utga fran samma dokumenterade relationsbas som v1.

Huvudprinciper:

- enkelriktad filtrering fran dimension till fakta
- inga dubbelriktade relationer som standard
- inga modellandringar utan tydligt behov fran `Structure`

## Rapportlager i PBIX

V2 ska bygga vidare pa v1:s rapportlager, inte ersatta det.

Sannolika tillagg i rapportlagret for v2:

- tydligare rollpresentation for rader i `Overview`
- enkel logik for datum-snabbval i `Performance`
- ett litet measure-lager for `Structure`, exempelvis vikt, malvikt och avvikelse per kategori eller innehav

Viktig princip:

- ny logik ska laggas till stegvis och bara nar den ger tydlig nytta pa rapportytan

## Sidlogik for v2

Notering:

- `Overview`, `Performance` och `Structure` har nu exakt v2-scope i detta dokument
- KPI-period hor hemma i `Overview`
- datumstyrning hor hemma i `Performance`
- strukturfilter hor hemma i `Structure`

### `Overview`

Syfte:

- ge snabb beslutsoversikt for vald primarserie
- visa jamforelser tydligare utan att gora sidan tyngre

Exakt scope i v2:

- sidan ska fortsatt vara rapportens lilla KPI- och jamforelsesida
- sidan ska fortsatt utga fran exakt en primarserie
- jamforelser ska visas tydligare framfor allt genom klar rollmarkering i tabellen
- samma grundlogik som i v1 ska behallas dar den redan fungerar
- sidan ska inte byggas ut till en tung dashboardyta

Block som ska inga:

- befintliga KPI-kort for primarserien
- befintlig jamforelsetabell
- befintliga selectors for primarval, KPI-period och fria jamforelser

Filter- och selector-logik:

- samma frikopplade selector-logik som i v1
- `Primary Portfolio`
- `Primary Variant`
- `KPI Period`
- fri benchmark
- fri extra jamforelse
- ingen lokal datumstyrning pa sidan
- KPI-korten ska fortsatt styras av primarserien och inte skrivas over av klick i tabellen

Hur jamforelsetabellen ska fungera:

- tabellen ska fortsatt vara det centrala jamforelseblocket pa sidan
- varje rad ska tydligt markeras som `Primar`, `Jamforelse` eller `Benchmark`
- rollmarkeringen bor losas i tabellen, inte genom att dela upp innehallet i flera separata visuals
- tabellen ska fortsatt sorteras sa att primarserie visas forst, extra jamforelser darefter och benchmark sist
- eventuell visuell polish ska vara diskret, exempelvis via kolumnrubriker, kolumnordning eller enkel conditional formatting

KPI-logik:

- KPI:erna ska fortsatt lasas fran befintligt Python-materialiserat KPI-underlag
- ingen ny KPI-berakning i DAX ska inga i `Overview`-scope for v2

Ingaar inte i `Overview`-scope for v2:

- nytt separat visual for extra oversikt
- kategoriinnehall
- ny KPI-logik
- datumstyrning eller tidsserievisuals
- guardrails som begransar hur manga benchmark eller extra jamforelser anvandaren far valja

Risker och beroenden:

- om manga benchmark eller extra valjs blir tabellen mer svarlast, men detta ligger fortsatt pa anvandaren
- befintlig selector-logik och sortlogik behover fortsatt racka for att skilja primarserie, extra jamforelse och benchmark pa ett robust satt

### `Performance`

Syfte:

- visa utveckling och drawdown for samma serieurval som i `Overview`
- gora datumstyrningen snabbare och enklare att anvanda

Exakt scope i v2:

- sidan ska fortsatt vara en ren tidsseriesida
- sidan ska fortsatt utga fran samma primarserie och samma valda jamforelseserier som `Overview`
- datumstyrningen ska bli snabbare via enkla snabbval, men fortsatt vara lokal for sidan
- snabbvalen ska vara ett bekvamlighetslager for datumintervall, inte en ersattning for fri datumstyrning
- sidan ska inte byggas ut till KPI-, risk- eller periodanalysyta

Block som ska inga:

- en lokal rad eller kontrollgrupp for datum-snabbval
- en lokal datumslicer pa `Dim_Date[Date]` i `Between`-lage for fri datumstyrning
- ett linjediagram for rebased `IDX`
- ett linjediagram for `DD`

Filter- och selector-logik:

- samma frikopplade selector-logik som i v1 och `Overview`
- `Primary Portfolio`
- `Primary Variant`
- fri benchmark
- fri extra jamforelse
- samma resolvering av primarserie som i v1
- samma urval av synliga serier som i v1, det vill saga primarserie plus valda benchmark och extra jamforelser
- ingen egen KPI-periodlogik pa sidan
- lokal datumstyrning ska bara paverka `Performance`
- datumstyrningen pa `Performance` ska inte syncas sa att den spiller over till `Overview` eller `Structure`

Datum-snabbval som ska inga:

- `1M`
- `3M`
- `YTD`
- `1Y`

Semantik for snabbval:

- snabbval ska ankras till senaste tillgangliga datum for vald primarserie, inte till dagens systemdatum
- `1M`, `3M` och `1Y` ska tolkas som rullande intervall bakat fran detta slutdatum
- `YTD` ska betyda fran 1 januari i slutdatumets ar till samma slutdatum
- jamforelseserier som saknar observationer pa delar av intervallet ska visas med den data som finns, utan att andra snabbvalets perioddefinition

Hur snabbval och fri datumstyrning ska samexistera:

- snabbval ska ge ett snabbt standardurval for nagra vanliga datumintervall
- den fria datumslicern ska fortsatt vara den slutliga datumstyrningen
- anvandaren ska kunna valja ett snabbval och sedan finjustera datum manuellt i slicern
- hela tillgangliga historiken ska fortsatt vara natbar via den fria slicern
- om manuell datumjustering inte langre motsvarar ett standardintervall ska laget betraktas som `Custom`
- `Custom` ska fortsatt vara ren datumlogik och inte kopplas till KPI-period

Ingaar inte i `Performance`-scope for v2:

- KPI-tabell eller KPI-kort pa sidan
- nya tidsserievisuals utover `IDX` och `DD`
- fler risk- eller periodmatt
- ny separat selector-logik for serienivor
- global eller syncad datumstyrning som paverkar andra sidor
- sammanblandning av datum-snabbval med `KPI Period`

Risker och beroenden:

- snabbval som ankras till systemdatum i stallet for senaste tillgangliga datapunkt riskerar att ge forvirrande intervall
- snabbval och fri datumslicer behover ett tydligt `Custom`-lage for att inte skapa oklarhet i UI
- enklaste mojliga losning i rapportlagret ska foredras framfor stor ny datumlogik

### `Structure`

Syfte:

- ge en tydlig snapshot-bild av aktuell portfoljstruktur per `Category`
- ge en enkel och direkt jamforelse mellan `CUR` och `TGT`
- ge latt analyskontext utan att glida over i en full `Category`-produkt

Exakt scope i v2:

- sidan ska vara en ren snapshot-sida, utan historik
- sidan ska alltid utga fran exakt en vald portfolj
- sidan ska alltid jamfora `CUR` mot `TGT`
- `REAL` ska inte anvandas pa sidan
- `Category` ar huvudnivan for oversikt
- innehav ar detaljnivan for nedbrytning

Block som ska inga:

- ett huvudblock for viktfordelning per `Category`
- ett litet KPI-block for enkel analyskontext
- en innehavslista for samtliga innehav i vald portfolj

Filter- och selector-logik:

- sidan ska ateranvanda befintligt `Primary Portfolio` som portfoljval
- portfoljvalet ska vara single-select
- sidan ska inte styras av benchmark, extra jamforelse eller KPI-period
- sidan ska inte exponera en egen variantslicer
- `Primary Variant` ska inte styra sidan
- variantsammanstallningen ska vara intern och alltid losas som `CUR` mot `TGT`
- klick pa en kategori ska filtrera innehavslistan
- utan kategorival ska innehavslistan visa hela innehavsuniversumet for vald portfolj

Visualupplagg:

- huvudvisual: horisontell grupperad stapel per `Category`
- varden: `CUR %` och `TGT %`
- sortering: fallande pa `CUR %`
- avvikelse: `Delta pp = CUR - TGT` ska visas som tooltip eller etikett
- avvikelse ska uttryckas i procentenheter, inte relativ procent

Hur viktfordelning per `Category` bor visas:

- varje kategori ska visas som en rad med tva vikter: `CUR` och `TGT`
- kategorier utan vikt i ena varianten ska fortsatt kunna visas med `0`
- fokus ska ligga pa enkel lasbarhet, inte pa avancerad decomposition

Hur `CUR` och `TGT` bast jamfors:

- huvudjamforelsen ska ske side-by-side i samma kategorivisual
- `Delta pp` ska anvandas som enkel avvikelseindikator
- jamforelsen ska bygga pa `Variant` i seriedimensionen, inte pa `Weight_Source`

Kategori-KPI:er som ar mest relevanta i v2:

- storsta kategori i `CUR`
- storsta overvikt mot `TGT`
- storsta undervikt mot `TGT`

KPI-blocket ska vara litet och ge snabb orientering, inte bli en egen analysyta.

Hur innehavslistan bor fungera:

- listan ska visa samtliga innehav for vald portfolj
- klick pa kategori ska filtrera listan till den valda kategorin
- utan kategorifilter ska listan visa alla innehav
- foreslagna kolumner: `Holding`, `Category`, `CUR %`, `TGT %`, `Delta pp`
- innehav som bara finns i `CUR` eller bara i `TGT` ska fortfarande visas, med `0` i den andra kolumnen

Ingaar inte i `Structure`-scope for v2:

- `REAL`
- historisk struktur
- kategori-tidsserier
- separat `Category`-sida
- benchmark eller extra jamforelse pa sidan
- KPI-periodlogik pa sidan
- koncentrationspaket eller fordjupad kategorianalys
- drillthrough eller annan tung interaktionslogik

Risker och beroenden:

- nuvarande snapshot-fakta verkar racka for portfolj, variant och innehav
- nuvarande BI-artefakt rackar inte fullt ut for kategori pa ratt grain
- portfoljfiltreringen ser sannolikt losbar ut via `Dim_Portfolio -> Dim_Series -> Fact_Portfolio_Alloc_Snapshot`
- innehavslistan behover robust logik for att visa innehav som bara finns i ena varianten

## Rapportlager kontra BI-spar

Sannolikt rapportlager:

- rollmarkering, tabellsortering och eventuell diskret tabellpolish pa `Overview`
- datum-snabbval pa `Performance`
- enkel logik for att lata snabbval och fri datumslicer samexistera pa `Performance`
- selector-logik och measures for att losa vald portfoljs `CUR`- och `TGT`-serier
- measures for `CUR %`, `TGT %` och `Delta pp`
- huvudvisual per `Category`
- KPI-kort for enkel analyskontext
- innehavslista och interaktion mellan kategori och innehav

Sannolikt BI-spar om gap identifieras:

- komplettering av BI-artefakten sa att `Category` foljer med pa snapshotniva in i `Fact_Portfolio_Alloc_Snapshot`
- komplettering av BI-artefakten om `Instrument_Type` behovs for tydligare innehavslista

Viktig princip:

- BI-sparet ska bara andras for verkliga datakontraktsgap, inte for ren presentationslogik

## Upstream-komplettering for `Structure`

Nuvarande bedomning:

- gemensamt upstream-spor verkar redan ha tillgang till kategori per instrument
- det som idag inte kommer tillrackligt robust in i Power BI-kedjan ar framfor allt kategori pa snapshot-relevant niva

Det som tydligt behover kompletteras uppstroms sa att tillrackligt med data kommer med:

- `Category` bor finnas explicit pa struktur-snapshotraderna i upstream-utdata, inte bara implicit via andra tabeller
- `Instrument_Type` bor ocksa folja med om det ska kunna anvandas i innehavslistan eller framtida enkel segmentering
- instrumentnara metadata bor helst materialiseras pa snapshot-grain, sa att nedstroms steg inte behover skora sekundara lookup-steg

Minsta pragmatiska komplettering uppstroms:

- lagg till `Category` i `Portfolio_Series_Map`
- lagg garna till `Instrument_Type` i `Portfolio_Series_Map`

Motivering:

- `Structure` bygger pa snapshot-grain, inte pa tidsseriegrains eller kategori-serier
- kategori pa snapshotraden gor aggregation per `Category` enkel, tydlig och stabil
- detta minskar risken for att BI-sparet tappar metadata i onodiga mellanled
- `Category` i `Dim_Instrument` ska inte vara primar kalla for `Structure`
- om `Category` idag bara behover finnas i `Dim_Instrument` for `Structure` ar den kolumnen inte langre nodvandig i v2-losningen

Om upstream inte andras:

- da behover BI-sparet robust och explicit mappa in `Category` fran upstreams instrumentmetadata till `Dim_Instrument`
- det bor da ocksa overvagas att skriva `Category` vidare till `Fact_Portfolio_Alloc_Snapshot`
- detta ar mojligt, men mer skort an att lata kategorin komma med direkt i snapshot-kontraktet

Viktig princip:

- upstream ska bara kompletteras med liten, tydlig metadata som behovs for ett stabilt datakontrakt
- ingen stor omskrivning av upstream-sporet ska goras for `Structure`

## Antaganden och risker

Antaganden:

- en aktuell snapshot per korning ar tillracklig for v2
- portfoljval pa sidan kan hallas till exakt en portfolj at gangen
- `CUR` och `TGT` ska fortsatt vara de enda relevanta varianterna for `Structure`

Risker:

- om kategori fortsatt bara ar indirekt tillganglig blir rapportlagret onodigt skort
- om `Weight_Source` anvands som styrlogik i stallet for `Variant` blir sidan mindre robust
- om innehav bara visas nar de finns i bada varianterna tappas viktig avvikelseinformation

## Oppna fragor for fortsatt v2-arbete

- om `Instrument_Type` ska inga redan i v2-ytan eller bara folja med som framtidssaker metadata

## Rekommenderad prioritering

1. `Structure`
2. `Overview`
3. `Performance`

Motivering:

- `Structure` ar den tydligaste nya nyttan i v2 och den storsta sannolika datakontraktsfragan
- `Overview` ar en liten och tydlig forbattring ovanpa fungerande v1-logik
- `Performance` ar mest isolerad rapportlagerutbyggnad ovanpa fungerande v1-logik

## Foreslagna arbetstradar

- `Structure` datakontrakt: komplettera upstream och BI-sparet sa att `Category` foljer snapshot-grain stabilt till `Fact_Portfolio_Alloc_Snapshot`
- `Structure` PBIX: implementera selector-logik, kategorivisual, KPI-kort och innehavslista ovanpa last datakontrakt
- `Overview`: implementera last rollmarkering, tabellsortering och eventuell diskret tabellpolish
- `Performance`: implementera last datum-snabbval och lokal samexistens med fri datumslicer

---

Senast uppdaterad: 2026-04-19
