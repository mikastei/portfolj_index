# Power BI DAX v1

## Syfte

Detta dokument samlar de DAX-definitioner som utgor rapportlagret for Power BI v1.

Det omfattar:

- beraknad kolumn
- calculated tables for slicers och measure-hub
- selector-measures
- generiska KPI-measures
- `Primary KPI`-measures for kort

Dokumentet ar avsett som referens for fortsatt PBIX-arbete och for framtida Codex-tradar som behover veta vilka DAX-uttryck som ligger bakom v1-logiken.

Notering:

- nedan visas DAX med komma som avgransare
- om Power BI-miljon kraver semikolon ska uttrycken anpassas lokalt

## Beraknad kolumn

### `Dim_Series[Series_Label]`

Syfte:

- anvandarvanlig serieetikett i slicers, tabeller och framtida visuals

```DAX
Series_Label =
VAR BenchmarkLabel =
    IF (
        NOT ISBLANK ( Dim_Series[Benchmark_ID] ),
        SUBSTITUTE ( SUBSTITUTE ( Dim_Series[Benchmark_ID], "BM_", "" ), "_", " " )
    )
VAR MainLabel =
    TRIM ( Dim_Series[Portfolio_Name] & " " & Dim_Series[Variant] )
VAR CategoryLabel =
    TRIM ( Dim_Series[Portfolio_Name] & " " & Dim_Series[Variant] & " | " & Dim_Series[Category] )
RETURN
    SWITCH (
        TRUE (),
        NOT ISBLANK ( Dim_Series[Benchmark_ID] ), BenchmarkLabel,
        NOT ISBLANK ( Dim_Series[Category] ), CategoryLabel,
        MainLabel
    )
```

## Calculated tables

### `Measure_Hub`

Syfte:

- separat tabell for rapportens measures

```DAX
Measure_Hub =
DATATABLE (
    "Dummy", INTEGER,
    {
        { 1 }
    }
)
```

### `Sel_Primary_Portfolio`

Syfte:

- frikopplad slicertabell for val av primar portfolj

```DAX
Sel_Primary_Portfolio =
DISTINCT (
    SELECTCOLUMNS (
        FILTER ( Dim_Series, Dim_Series[Is_Main_Portfolio_Series] = TRUE () ),
        "Portfolio_Name", Dim_Series[Portfolio_Name]
    )
)
```

### `Sel_Primary_Variant`

Syfte:

- frikopplad slicertabell for val av primar variant

```DAX
Sel_Primary_Variant =
DATATABLE (
    "Variant", STRING,
    "SortOrder", INTEGER,
    {
        { "REAL", 1 },
        { "CUR", 2 },
        { "TGT", 3 }
    }
)
```

### `Sel_KPI_Period`

Syfte:

- frikopplad slicertabell for val av KPI-period

```DAX
Sel_KPI_Period =
DATATABLE (
    "Period", STRING,
    "SortOrder", INTEGER,
    {
        { "30D", 1 },
        { "YTD", 2 },
        { "1Y", 3 },
        { "Since_Start", 4 }
    }
)
```

### `Sel_Benchmark`

Syfte:

- frikopplad slicertabell for val av benchmark

```DAX
Sel_Benchmark =
SELECTCOLUMNS (
    FILTER ( Dim_Series, Dim_Series[Is_Benchmark] = TRUE () ),
    "Series_ID", Dim_Series[Series_ID],
    "Series_Label", Dim_Series[Series_Label],
    "SortOrder", 1
)
```

### `Sel_Compare_Extra`

Syfte:

- frikopplad slicertabell for val av extra jamforelse inom huvuduniversumet

```DAX
Sel_Compare_Extra =
SELECTCOLUMNS (
    FILTER ( Dim_Series, Dim_Series[Is_Main_Portfolio_Series] = TRUE () ),
    "Series_ID", Dim_Series[Series_ID],
    "Series_Label", Dim_Series[Series_Label],
    "SortOrder", 1
)
```

## Selector-measures

### `Selected Primary Portfolio`

```DAX
Selected Primary Portfolio =
SELECTEDVALUE ( Sel_Primary_Portfolio[Portfolio_Name] )
```

### `Selected Primary Variant`

