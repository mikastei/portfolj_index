"""Builders for dashboard output tables."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from .dashboard_metrics import (
    PERIOD_ORDER,
    compute_kpis,
    compute_total_return,
    correlation_for_period,
    has_minimum_observations,
    slice_period,
)


def build_kpi_summary(
    master_long: pd.DataFrame,
    analysis_metadata: pd.DataFrame,
    rf_rate_annual: float,
    trading_days_per_year: int,
) -> pd.DataFrame:
    """Build one KPI row per series and valid period."""
    rows: list[dict[str, object]] = []
    metadata_by_series = analysis_metadata.set_index("Series_ID")

    for series_id, series_frame in master_long.groupby("Series_ID", sort=True):
        meta = metadata_by_series.loc[series_id]
        for period in PERIOD_ORDER:
            period_slice = slice_period(series_frame, period)
            if not has_minimum_observations(period_slice.frame, period):
                continue
            metrics = compute_kpis(period_slice.frame, rf_rate_annual, trading_days_per_year)
            rows.append(
                {
                    "Series_ID": series_id,
                    "Display_Name": meta["Display_Name"],
                    "Series_Type": meta["Series_Type"],
                    "Portfolio_Name": meta["Portfolio_Name"],
                    "Variant": meta["Variant"],
                    "Period": period,
                    **metrics,
                }
            )

    columns = [
        "Series_ID",
        "Display_Name",
        "Series_Type",
        "Portfolio_Name",
        "Variant",
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
    out = pd.DataFrame(rows)
    out["Period"] = pd.Categorical(out["Period"], categories=PERIOD_ORDER, ordered=True)
    return out.sort_values(["Series_Type", "Display_Name", "Period"]).reset_index(drop=True)[columns]


def build_period_returns(master_long: pd.DataFrame, analysis_metadata: pd.DataFrame) -> pd.DataFrame:
    """Build period return table with NaN for periods lacking enough data."""
    rows: list[dict[str, object]] = []
    metadata_by_series = analysis_metadata.set_index("Series_ID")

    for series_id, series_frame in master_long.groupby("Series_ID", sort=True):
        meta = metadata_by_series.loc[series_id]
        row: dict[str, object] = {
            "Series_ID": series_id,
            "Display_Name": meta["Display_Name"],
            "Series_Type": meta["Series_Type"],
            "Portfolio_Name": meta["Portfolio_Name"],
            "Variant": meta["Variant"],
        }
        for period in ("30D", "YTD", "1Y", "Since_Start"):
            period_slice = slice_period(series_frame, period)
            row[period] = (
                compute_total_return(period_slice.frame)
                if has_minimum_observations(period_slice.frame, period)
                else pd.NA
            )
        rows.append(row)

    columns = [
        "Series_ID",
        "Display_Name",
        "Series_Type",
        "Portfolio_Name",
        "Variant",
        "30D",
        "YTD",
        "1Y",
        "Since_Start",
    ]
    return pd.DataFrame(rows, columns=columns).sort_values(["Series_Type", "Display_Name"]).reset_index(drop=True)


def build_chart_wide(master_long: pd.DataFrame, analysis_metadata: pd.DataFrame, value_column: str) -> pd.DataFrame:
    """Pivot IDX or DD values to wide chart format using Series_ID columns."""
    valid_columns = {"IDX", "DD"}
    if value_column not in valid_columns:
        raise ValueError(f"value_column must be one of {sorted(valid_columns)}")
    analysis_ids = analysis_metadata["Series_ID"].tolist()
    chart = (
        master_long[master_long["Series_ID"].isin(analysis_ids)][["Date", "Series_ID", value_column]]
        .pivot(index="Date", columns="Series_ID", values=value_column)
        .sort_index()
        .reset_index()
    )
    return chart


def build_correlation_long(master_long: pd.DataFrame, analysis_metadata: pd.DataFrame) -> pd.DataFrame:
    """Build pairwise daily return correlations in long format."""
    returns_wide = (
        master_long[["Date", "Series_ID", "RET"]]
        .pivot(index="Date", columns="Series_ID", values="RET")
        .sort_index()
    )
    latest_dates = master_long.groupby("Series_ID")["Date"].max().to_dict()
    correlations = pd.concat(
        [
            correlation_for_period(returns_wide, "Since_Start", latest_dates),
            correlation_for_period(returns_wide, "1Y", latest_dates),
        ],
        ignore_index=True,
    )
    if correlations.empty:
        return pd.DataFrame(
            columns=[
                "Period",
                "Series_ID_Row",
                "Series_ID_Col",
                "Display_Name_Row",
                "Display_Name_Col",
                "Correlation",
            ]
        )

    display_name_map = analysis_metadata.set_index("Series_ID")["Display_Name"].to_dict()
    correlations["Display_Name_Row"] = correlations["Series_ID_Row"].map(display_name_map)
    correlations["Display_Name_Col"] = correlations["Series_ID_Col"].map(display_name_map)
    columns = [
        "Period",
        "Series_ID_Row",
        "Series_ID_Col",
        "Display_Name_Row",
        "Display_Name_Col",
        "Correlation",
    ]
    return correlations.sort_values(["Period", "Series_ID_Row", "Series_ID_Col"]).reset_index(drop=True)[columns]


def build_allocation_snapshot(
    portfolio_series_map: pd.DataFrame,
    series_definition: pd.DataFrame,
) -> pd.DataFrame:
    """Build allocation snapshot from Portfolio_Series_Map and derive Variant from series metadata."""
    variant_map = series_definition.set_index("Series_ID")["Variant"].to_dict()
    snapshot = portfolio_series_map.copy()
    snapshot["Variant"] = snapshot["Series_ID"].map(variant_map)
    columns = [
        "Portfolio_Name",
        "Series_ID",
        "Variant",
        "Yahoo_Ticker",
        "Weight",
        "Weight_Source",
    ]
    return snapshot.loc[:, columns].sort_values(["Portfolio_Name", "Variant", "Yahoo_Ticker"]).reset_index(drop=True)


def build_dashboard_config() -> pd.DataFrame:
    """Create default configuration rows for downstream Excel dashboard logic."""
    return pd.DataFrame(
        [
            {"Config_Key": "default_variant", "Config_Value": "REAL"},
            {"Config_Key": "default_period", "Config_Value": "Since_Start"},
            {"Config_Key": "include_series_types", "Config_Value": "PORT,BM"},
        ]
    )


def build_build_info(
    source_output_file: str,
    master_long: pd.DataFrame,
    analysis_metadata: pd.DataFrame,
    rf_rate_annual: float,
    trading_days_per_year: int,
) -> pd.DataFrame:
    """Build metadata for the dashboard-prep workbook."""
    created_at = datetime.now()
    date_min = master_long["Date"].min() if not master_long.empty else pd.NaT
    date_max = master_long["Date"].max() if not master_long.empty else pd.NaT
    number_of_portfolios = int(
        analysis_metadata.loc[analysis_metadata["Series_Type"] == "PORT", "Portfolio_Name"]
        .dropna()
        .nunique()
    )
    number_of_benchmarks = int((analysis_metadata["Series_Type"] == "BM").sum())
    return pd.DataFrame(
        [
            {
                "Created_At": created_at,
                "Source_Output_File": source_output_file,
                "Date_Min": date_min,
                "Date_Max": date_max,
                "Number_Of_Analysis_Series": int(len(analysis_metadata)),
                "Number_Of_Portfolios": number_of_portfolios,
                "Number_Of_Benchmarks": number_of_benchmarks,
                "RF_RATE_ANNUAL": rf_rate_annual,
                "TRADING_DAYS_PER_YEAR": trading_days_per_year,
            }
        ]
    )
