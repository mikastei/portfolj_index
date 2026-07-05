"""Read-only inläsning av portfolio_bi_data.xlsx för fond-rapporten."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

SHEET_NAMES = [
    "Dim_Date",
    "Dim_Portfolio",
    "Dim_Series",
    "Dim_Instrument",
    "Fact_Series_Daily",
    "Fact_Series_KPI",
    "Fact_Portfolio_Alloc_Snapshot",
    "Fact_Portfolio_Alloc_Monthly",
    "Fact_Portfolio_Courtage",
]

WEIGHT_SUM_TOLERANCE = 1e-6


@dataclass(frozen=True)
class BIData:
    """Samtliga BI-tabeller som DataFrames, lästa utan att röra källfilen."""

    dim_date: pd.DataFrame
    dim_portfolio: pd.DataFrame
    dim_series: pd.DataFrame
    dim_instrument: pd.DataFrame
    fact_daily: pd.DataFrame
    fact_kpi: pd.DataFrame
    fact_alloc: pd.DataFrame
    fact_alloc_monthly: pd.DataFrame
    fact_courtage: pd.DataFrame = field(default_factory=pd.DataFrame)


def load_bi_data(path: Path) -> BIData:
    """Läs alla blad ur BI-arbetsboken. Filen öppnas enbart för läsning."""
    if not path.exists():
        raise FileNotFoundError(f"BI-filen saknas: {path}")
    workbook = pd.ExcelFile(path)
    missing = [sheet for sheet in SHEET_NAMES if sheet not in workbook.sheet_names]
    if missing:
        raise ValueError(f"BI-filen saknar förväntade blad: {missing}")

    frames = {sheet: workbook.parse(sheet) for sheet in SHEET_NAMES}
    workbook.close()

    fact_daily = frames["Fact_Series_Daily"].copy()
    fact_daily["Date"] = pd.to_datetime(fact_daily["Date"])
    fact_daily = fact_daily.sort_values(["Series_ID", "Date"]).reset_index(drop=True)

    alloc_monthly = frames["Fact_Portfolio_Alloc_Monthly"].copy()
    alloc_monthly["Period_End_Date"] = pd.to_datetime(alloc_monthly["Period_End_Date"])

    courtage = frames["Fact_Portfolio_Courtage"].copy()
    courtage["Period_End_Date"] = pd.to_datetime(courtage["Period_End_Date"])

    return BIData(
        dim_date=frames["Dim_Date"],
        dim_portfolio=frames["Dim_Portfolio"],
        dim_series=frames["Dim_Series"],
        dim_instrument=frames["Dim_Instrument"],
        fact_daily=fact_daily,
        fact_kpi=frames["Fact_Series_KPI"],
        fact_alloc=frames["Fact_Portfolio_Alloc_Snapshot"],
        fact_alloc_monthly=alloc_monthly,
        fact_courtage=courtage,
    )


def check_contract(data: BIData) -> list[str]:
    """Grundläggande datakontrakt: inga NaN i faktatabeller, vikter summerar till 1."""
    failures: list[str] = []

    for name, frame in (
        ("Fact_Series_Daily", data.fact_daily),
        ("Fact_Series_KPI", data.fact_kpi),
        ("Fact_Portfolio_Alloc_Snapshot", data.fact_alloc),
        ("Fact_Portfolio_Alloc_Monthly", data.fact_alloc_monthly),
        ("Fact_Portfolio_Courtage", data.fact_courtage),
    ):
        nan_counts = frame.isna().sum()
        nan_columns = nan_counts[nan_counts > 0]
        if not nan_columns.empty:
            failures.append(f"{name} innehåller NaN: {nan_columns.to_dict()}")

    weight_sums = data.fact_alloc.groupby(["Portfolio_Key", "Series_ID"])["Weight"].sum()
    for (portfolio, series_id), total in weight_sums.items():
        if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
            failures.append(
                f"Viktsumma avviker från 1.0 för {portfolio}/{series_id}: {total:.8f}"
            )

    monthly_sums = data.fact_alloc_monthly.groupby(["Portfolio_Key", "Period_End_Date"])[
        "Weight"
    ].sum()
    off = monthly_sums[(monthly_sums - 1.0).abs() > WEIGHT_SUM_TOLERANCE]
    for (portfolio, period_end), total in off.items():
        failures.append(
            f"Månadsviktsumma avviker från 1.0 för {portfolio} per "
            f"{pd.Timestamp(period_end).date()}: {total:.8f}"
        )

    return failures


def series_index(data: BIData, series_id: str) -> pd.Series:
    """IDX-kurvan för en serie, indexerad på datum."""
    sub = data.fact_daily[data.fact_daily["Series_ID"] == series_id]
    if sub.empty:
        raise KeyError(f"Serien saknas i Fact_Series_Daily: {series_id}")
    return sub.set_index("Date")["IDX"]


def series_drawdown(data: BIData, series_id: str) -> pd.Series:
    """DD-kurvan för en serie, indexerad på datum."""
    sub = data.fact_daily[data.fact_daily["Series_ID"] == series_id]
    if sub.empty:
        raise KeyError(f"Serien saknas i Fact_Series_Daily: {series_id}")
    return sub.set_index("Date")["DD"]