```DAX
Selected Primary Variant =
SELECTEDVALUE ( Sel_Primary_Variant[Variant], "REAL" )
```

### `Selected KPI Period`

```DAX
Selected KPI Period =
SELECTEDVALUE ( Sel_KPI_Period[Period], "1Y" )
```

### `Selected Benchmark Series ID`

Notering:

- denna measure ar nu endast entydig nar exakt ett benchmark ar valt

```DAX
Selected Benchmark Series ID =
SELECTEDVALUE ( Sel_Benchmark[Series_ID] )
```

### `Selected Extra Series ID`

Notering:

- denna measure ar nu endast entydig nar exakt en extra jamforelse ar vald

```DAX
Selected Extra Series ID =
SELECTEDVALUE ( Sel_Compare_Extra[Series_ID] )
```

### `Selected Primary Series ID`

```DAX
Selected Primary Series ID =
VAR _portfolio = [Selected Primary Portfolio]
VAR _variant = [Selected Primary Variant]
RETURN
    CALCULATE (
        SELECTEDVALUE ( Dim_Series[Series_ID] ),
        FILTER (
            ALL ( Dim_Series ),
            Dim_Series[Is_Main_Portfolio_Series] = TRUE ()
                && Dim_Series[Portfolio_Name] = _portfolio
                && Dim_Series[Variant] = _variant
        )
    )
```

### `Is Selected Overview Series`

```DAX
Is Selected Overview Series =
VAR _current = SELECTEDVALUE ( Dim_Series[Series_ID] )
VAR _primary = [Selected Primary Series ID]
VAR _hasBenchmarkSelection = ISFILTERED ( Sel_Benchmark[Series_Label] )
VAR _hasExtraSelection = ISFILTERED ( Sel_Compare_Extra[Series_Label] )
VAR _isBenchmarkSelected =
    _hasBenchmarkSelection
        && CONTAINS (
            VALUES ( Sel_Benchmark[Series_ID] ),
            Sel_Benchmark[Series_ID], _current
        )
VAR _isExtraSelected =
    _hasExtraSelection
        && CONTAINS (
            VALUES ( Sel_Compare_Extra[Series_ID] ),
            Sel_Compare_Extra[Series_ID], _current
        )
RETURN
    IF (
        _current = _primary
            || _isBenchmarkSelected
            || _isExtraSelected,
        1,
        0
    )
```

### `Overview Series Sort Rank`

Notering:

- anvands som tekniskt hjalpmeasure for att sortera jamforelsetabellen pa `Overview`
- ordningen ar primarserie, sedan extra jamforelse, sedan benchmark

```DAX
Overview Series Sort Rank =
VAR _current = SELECTEDVALUE ( Dim_Series[Series_ID] )
VAR _primary = [Selected Primary Series ID]
VAR _hasBenchmarkSelection = ISFILTERED ( Sel_Benchmark[Series_Label] )
VAR _hasExtraSelection = ISFILTERED ( Sel_Compare_Extra[Series_Label] )
VAR _isBenchmarkSelected =
    _hasBenchmarkSelection
        && CONTAINS (
            VALUES ( Sel_Benchmark[Series_ID] ),
            Sel_Benchmark[Series_ID], _current
        )
VAR _isExtraSelected =
    _hasExtraSelection
        && CONTAINS (
            VALUES ( Sel_Compare_Extra[Series_ID] ),
            Sel_Compare_Extra[Series_ID], _current
        )
RETURN
    SWITCH (
        TRUE (),
        _current = _primary, 1,
        _isExtraSelected, 2,
        _isBenchmarkSelected, 3,
        9
    )
```

### `Selected Primary Label`

```DAX
Selected Primary Label =
VAR _id = [Selected Primary Series ID]
RETURN
    CALCULATE (
        SELECTEDVALUE ( Dim_Series[Series_Label] ),
        FILTER ( ALL ( Dim_Series ), Dim_Series[Series_ID] = _id )
    )
```

### `Selected Benchmark Label`

