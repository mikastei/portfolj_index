
# Portföljindex

Det här projektet bygger ett portföljindex (bas 100) för en eller flera portföljer samt benchmarkserier, baserat på transaktioner och prisdata (Yahoo Finance).
Outputen (`portfolio_output_timeseries.xlsx`) används som underlag för vidare analys, jämförelser och dashboards.

---

# Översikt – dataflöde

Projektet kopplar ihop tre typer av data:

1. Transaktioner från Nordnet
2. Prisdata från Yahoo Finance
3. Portföljmetadata och benchmarkdefinitioner

Förenklat dataflöde:

```
transaktioner.xlsx
    │
    ├── Transactions (Nordnet historik)
    ├── Mapping (ISIN → Yahoo ticker)
    ├── Portfolio_Metadata
    └── Benchmarks
            │
            ▼
       Yahoo Finance
       (prisdata)
            │
            ▼
      Portföljindex‑motor
      (TWR-beräkning)
            │
            ▼
portfolio_output_timeseries.xlsx
```

---

# Indata

## 1. `transaktioner.xlsx`

Excelarbetsbok som innehåller både transaktionshistorik och de tabeller som används för att koppla instrument till prisdata, portföljer och benchmark.

Filen innehåller fyra flikar.

---

## Transactions (Nordnet-export)

Rå transaktionslogg från Nordnet. Den används för att beräkna **REAL-serierna**, dvs portföljens faktiska historiska utveckling.

### Viktiga kolumner

| Kolumn | Beskrivning |
|------|------|
| Affärsdag | Datum då transaktionen påverkar portföljen |
| Depå | Portföljens ID |
| Transaktionstyp | t.ex. KÖP eller SÄLJ |
| ISIN | Instrumentets ISIN |
| Antal | Antal andelar |
| Belopp | Transaktionsbelopp |
| Valuta | Transaktionens valuta |
| Referensvalutakurs | Valutakurs mot basvaluta |
| Växlingskurs | Alternativ valutakurs från Nordnet |

### Viktig konvention

I projektet används följande teckenregler:

```
KÖP  = negativt belopp
SÄLJ = positivt belopp
```

Detta gör att portföljens kassaflöden kan beräknas korrekt.

---

## Mapping

Tabellen som kopplar varje ISIN till en prisserie.

| Kolumn | Beskrivning |
|------|------|
| ISIN | Nyckel som kopplar till Transactions |
| Name | Instrumentnamn |
| Yahoo_Ticker | Ticker på Yahoo Finance |
| Price_Source | Normalt YAHOO |
| Instrument_Type | FUND / ETF / STOCK |
| Price_Currency | Valutan som priset är noterat i |
| Category | Fondens kategori i portföljanalysen |

### Viktig regel

Varje ISIN som förekommer i **Transactions** måste finnas i **Mapping**.

---

## Portfolio_Metadata

Definierar vilka portföljer som ska byggas.

| Kolumn | Beskrivning |
|------|------|
| Portfolio_ID | Matchar Depå i Transactions |
| Portfolio_Name | Kort namn (ex PA eller EGEN) |
| Index_Start_Date | Datum då indexserien startar |
| Initial_Index_Value | Normalt 100 |

---

## Benchmarks

Definierar benchmarkserier.

| Kolumn | Beskrivning |
|------|------|
| Benchmark_ID | Namn på benchmark |
| ISIN | Metadata |
| Yahoo_Ticker | Ticker för benchmark |
| Price_Currency | Valuta |
| Category | Klassificering |
| Include_From_Date | Startdatum för benchmark |

---

## 2. `fonder.xlsx`

Denna fil genereras i projektet **Fondanalys** och innehåller modellportföljernas vikter.

I detta projekt används filen endast som input för:

- **CUR-serier**
- **TGT-serier**

Den behöver därför **inte uppdateras manuellt här**.

---

# Utdata

## `portfolio_output_timeseries.xlsx`

Outputfilen innehåller alla beräknade tidsserier och metadata.

Den innehåller fyra flikar.

---

## Master_TimeSeries_Long

