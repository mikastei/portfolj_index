"""Separate BI prep step that builds a first Power BI data contract from the shared output workbook."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from . import config
from .bi_io import extract_run_parameters, load_portfolio_output
from .bi_metrics import PERIOD_ORDER, compute_kpis, has_minimum_observations, slice_period

ANALYSIS_PREFIXES = ("PORT_", "BM_")
ALLOCATION_SNAPSHOT_SHEET_NAME = "Fact_Portfolio_Alloc_Snapshot"


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-path",
        default=None,
        help="Path to portfolio_output_timeseries.xlsx",
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Path to portfolio_bi_data.xlsx",
    )
    return parser.parse_args()


def _clean_text(series: pd.Series) -> pd.Series:
    cleaned = series.fillna("").astype(str).str.strip()
    return cleaned.replace({"nan": "", "None": "", "NaT": "", "<NA>": ""})


def _nullable_text(series: pd.Series) -> pd.Series:
    cleaned = _clean_text(series)
    return cleaned.mask(cleaned == "")


def _combine_optional_columns(df: pd.DataFrame, target: str) -> pd.Series:
    map_column = f"{target}_map"
    series_column = f"{target}_series"
    map_values = df[map_column] if map_column in df.columns else pd.Series(pd.NA, index=df.index, dtype="object")
    series_values = (
        df[series_column] if series_column in df.columns else pd.Series(pd.NA, index=df.index, dtype="object")
    )
    return map_values.combine_first(series_values)


def _build_analysis_metadata(
    series_definition: pd.DataFrame,
    master_long: pd.DataFrame,
) -> pd.DataFrame:
    analysis_ids = sorted(
        {
            series_id
            for series_id in _clean_text(master_long["Series_ID"]).tolist()
            if any(series_id.startswith(prefix) for prefix in ANALYSIS_PREFIXES)
        }
    )
    if not analysis_ids:
        raise ValueError("No BI analysis series found in Master_TimeSeries_Long")

    metadata = series_definition.copy()
    metadata["Series_ID"] = _clean_text(metadata["Series_ID"])
    metadata["Series_Type"] = _clean_text(metadata["Series_Type"]).str.upper()
    metadata["Portfolio_Name"] = _nullable_text(metadata["Portfolio_Name"])
    metadata["Variant"] = _nullable_text(metadata["Variant"])
    metadata["Benchmark_ID"] = _nullable_text(metadata["Benchmark_ID"])
    metadata["Yahoo_Ticker"] = _nullable_text(metadata["Yahoo_Ticker"])
    metadata["ISIN"] = _nullable_text(metadata["ISIN"])
    metadata["Display_Name"] = _nullable_text(metadata["Display_Name"])
    metadata["Price_Currency"] = _nullable_text(metadata["Price_Currency"])
    metadata["Instrument_Type"] = _nullable_text(metadata["Instrument_Type"])
    metadata["Category"] = _nullable_text(metadata["Category"])
    metadata = metadata[metadata["Series_ID"].isin(analysis_ids)].copy()
    if metadata.empty:
        raise ValueError("Series_Definition does not contain BI metadata for analysis series")

    missing_ids = sorted(set(analysis_ids) - set(metadata["Series_ID"].tolist()))
    if missing_ids:
        raise ValueError(f"Series_Definition is missing BI metadata for series: {missing_ids}")

    metadata["Is_Main_Portfolio_Series"] = (
        (metadata["Series_Type"] == "PORT") & metadata["Category"].isna()
    )
    metadata["Is_Category_Series"] = (
        (metadata["Series_Type"] == "PORT") & metadata["Category"].notna()
    )
    metadata["Is_Benchmark"] = metadata["Series_Type"] == "BM"
    metadata["Is_Overview_Eligible"] = (
        metadata["Is_Main_Portfolio_Series"] | metadata["Is_Benchmark"]
    )
    metadata["Is_Performance_Eligible"] = (
        metadata["Is_Overview_Eligible"] | metadata["Is_Category_Series"]
    )

    return metadata.sort_values(["Series_Type", "Portfolio_Name", "Variant", "Benchmark_ID", "Series_ID"]).reset_index(
        drop=True
    )


def _build_dim_portfolio(analysis_metadata: pd.DataFrame) -> pd.DataFrame:
    portfolios = analysis_metadata.loc[
        analysis_metadata["Portfolio_Name"].notna(),
        ["Portfolio_Name", "Index_Start_Date", "Initial_Index_Value"],
    ].copy()
    if portfolios.empty:
        return pd.DataFrame(
            columns=["Portfolio_Key", "Portfolio_Name", "Index_Start_Date", "Initial_Index_Value"]
        )
    portfolios = portfolios.sort_values(["Portfolio_Name", "Index_Start_Date"]).drop_duplicates(
        subset=["Portfolio_Name"],
        keep="first",
    )
    portfolios.insert(0, "Portfolio_Key", portfolios["Portfolio_Name"])
    return portfolios.reset_index(drop=True)


def _build_dim_series(analysis_metadata: pd.DataFrame) -> pd.DataFrame:
    dim_series = analysis_metadata[
        [
            "Series_ID",
            "Series_Type",
            "Portfolio_Name",
            "Variant",
            "Benchmark_ID",
            "Category",
            "Yahoo_Ticker",
            "ISIN",
            "Display_Name",
            "Price_Currency",
            "Instrument_Type",
            "Include_From_Date",
            "Index_Start_Date",
            "Initial_Index_Value",
            "Is_Main_Portfolio_Series",
            "Is_Category_Series",
            "Is_Benchmark",
            "Is_Overview_Eligible",
            "Is_Performance_Eligible",
        ]
    ].copy()
    dim_series.insert(2, "Portfolio_Key", dim_series["Portfolio_Name"])
    if dim_series["Series_ID"].duplicated().any():
        duplicates = dim_series.loc[dim_series["Series_ID"].duplicated(), "Series_ID"].tolist()
        raise ValueError(f"Dim_Series would contain duplicate Series_ID values: {duplicates}")
    return dim_series.reset_index(drop=True)


def _build_fact_series_daily(master_long: pd.DataFrame, dim_series: pd.DataFrame) -> pd.DataFrame:
    valid_ids = set(dim_series["Series_ID"].tolist())
    fact_daily = master_long.copy()
    fact_daily["Series_ID"] = _clean_text(fact_daily["Series_ID"])
    fact_daily = fact_daily[fact_daily["Series_ID"].isin(valid_ids)].copy()
    if fact_daily.empty:
        raise ValueError("Master_TimeSeries_Long has no rows for the BI analysis universe")
    fact_daily["Date"] = pd.to_datetime(fact_daily["Date"], errors="coerce")
    for column in ("RET", "IDX", "DD"):
        fact_daily[column] = pd.to_numeric(fact_daily[column], errors="coerce")
    return fact_daily[["Date", "Series_ID", "RET", "IDX", "DD"]].sort_values(
        ["Series_ID", "Date"]
    ).reset_index(drop=True)


def _build_dim_date(fact_series_daily: pd.DataFrame) -> pd.DataFrame:
    dates = pd.Index(pd.to_datetime(fact_series_daily["Date"], errors="coerce").dropna().unique()).sort_values()
    if len(dates) == 0:
        return pd.DataFrame(
            columns=["Date", "Year", "Month", "Month_Name", "Quarter", "YearMonth", "Is_YTD_Latest_Flag"]
        )
    latest_date = dates.max()
    dim_date = pd.DataFrame({"Date": dates})
    dim_date["Year"] = dim_date["Date"].dt.year
    dim_date["Month"] = dim_date["Date"].dt.month
    dim_date["Month_Name"] = dim_date["Date"].dt.strftime("%B")
    dim_date["Quarter"] = "Q" + dim_date["Date"].dt.quarter.astype(str)
    dim_date["YearMonth"] = dim_date["Date"].dt.strftime("%Y-%m")
    dim_date["Is_YTD_Latest_Flag"] = (
        (dim_date["Date"].dt.year == latest_date.year) & (dim_date["Date"] <= latest_date)
    )
    return dim_date.reset_index(drop=True)


def _build_fact_series_kpi(
    fact_series_daily: pd.DataFrame,
    dim_series: pd.DataFrame,
    rf_rate_annual: float,
    trading_days_per_year: int,
) -> pd.DataFrame:
    eligible_ids = set(
        dim_series.loc[dim_series["Is_Performance_Eligible"], "Series_ID"].tolist()
    )
    rows: list[dict[str, object]] = []
    for series_id, series_frame in fact_series_daily.groupby("Series_ID", sort=True):
        if series_id not in eligible_ids:
            continue
        for period in PERIOD_ORDER:
            period_slice = slice_period(series_frame, period)
            if not has_minimum_observations(period_slice.frame, period):
                continue
            rows.append(
                {
                    "Series_ID": series_id,
                    "Period": period,
                    **compute_kpis(period_slice.frame, rf_rate_annual, trading_days_per_year),
                }
            )

    columns = [
        "Series_ID",
        "Period",
        "Start_Date",
        "End_Date",
        "Obs_Days",
        "Return_Total",
        "CAGR",
        "Vol",
        "Sharpe",
        "Sortino",
        "Max_DD",
        "Calmar",
        "DD_Duration_Max_Days",
        "Positive_Days_Pct",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    fact_kpi = pd.DataFrame(rows)
    fact_kpi["Period"] = pd.Categorical(fact_kpi["Period"], categories=PERIOD_ORDER, ordered=True)
    return fact_kpi.sort_values(["Series_ID", "Period"]).reset_index(drop=True)[columns]


def _build_dim_instrument(
    series_definition: pd.DataFrame,
    portfolio_series_map: pd.DataFrame,
) -> pd.DataFrame:
    map_rows = portfolio_series_map[
        ["Yahoo_Ticker", "ISIN", "Display_Name", "Price_Currency"]
    ].copy()
    map_rows["Yahoo_Ticker"] = _nullable_text(map_rows["Yahoo_Ticker"])
    map_rows["ISIN"] = _nullable_text(map_rows["ISIN"])
    map_rows["Display_Name"] = _nullable_text(map_rows["Display_Name"])
    map_rows["Price_Currency"] = _nullable_text(map_rows["Price_Currency"])

    series_rows = series_definition[
        [
            "Yahoo_Ticker",
            "ISIN",
            "Display_Name",
            "Price_Currency",
            "Instrument_Type",
            "Category",
        ]
    ].copy()
    series_rows["Yahoo_Ticker"] = _nullable_text(series_rows["Yahoo_Ticker"])
    series_rows["ISIN"] = _nullable_text(series_rows["ISIN"])
    series_rows["Display_Name"] = _nullable_text(series_rows["Display_Name"])
    series_rows["Price_Currency"] = _nullable_text(series_rows["Price_Currency"])
    series_rows["Instrument_Type"] = _nullable_text(series_rows["Instrument_Type"])
    series_rows["Category"] = _nullable_text(series_rows["Category"])

    all_tickers = (
        pd.concat([map_rows[["Yahoo_Ticker"]], series_rows[["Yahoo_Ticker"]]], ignore_index=True)
        .dropna()
        .drop_duplicates()
        .sort_values("Yahoo_Ticker")
        .reset_index(drop=True)
    )
    if all_tickers.empty:
        return pd.DataFrame(
            columns=[
                "Instrument_Key",
                "Yahoo_Ticker",
                "ISIN",
                "Display_Name",
                "Price_Currency",
                "Instrument_Type",
                "Category",
                "Structure",
            ]
        )

    metadata_from_map = (
        map_rows.dropna(subset=["Yahoo_Ticker"])
        .sort_values(["Yahoo_Ticker", "Display_Name", "ISIN", "Price_Currency"])
        .drop_duplicates(subset=["Yahoo_Ticker"], keep="first")
    )
    metadata_from_series = (
        series_rows.dropna(subset=["Yahoo_Ticker"])
        .sort_values(["Yahoo_Ticker", "Display_Name", "ISIN", "Price_Currency", "Instrument_Type", "Category"])
        .drop_duplicates(subset=["Yahoo_Ticker"], keep="first")
    )
    dim_instrument = all_tickers.merge(metadata_from_map, on="Yahoo_Ticker", how="left")
    dim_instrument = dim_instrument.merge(
        metadata_from_series,
        on="Yahoo_Ticker",
        how="left",
        suffixes=("_map", "_series"),
    )
    dim_instrument.insert(0, "Instrument_Key", dim_instrument["Yahoo_Ticker"])
    for column in ("ISIN", "Display_Name", "Price_Currency", "Instrument_Type", "Category"):
        dim_instrument[column] = _combine_optional_columns(dim_instrument, column)
    dim_instrument["Structure"] = pd.NA
    return dim_instrument[
        [
            "Instrument_Key",
            "Yahoo_Ticker",
            "ISIN",
            "Display_Name",
            "Price_Currency",
            "Instrument_Type",
            "Category",
            "Structure",
        ]
    ]


def _build_fact_portfolio_allocation_snapshot(
    portfolio_series_map: pd.DataFrame,
    dim_series: pd.DataFrame,
    snapshot_date: pd.Timestamp,
) -> pd.DataFrame:
    valid_series = set(dim_series["Series_ID"].tolist())
    snapshot = portfolio_series_map.copy()
    snapshot["Portfolio_Name"] = _nullable_text(snapshot["Portfolio_Name"])
    snapshot["Series_ID"] = _clean_text(snapshot["Series_ID"])
    snapshot["ISIN"] = _nullable_text(snapshot["ISIN"])
    snapshot["Display_Name"] = _nullable_text(snapshot["Display_Name"])
    snapshot["Price_Currency"] = _nullable_text(snapshot["Price_Currency"])
    snapshot["Yahoo_Ticker"] = _nullable_text(snapshot["Yahoo_Ticker"])
    snapshot["Weight_Source"] = _nullable_text(snapshot["Weight_Source"])
    snapshot["Weight"] = pd.to_numeric(snapshot["Weight"], errors="coerce")
    snapshot = snapshot[
        snapshot["Series_ID"].isin(valid_series) & snapshot["Yahoo_Ticker"].notna() & snapshot["Weight"].notna()
    ].copy()
    snapshot.insert(0, "Portfolio_Key", snapshot["Portfolio_Name"])
    snapshot.insert(3, "Instrument_Key", snapshot["Yahoo_Ticker"])
    snapshot["Snapshot_Date"] = pd.Timestamp(snapshot_date).normalize()
    return snapshot[
        [
            "Portfolio_Key",
            "Series_ID",
            "Instrument_Key",
            "ISIN",
            "Display_Name",
            "Price_Currency",
            "Weight",
            "Weight_Source",
            "Snapshot_Date",
        ]
    ].sort_values(["Portfolio_Key", "Series_ID", "Instrument_Key"]).reset_index(drop=True)


def run(
    source_output_path: str | Path | None = None,
    bi_output_path: str | Path | None = None,
) -> None:
    """Read the shared workbook and write a first BI workbook."""
    _configure_logging()

    source_path = Path(source_output_path or config.BI_DATA_SOURCE_PATH)
    output_path = Path(bi_output_path or config.BI_DATA_OUTPUT_PATH)

    logging.info("Loading BI source workbook: %s", source_path)
    source = load_portfolio_output(source_path)
    rf_rate_annual, trading_days_per_year = extract_run_parameters(source.run_config)

    analysis_metadata = _build_analysis_metadata(source.series_definition, source.master_long)
    dim_portfolio = _build_dim_portfolio(analysis_metadata)
    dim_series = _build_dim_series(analysis_metadata)
    fact_series_daily = _build_fact_series_daily(source.master_long, dim_series)
    dim_date = _build_dim_date(fact_series_daily)
    fact_series_kpi = _build_fact_series_kpi(
        fact_series_daily,
        dim_series,
        rf_rate_annual,
        trading_days_per_year,
    )
    dim_instrument = _build_dim_instrument(source.series_definition, source.portfolio_series_map)
    snapshot_date = fact_series_daily["Date"].max()
    fact_allocation_snapshot = _build_fact_portfolio_allocation_snapshot(
        source.portfolio_series_map,
        dim_series,
        snapshot_date,
    )

    logging.info(
        "BI analysis universe: %s series, %s daily rows, %s KPI rows, snapshot date %s",
        len(dim_series),
        len(fact_series_daily),
        len(fact_series_kpi),
        pd.Timestamp(snapshot_date).date().isoformat(),
    )
    if dim_instrument.empty:
        logging.info("Dim_Instrument is empty; upstream artifact did not materialize instrument tickers")
    else:
        logging.info(
            "Dim_Instrument built from upstream ticker metadata in Series_Definition and Portfolio_Series_Map"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        dim_date.to_excel(writer, sheet_name="Dim_Date", index=False)
        dim_portfolio.to_excel(writer, sheet_name="Dim_Portfolio", index=False)
        dim_series.to_excel(writer, sheet_name="Dim_Series", index=False)
        dim_instrument.to_excel(writer, sheet_name="Dim_Instrument", index=False)
        fact_series_daily.to_excel(writer, sheet_name="Fact_Series_Daily", index=False)
        fact_series_kpi.to_excel(writer, sheet_name="Fact_Series_KPI", index=False)
        fact_allocation_snapshot.to_excel(
            writer,
            sheet_name=ALLOCATION_SNAPSHOT_SHEET_NAME,
            index=False,
        )

    logging.info("BI data workbook written: %s", output_path)


if __name__ == "__main__":
    args = _parse_args()
    run(
        source_output_path=args.input_path,
        bi_output_path=args.output_path,
    )