```DAX
Selected Benchmark Label =
VAR _hasSelection = ISFILTERED ( Sel_Benchmark[Series_Label] )
RETURN
    IF (
        NOT _hasSelection,
        "(Ingen benchmark)",
        CONCATENATEX (
            VALUES ( Sel_Benchmark[Series_Label] ),
            Sel_Benchmark[Series_Label],
            ", ",
            Sel_Benchmark[Series_Label],
            ASC
        )
    )
```

### `Selected Extra Label`

```DAX
Selected Extra Label =
VAR _hasSelection = ISFILTERED ( Sel_Compare_Extra[Series_Label] )
RETURN
    IF (
        NOT _hasSelection,
        "(Ingen jämförelse)",
        CONCATENATEX (
            VALUES ( Sel_Compare_Extra[Series_Label] ),
            Sel_Compare_Extra[Series_Label],
            ", ",
            Sel_Compare_Extra[Series_Label],
            ASC
        )
    )
```

## Generiska KPI-measures

Dessa measures ar avsedda for tabeller och annan radkontext dar vald serie kan komma antingen fran radens `Dim_Series` eller falla tillbaka till primarserien.

### `KPI Context Series ID`

```DAX
KPI Context Series ID =
COALESCE (
    SELECTEDVALUE ( Dim_Series[Series_ID] ),
    [Selected Primary Series ID]
)
```

### `KPI Context Label`

```DAX
KPI Context Label =
VAR _series = [KPI Context Series ID]
RETURN
    CALCULATE (
        SELECTEDVALUE ( Dim_Series[Series_Label] ),
        FILTER ( ALL ( Dim_Series ), Dim_Series[Series_ID] = _series )
    )
```

### `KPI Return Total`

```DAX
KPI Return Total =
VAR _series = [KPI Context Series ID]
VAR _period = [Selected KPI Period]
RETURN
    IF (
        NOT ISBLANK ( _series ),
        CALCULATE (
            MAX ( Fact_Series_KPI[Return_Total] ),
            FILTER (
                ALL ( Fact_Series_KPI ),
                Fact_Series_KPI[Series_ID] = _series
                    && Fact_Series_KPI[Period] = _period
            )
        )
    )
```

### `KPI CAGR`

```DAX
KPI CAGR =
VAR _series = [KPI Context Series ID]
VAR _period = [Selected KPI Period]
RETURN
    IF (
        NOT ISBLANK ( _series ),
        CALCULATE (
            MAX ( Fact_Series_KPI[CAGR] ),
            FILTER (
                ALL ( Fact_Series_KPI ),
                Fact_Series_KPI[Series_ID] = _series
                    && Fact_Series_KPI[Period] = _period
            )
        )
    )
```

### `KPI Vol`

```DAX
KPI Vol =
VAR _series = [KPI Context Series ID]
VAR _period = [Selected KPI Period]
RETURN
    IF (
        NOT ISBLANK ( _series ),
        CALCULATE (
            MAX ( Fact_Series_KPI[Vol] ),
            FILTER (
                ALL ( Fact_Series_KPI ),
                Fact_Series_KPI[Series_ID] = _series
                    && Fact_Series_KPI[Period] = _period
            )
        )
    )
```

### `KPI Sharpe`

```DAX
KPI Sharpe =
VAR _series = [KPI Context Series ID]
VAR _period = [Selected KPI Period]
RETURN
    IF (
        NOT ISBLANK ( _series ),
        CALCULATE (
            MAX ( Fact_Series_KPI[Sharpe] ),
            FILTER (
                ALL ( Fact_Series_KPI ),
                Fact_Series_KPI[Series_ID] = _series
                    && Fact_Series_KPI[Period] = _period
            )
        )
    )
```

### `KPI Sortino`

```DAX
KPI Sortino =
VAR _series = [KPI Context Series ID]
VAR _period = [Selected KPI Period]
RETURN
    IF (
        NOT ISBLANK ( _series ),
        CALCULATE (
            MAX ( Fact_Series_KPI[Sortino] ),
            FILTER (
                ALL ( Fact_Series_KPI ),
                Fact_Series_KPI[Series_ID] = _series
                    && Fact_Series_KPI[Period] = _period
            )
        )
    )
```

### `KPI Max DD`

