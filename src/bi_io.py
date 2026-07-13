"""I/O and validation helpers for BI preparation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REQUIRED_SHEETS: dict[str, list[str]] = {
    "Master_TimeSeries_Long": ["Date", "Series_ID", "RET", "IDX", "DD"],
    "Series_Definition": [
        "Series_ID",
        "Series_Type",
        "Portfolio_Name",
        "Variant",
        "Benchmark_ID",
        "Yahoo_Ticker",
        "Instrument_Type",
        "Category",
        "Include_From_Date",
        "Index_Start_Date",
        "Initial_Index_Value",
    ],
    "Portfolio_Series_Map": [
        "Portfolio_Name",
        "Series_ID",
        "Yahoo_Ticker",
        "Weight",
        "Weight_Source",
    ],
    "Run_Config": [
        "Timestamp",
        "PATH_TRANSAKTIONER",
        "PATH_FONDER",
        "OUTPUT_PATH",
        "RF_RATE_ANNUAL",
        "BASE_CURRENCY",
        "TRADING_DAYS_PER_YEAR",
        "FORWARD_FILL",
        "DAILY_REBALANCING",
    ],
}

# Optional sheet: historical month-end REAL allocation weights. Older upstream
# workbooks predate it, so BI degrades gracefully to an empty series when absent.
ALLOC_MONTHLY_SHEET = "Portfolio_Alloc_Monthly"
ALLOC_MONTHLY_COLUMNS = [
    "Portfolio_Name",
    "Series_ID",
    "Period_End_Date",
    "Yahoo_Ticker",
    "ISIN",
    "Display_Name",
    "Price_Currency",
    "Category",
    "Market_Value_SEK",
    "Portfolio_MV_SEK",
    "Weight",
    "Weight_Source",
]

# Optional cost sheets (Steg 2b). Older upstream workbooks predate them, so BI
# degrades gracefully to empty frames when absent.
INSTRUMENT_COST_SHEET = "Instrument_Cost"
INSTRUMENT_COST_COLUMNS = ["ISIN", "Instrument_Type", "TER", "TER_Status", "TER_Source"]
COURTAGE_SHEET = "Portfolio_Courtage"
COURTAGE_COLUMNS = [
    "Portfolio_Name",
    "Portfolio_ID",
    "Series_ID",
    "Period_End_Date",
    "ISIN",
    "Yahoo_Ticker",
    "Display_Name",
    "Category",
    "Currency",
    "Courtage_Native",
    "Courtage_SEK",
    "Txn_Count",
]


@dataclass(frozen=True)
class PortfolioOutputSource:
    """Validated source tables from the shared portfolio output workbook."""

    source_path: Path
    master_long: pd.DataFrame
    series_definition: pd.DataFrame
    portfolio_series_map: pd.DataFrame
    run_config: pd.DataFrame
    portfolio_alloc_monthly: pd.DataFrame
    instrument_cost: pd.DataFrame
    portfolio_courtage: pd.DataFrame


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(col).strip() for col in out.columns]
    return out


def _validate_columns(df: pd.DataFrame, required: list[str], sheet_name: str) -> None:
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Sheet '{sheet_name}' is missing required columns: {missing}")


def _read_workbook(path: Path) -> dict[str, pd.DataFrame]:
    if not path.exists():
        raise FileNotFoundError(f"Source workbook does not exist: {path}")
    sheets = pd.read_excel(path, sheet_name=None)
    missing_sheets = [sheet for sheet in REQUIRED_SHEETS if sheet not in sheets]
    if missing_sheets:
        raise ValueError(f"Source workbook is missing required sheets: {missing_sheets}")
    return {name: _normalize_columns(df) for name, df in sheets.items()}


def load_portfolio_output(path: str | Path) -> PortfolioOutputSource:
    """Load and validate the shared portfolio output workbook."""
    source_path = Path(path)
    sheets = _read_workbook(source_path)

    master_long = sheets["Master_TimeSeries_Long"].copy()
    series_definition = sheets["Series_Definition"].copy()
    portfolio_series_map = sheets["Portfolio_Series_Map"].copy()
    run_config = sheets["Run_Config"].copy()

    _validate_columns(master_long, REQUIRED_SHEETS["Master_TimeSeries_Long"], "Master_TimeSeries_Long")
    _validate_columns(series_definition, REQUIRED_SHEETS["Series_Definition"], "Series_Definition")
    _validate_columns(portfolio_series_map, REQUIRED_SHEETS["Portfolio_Series_Map"], "Portfolio_Series_Map")
    _validate_columns(run_config, REQUIRED_SHEETS["Run_Config"], "Run_Config")

    master_long["Date"] = pd.to_datetime(master_long["Date"], errors="coerce")
    if master_long["Date"].isna().any():
        raise ValueError("Sheet 'Master_TimeSeries_Long' contains invalid values in column 'Date'")
    master_long["Series_ID"] = master_long["Series_ID"].astype(str).str.strip()
    for column in ("RET", "IDX", "DD"):
        master_long[column] = pd.to_numeric(master_long[column], errors="coerce")
    master_long = master_long.sort_values(["Series_ID", "Date"]).reset_index(drop=True)

    for column in ("Include_From_Date", "Index_Start_Date"):
        series_definition[column] = pd.to_datetime(series_definition[column], errors="coerce")
    series_definition["Series_ID"] = series_definition["Series_ID"].astype(str).str.strip()
    series_definition["Series_Type"] = series_definition["Series_Type"].astype(str).str.strip()

    portfolio_series_map["Series_ID"] = portfolio_series_map["Series_ID"].astype(str).str.strip()
    portfolio_series_map["Portfolio_Name"] = portfolio_series_map["Portfolio_Name"].astype(str).str.strip()
    portfolio_series_map["Yahoo_Ticker"] = portfolio_series_map["Yahoo_Ticker"].astype(str).str.strip()
    portfolio_series_map["Weight"] = pd.to_numeric(portfolio_series_map["Weight"], errors="coerce")

    run_config["Timestamp"] = pd.to_datetime(run_config["Timestamp"], errors="coerce")
    run_config["RF_RATE_ANNUAL"] = pd.to_numeric(run_config["RF_RATE_ANNUAL"], errors="coerce")
    run_config["TRADING_DAYS_PER_YEAR"] = pd.to_numeric(run_config["TRADING_DAYS_PER_YEAR"], errors="coerce")

    portfolio_alloc_monthly = _load_alloc_monthly(sheets)
    instrument_cost = _load_instrument_cost(sheets)
    portfolio_courtage = _load_portfolio_courtage(sheets)

    return PortfolioOutputSource(
        source_path=source_path,
        master_long=master_long,
        series_definition=series_definition,
        portfolio_series_map=portfolio_series_map,
        run_config=run_config,
        portfolio_alloc_monthly=portfolio_alloc_monthly,
        instrument_cost=instrument_cost,
        portfolio_courtage=portfolio_courtage,
    )


def _load_alloc_monthly(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Read the optional monthly allocation sheet, empty frame when absent."""
    if ALLOC_MONTHLY_SHEET not in sheets:
        return pd.DataFrame(columns=ALLOC_MONTHLY_COLUMNS)
    alloc = sheets[ALLOC_MONTHLY_SHEET].copy()
    _validate_columns(
        alloc,
        ["Portfolio_Name", "Series_ID", "Period_End_Date", "Yahoo_Ticker", "Weight"],
        ALLOC_MONTHLY_SHEET,
    )
    alloc["Period_End_Date"] = pd.to_datetime(alloc["Period_End_Date"], errors="coerce")
    alloc["Series_ID"] = alloc["Series_ID"].astype(str).str.strip()
    alloc["Portfolio_Name"] = alloc["Portfolio_Name"].astype(str).str.strip()
    alloc["Yahoo_Ticker"] = alloc["Yahoo_Ticker"].astype(str).str.strip()
    for column in ("Market_Value_SEK", "Portfolio_MV_SEK", "Weight"):
        if column in alloc.columns:
            alloc[column] = pd.to_numeric(alloc[column], errors="coerce")
    return alloc