Huvudtabellen med alla tidsserier.

| Kolumn | Beskrivning |
|------|------|
| Date | Handelsdatum |
| Series_ID | Serieidentifierare |
| RET | Daglig avkastning |
| IDX | Indexnivå |
| DD | Drawdown |

### Exempel på Series_ID

```
PORT_PA_REAL
PORT_PA_CUR
PORT_PA_TGT

PORT_EGEN_REAL
PORT_EGEN_CUR
PORT_EGEN_TGT

BM_NORDNET_BALANSERAD_SEK
BM_NORDNET_OFFENSIV_SEK
```

---

## Series_Definition

Metadata per serie.

| Kolumn | Beskrivning |
|------|------|
| Series_ID | Serieidentifierare |
| Series_Type | PORT eller BM |
| Portfolio_Name | Portföljnamn |
| Variant | REAL / CUR / TGT |
| Benchmark_ID | Benchmarknamn |
| Yahoo_Ticker | Underliggande ticker |
| Instrument_Type | Typ av instrument |
| Category | Fondkategori |
| Include_From_Date | Startdatum |
| Index_Start_Date | Indexstart |
| Initial_Index_Value | Startvärde |

---

## Portfolio_Series_Map

Visar vilka instrument och vikter som används i modellportföljer.

| Kolumn | Beskrivning |
|------|------|
| Portfolio_Name | Portfölj |
| Series_ID | Serie |
| Yahoo_Ticker | Instrument |
| Weight | Vikt |
| Weight_Source | Källa till vikten |

---

## Run_Config

Loggar körningen så att resultatet går att reproducera.

| Kolumn | Beskrivning |
|------|------|
| Timestamp | När körningen gjordes |
| PATH_TRANSAKTIONER | Källfil |
| PATH_FONDER | Källfil |
| OUTPUT_PATH | Outputfil |
| RF_RATE_ANNUAL | Riskfri ränta |
| BASE_CURRENCY | Basvaluta |
| TRADING_DAYS_PER_YEAR | Antal handelsdagar |
| FORWARD_FILL | Om priser forward-fillas |
| NO_REBALANCING | Modellportfölj utan rebalansering |

---

# Serietyper

| Typ | Beskrivning |
|------|------|
| REAL | Faktiska portföljvikter från transaktioner |
| CUR | Modellportfölj baserad på aktuella vikter |
| TGT | Modellportfölj baserad på målvikter |
| BM | Benchmarkserie |

---

# Lägga till en ny fond i en portfölj

När en ny fond köps behöver endast **transaktioner.xlsx** uppdateras.

`fonder.xlsx` uppdateras automatiskt i projektet **Fondanalys**.

## Steg 1 – lägg till fond i Mapping

Om fondens ISIN inte finns i Mapping lägger man till en ny rad.

Exempel:

| ISIN | Name | Yahoo_Ticker | Price_Source | Instrument_Type | Price_Currency | Category |
|-----|-----|-----|-----|-----|-----|-----|
| IE00B4L5Y983 | iShares Core MSCI World ETF | IWDA.AS | YAHOO | ETF | USD | Global – Breda fonder |

## Steg 2 – säkerställ att transaktionen finns i Transactions

| Affärsdag | Depå | Transaktionstyp | ISIN | Antal | Belopp | Valuta |
|---|---|---|---|---|---|---|
| 2025-04-15 | PA | KÖP | IE00B4L5Y983 | 150 | -15000 | SEK |

## Steg 3 – kör skriptet

```
py -m src.main
```

Skriptet kommer då att:

1. hitta fonden via Mapping
2. hämta prisdata från Yahoo Finance
3. inkludera fonden i portföljens REAL-serie
4. uppdatera `portfolio_output_timeseries.xlsx`

---

# Vanliga fel

### Saknad Mapping

```
Missing Mapping for ISIN
```

### Fel Yahoo ticker

Ger saknade prisserier.

### Fel tecken på Belopp

```
KÖP = negativt
SÄLJ = positivt
```

Fel tecken kan skapa stora hopp i index.

---

Senast uppdaterad: 2026-03-05