```DAX
KPI Max DD =
VAR _series = [KPI Context Series ID]
VAR _period = [Selected KPI Period]
RETURN
    IF (
        NOT ISBLANK ( _series ),
        CALCULATE (
            MAX ( Fact_Series_KPI[Max_DD] ),
            FILTER (
                ALL ( Fact_Series_KPI ),
                Fact_Series_KPI[Series_ID] = _series
                    && Fact_Series_KPI[Period] = _period
            )
        )
    )
```

### `KPI Calmar`

```DAX
KPI Calmar =
VAR _series = [KPI Context Series ID]
VAR _period = [Selected KPI Period]
RETURN
    IF (
        NOT ISBLANK ( _series ),
        CALCULATE (
            MAX ( Fact_Series_KPI[Calmar] ),
            FILTER (
                ALL ( Fact_Series_KPI ),
                Fact_Series_KPI[Series_ID] = _series
                    && Fact_Series_KPI[Period] = _period
            )
        )
    )
```

## Primary KPI-measures

Dessa measures ar avsedda for KPI-korten pa `Overview` och ska alltid folja primarserien, oavsett klick i tabeller eller andra visuals.

### `Primary KPI Return Total`

```DAX
Primary KPI Return Total =
VAR _series = [Selected Primary Series ID]
VAR _period = [Selected KPI Period]
RETURN
    IF (
        NOT ISBLANK ( _series ),
        CALCULATE (
            MAX ( Fact_Series_KPI[Return_Total] ),
            FILTER (
                ALL ( Fact_Series_KPI ),
                Fact_Series_KPI[Series_ID] = _series
                    && Fact_Series_KPI[Period] = _period
            )
        )
    )
```

### `Primary KPI CAGR`

```DAX
Primary KPI CAGR =
VAR _series = [Selected Primary Series ID]
VAR _period = [Selected KPI Period]
RETURN
    IF (
        NOT ISBLANK ( _series ),
        CALCULATE (
            MAX ( Fact_Series_KPI[CAGR] ),
            FILTER (
                ALL ( Fact_Series_KPI ),
                Fact_Series_KPI[Series_ID] = _series
                    && Fact_Series_KPI[Period] = _period
            )
        )
    )
```

### `Primary KPI Vol`

```DAX
Primary KPI Vol =
VAR _series = [Selected Primary Series ID]
VAR _period = [Selected KPI Period]
RETURN
    IF (
        NOT ISBLANK ( _series ),
        CALCULATE (
            MAX ( Fact_Series_KPI[Vol] ),
            FILTER (
                ALL ( Fact_Series_KPI ),
                Fact_Series_KPI[Series_ID] = _series
                    && Fact_Series_KPI[Period] = _period
            )
        )
    )
```

### `Primary KPI Sharpe`

```DAX
Primary KPI Sharpe =
VAR _series = [Selected Primary Series ID]
VAR _period = [Selected KPI Period]
RETURN
    IF (
        NOT ISBLANK ( _series ),
        CALCULATE (
            MAX ( Fact_Series_KPI[Sharpe] ),
            FILTER (
                ALL ( Fact_Series_KPI ),
                Fact_Series_KPI[Series_ID] = _series
                    && Fact_Series_KPI[Period] = _period
            )
        )
    )
```

### `Primary KPI Max DD`

```DAX
Primary KPI Max DD =
VAR _series = [Selected Primary Series ID]
VAR _period = [Selected KPI Period]
RETURN
    IF (
        NOT ISBLANK ( _series ),
        CALCULATE (
            MAX ( Fact_Series_KPI[Max_DD] ),
            FILTER (
                ALL ( Fact_Series_KPI ),
                Fact_Series_KPI[Series_ID] = _series
                    && Fact_Series_KPI[Period] = _period
            )
        )
    )
```

### `Primary KPI Calmar`

```DAX
Primary KPI Calmar =
VAR _series = [Selected Primary Series ID]
VAR _period = [Selected KPI Period]
RETURN
    IF (
        NOT ISBLANK ( _series ),
        CALCULATE (
            MAX ( Fact_Series_KPI[Calmar] ),
            FILTER (
                ALL ( Fact_Series_KPI ),
                Fact_Series_KPI[Series_ID] = _series
                    && Fact_Series_KPI[Period] = _period
            )
        )
    )
```
