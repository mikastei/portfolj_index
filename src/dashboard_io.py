"""I/O and validation helpers for dashboard preparation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ANALYSIS_PREFIXES = ("PORT_", "BM_")

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
        "NO_REBALANCING",
    ],
}


@dataclass(frozen=True)
class DashboardSource:
    """Validated source tables from the Portfolio_index output workbook."""

    source_path: Path
    master_long: pd.DataFrame
    series_definition: pd.DataFrame
    portfolio_series_map: pd.DataFrame
    run_config: pd.DataFrame


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


def load_dashboard_source(path: str | Path) -> DashboardSource:
    """Load and validate the Portfolio_index output workbook."""
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

    return DashboardSource(
        source_path=source_path,
        master_long=master_long,
        series_definition=series_definition,
        portfolio_series_map=portfolio_series_map,
        run_config=run_config,
    )


def _display_name(row: pd.Series) -> str:
    series_type = str(row.get("Series_Type") or "").strip().upper()
    if series_type == "PORT":
        portfolio_name = str(row.get("Portfolio_Name") or "").strip()
        variant = str(row.get("Variant") or "").strip().upper()
        category = "" if pd.isna(row.get("Category")) else str(row.get("Category") or "").strip()
        variant_display = {"REAL": "Real", "CUR": "Current", "TGT": "Target"}.get(variant, variant.title())
        display_name = f"{portfolio_name} {variant_display}".strip()
        if category:
            display_name = f"{display_name} {category}".strip()
        return display_name or str(row.get("Series_ID") or "").strip()
    if series_type == "BM":
        benchmark_id = str(row.get("Benchmark_ID") or "").strip()
        return benchmark_id or str(row.get("Series_ID") or "").strip()
    return str(row.get("Series_ID") or "").strip()


def build_analysis_metadata(source: DashboardSource) -> pd.DataFrame:
    """
    Build the dashboard analysis universe from series present in Master_TimeSeries_Long.

    AST_* rows are excluded explicitly even if they exist in Series_Definition.
    """
    master_series = source.master_long["Series_ID"].dropna().astype(str).str.strip()
    analysis_ids = sorted(
        {
            series_id
            for series_id in master_series.unique().tolist()
            if series_id.startswith(ANALYSIS_PREFIXES)
        }
    )
    if not analysis_ids:
        raise ValueError("No analysis series found in Master_TimeSeries_Long")

    metadata = source.series_definition.copy()
    metadata = metadata[metadata["Series_ID"].isin(analysis_ids)].copy()
    if metadata.empty:
        raise ValueError("Series_Definition does not contain metadata for analysis series")

    metadata["Display_Name"] = metadata.apply(_display_name, axis=1)
    metadata = metadata.drop_duplicates(subset=["Series_ID"]).reset_index(drop=True)
    return metadata.sort_values(["Series_Type", "Display_Name", "Series_ID"]).reset_index(drop=True)


def build_analysis_master_long(source: DashboardSource, analysis_metadata: pd.DataFrame) -> pd.DataFrame:
    """Filter Master_TimeSeries_Long to the dashboard analysis universe."""
    analysis_ids = set(analysis_metadata["Series_ID"].tolist())
    master_long = source.master_long[source.master_long["Series_ID"].isin(analysis_ids)].copy()
    if master_long.empty:
        raise ValueError("Master_TimeSeries_Long has no rows for the analysis universe")
    return master_long.sort_values(["Series_ID", "Date"]).reset_index(drop=True)


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