def _load_instrument_cost(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Read the optional per-instrument TER sheet, empty frame when absent."""
    if INSTRUMENT_COST_SHEET not in sheets:
        return pd.DataFrame(columns=INSTRUMENT_COST_COLUMNS)
    cost = sheets[INSTRUMENT_COST_SHEET].copy()
    _validate_columns(cost, ["ISIN", "TER", "TER_Status"], INSTRUMENT_COST_SHEET)
    cost["ISIN"] = cost["ISIN"].astype(str).str.strip()
    cost["TER"] = pd.to_numeric(cost["TER"], errors="coerce")
    cost["TER_Status"] = cost["TER_Status"].astype(str).str.strip()
    return cost


def _load_portfolio_courtage(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Read the optional realised-courtage sheet, empty frame when absent."""
    if COURTAGE_SHEET not in sheets:
        return pd.DataFrame(columns=COURTAGE_COLUMNS)
    courtage = sheets[COURTAGE_SHEET].copy()
    _validate_columns(
        courtage,
        ["Portfolio_Name", "Period_End_Date", "ISIN", "Courtage_Native", "Courtage_SEK"],
        COURTAGE_SHEET,
    )
    courtage["Period_End_Date"] = pd.to_datetime(courtage["Period_End_Date"], errors="coerce")
    courtage["Portfolio_Name"] = courtage["Portfolio_Name"].astype(str).str.strip()
    courtage["ISIN"] = courtage["ISIN"].astype(str).str.strip()
    for column in ("Courtage_Native", "Courtage_SEK", "Txn_Count"):
        if column in courtage.columns:
            courtage[column] = pd.to_numeric(courtage[column], errors="coerce")
    return courtage


def extract_run_parameters(run_config: pd.DataFrame) -> tuple[float, int]:
    """Read risk-free rate and trading days from the first Run_Config row."""
    if run_config.empty:
        raise ValueError("Run_Config is empty")
    row = run_config.iloc[0]
    rf_rate_annual = pd.to_numeric(row["RF_RATE_ANNUAL"], errors="coerce")
    trading_days_per_year = pd.to_numeric(row["TRADING_DAYS_PER_YEAR"], errors="coerce")
    if pd.isna(rf_rate_annual):
        raise ValueError("Run_Config column 'RF_RATE_ANNUAL' is missing or invalid")
    if pd.isna(trading_days_per_year):
        raise ValueError("Run_Config column 'TRADING_DAYS_PER_YEAR' is missing or invalid")
    return float(rf_rate_annual), int(trading_days_per_year)
