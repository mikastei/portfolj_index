"""Metric calculations for dashboard-ready portfolio tables."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

PERIOD_ORDER = ["Since_Start", "YTD", "30D", "1Y"]
PERIOD_MIN_OBS = {
    "Since_Start": 2,
    "YTD": 20,
    "30D": 20,
    "1Y": 126,
}
RISK_MIN_RET_OBS = 20


@dataclass(frozen=True)
class PeriodSlice:
    """Prepared time window for one series and one dashboard period."""

    period: str
    frame: pd.DataFrame
    latest_date: pd.Timestamp


def prepare_series_frame(series_frame: pd.DataFrame) -> pd.DataFrame:
    """Sort a single-series frame and keep only the columns used by KPI logic."""
    required = ["Date", "RET", "IDX", "DD"]
    missing = [column for column in required if column not in series_frame.columns]
    if missing:
        raise ValueError(f"Series frame is missing required columns: {missing}")
    frame = series_frame.loc[:, required].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame = frame.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    for column in ("RET", "IDX", "DD"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _period_start(latest_date: pd.Timestamp, period: str) -> pd.Timestamp | None:
    if period == "Since_Start":
        return None
    if period == "YTD":
        return pd.Timestamp(year=latest_date.year, month=1, day=1)
    if period == "30D":
        return latest_date - pd.Timedelta(days=30)
    if period == "1Y":
        return latest_date - pd.DateOffset(years=1)
    raise ValueError(f"Unsupported period: {period}")


def slice_period(series_frame: pd.DataFrame, period: str) -> PeriodSlice:
    """Slice one series using the latest available date for that series."""
    frame = prepare_series_frame(series_frame)
    if frame.empty:
        raise ValueError("Cannot slice an empty series frame")
    latest_date = frame["Date"].max()
    start_date = _period_start(latest_date, period)
    if start_date is None:
        window = frame.copy()
    else:
        window = frame[(frame["Date"] >= start_date) & (frame["Date"] <= latest_date)].copy()
    return PeriodSlice(period=period, frame=window.reset_index(drop=True), latest_date=latest_date)


def has_minimum_observations(period_frame: pd.DataFrame, period: str) -> bool:
    """Check whether a period should exist at all for a series."""
    return len(period_frame) >= PERIOD_MIN_OBS[period]


def compute_total_return(period_frame: pd.DataFrame) -> float:
    """Compute geometric total return from IDX when possible, otherwise chain RET."""
    idx_values = period_frame["IDX"].dropna()
    if len(idx_values) >= 2 and idx_values.iloc[0] != 0:
        return float(idx_values.iloc[-1] / idx_values.iloc[0] - 1.0)

    ret_values = period_frame["RET"].dropna()
    if len(ret_values) >= 1:
        return float((1.0 + ret_values).prod() - 1.0)
    return np.nan


def _compute_cagr(total_return: float, start_date: pd.Timestamp, end_date: pd.Timestamp) -> float:
    if pd.isna(total_return):
        return np.nan
    days = max((end_date - start_date).days, 0)
    years = days / 365.25
    if years <= 0:
        return np.nan
    base = 1.0 + total_return
    if base <= 0:
        return np.nan
    return float(base ** (1.0 / years) - 1.0)


def _max_drawdown_duration(dd_values: pd.Series) -> float:
    """
    Count drawdown duration in observations, not calendar days.

    NaN is returned when DD data is unavailable or entirely non-negative.
    """
    dd_valid = dd_values.dropna()
    if dd_valid.empty:
        return np.nan
    in_drawdown = dd_valid < 0
    if not in_drawdown.any():
        return 0.0

    longest = 0
    current = 0
    for flag in in_drawdown.tolist():
        if flag:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return float(longest)


def compute_kpis(
    period_frame: pd.DataFrame,
    rf_rate_annual: float,
    trading_days_per_year: int,
) -> dict[str, float | int | pd.Timestamp]:
    """
    Compute dashboard KPIs for one series-period.

    Risk metrics use only non-null RET values. If fewer than 20 daily returns are
    available, risk KPIs are set to NaN while the row itself can still exist.
    """
    if period_frame.empty:
        raise ValueError("Cannot compute KPIs for an empty period frame")

    start_date = period_frame["Date"].min()
    end_date = period_frame["Date"].max()
    total_return = compute_total_return(period_frame)
    cagr = _compute_cagr(total_return, start_date, end_date)

    ret_valid = period_frame["RET"].dropna()
    dd_valid = period_frame["DD"].dropna()
    obs_days = int(len(period_frame))

    vol = np.nan
    sharpe = np.nan
    sortino = np.nan
    max_dd = np.nan
    calmar = np.nan
    dd_duration = np.nan
    positive_days_pct = np.nan

    if len(ret_valid) >= RISK_MIN_RET_OBS:
        vol_daily = ret_valid.std(ddof=1)
        if pd.notna(vol_daily):
            vol = float(vol_daily * np.sqrt(trading_days_per_year))
        if pd.notna(vol) and vol != 0 and pd.notna(cagr):
            sharpe = float((cagr - rf_rate_annual) / vol)

        # Downside deviation uses returns below 0 as the downside threshold.
        downside = ret_valid.clip(upper=0.0)
        downside_dev_daily = float(np.sqrt(np.mean(np.square(downside)))) if len(downside) else np.nan
        if pd.notna(downside_dev_daily):
            downside_dev = downside_dev_daily * np.sqrt(trading_days_per_year)
            if downside_dev != 0 and pd.notna(cagr):
                sortino = float((cagr - rf_rate_annual) / downside_dev)

        positive_days_pct = float((ret_valid > 0).mean())
        dd_duration = _max_drawdown_duration(dd_valid)

        if not dd_valid.empty:
            max_dd = float(dd_valid.min())
        if pd.notna(cagr) and pd.notna(max_dd) and max_dd != 0:
            calmar = float(cagr / abs(max_dd))

    return {
        "Start_Date": start_date,
        "End_Date": end_date,
        "Obs_Days": obs_days,
        "Return_Total": total_return,
        "CAGR": cagr,
        "Vol": vol,
        "Sharpe": sharpe,
        "Sortino": sortino,
        "Max_DD": max_dd,
        "Calmar": calmar,
        "DD_Duration_Max_Days": dd_duration,
        "Positive_Days_Pct": positive_days_pct,
    }


def correlation_for_period(
    returns_wide: pd.DataFrame,
    period: str,
    latest_dates: dict[str, pd.Timestamp],
) -> pd.DataFrame:
    """Calculate pairwise correlation using pairwise overlap and a per-series period window."""
    if period not in {"Since_Start", "1Y"}:
        raise ValueError(f"Unsupported correlation period: {period}")
    series_ids = returns_wide.columns.tolist()
    rows: list[dict[str, object]] = []

    for row_index, row_id in enumerate(series_ids):
        row_series = returns_wide[row_id]
        row_latest = latest_dates[row_id]
        row_start = _period_start(row_latest, period)
        row_window = row_series if row_start is None else row_series[row_series.index >= row_start]

        for col_index in range(row_index + 1, len(series_ids)):
            col_id = series_ids[col_index]
            col_series = returns_wide[col_id]
            col_latest = latest_dates[col_id]
            col_start = _period_start(col_latest, period)
            col_window = col_series if col_start is None else col_series[col_series.index >= col_start]

            overlap = pd.concat([row_window, col_window], axis=1, join="inner").dropna()
            if len(overlap) < RISK_MIN_RET_OBS:
                continue

            correlation = overlap.iloc[:, 0].corr(overlap.iloc[:, 1])
            if pd.isna(correlation):
                continue
            rows.append(
                {
                    "Period": period,
                    "Series_ID_Row": row_id,
                    "Series_ID_Col": col_id,
                    "Correlation": float(correlation),
                }
            )

    return pd.DataFrame(rows)
