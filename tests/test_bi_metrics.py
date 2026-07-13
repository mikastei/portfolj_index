import numpy as np
import pandas as pd
import pytest

from src.bi_metrics import (
    compute_kpis,
    compute_total_return,
    has_minimum_observations,
    prepare_series_frame,
    slice_period,
)


def _series_frame(n_days=30, start="2026-01-01"):
    dates = pd.date_range(start, periods=n_days, freq="D")
    ret = pd.Series([0.0] + [0.001] * (n_days - 1), index=dates)
    idx = 100.0 * (1.0 + ret).cumprod()
    running_max = idx.cummax()
    dd = idx / running_max - 1.0
    return pd.DataFrame({"Date": dates, "RET": ret.values, "IDX": idx.values, "DD": dd.values})


def test_prepare_series_frame_requires_columns():
    with pytest.raises(ValueError, match="missing required columns"):
        prepare_series_frame(pd.DataFrame({"Date": [], "RET": []}))


def test_slice_period_since_start_keeps_full_frame():
    frame = _series_frame(10)
    sliced = slice_period(frame, "Since_Start")
    assert len(sliced.frame) == 10


def test_slice_period_30d_windows_from_latest_date():
    frame = _series_frame(60)
    sliced = slice_period(frame, "30D")
    assert sliced.latest_date == frame["Date"].max()
    assert sliced.frame["Date"].min() >= sliced.latest_date - pd.Timedelta(days=30)


def test_has_minimum_observations_respects_period_thresholds():
    frame = _series_frame(10)
    assert has_minimum_observations(frame, "Since_Start") is True
    assert has_minimum_observations(frame, "1Y") is False


def test_compute_total_return_uses_idx_when_available():
    frame = pd.DataFrame({"IDX": [100.0, 110.0], "RET": [0.0, 0.10]})
    assert compute_total_return(frame) == pytest.approx(0.10)


def test_compute_total_return_falls_back_to_chained_ret():
    frame = pd.DataFrame({"IDX": [np.nan, np.nan], "RET": [0.01, 0.02]})
    assert compute_total_return(frame) == pytest.approx(1.01 * 1.02 - 1.0)


def test_compute_kpis_below_min_obs_leaves_risk_metrics_nan():
    frame = _series_frame(5)
    kpis = compute_kpis(frame, rf_rate_annual=0.03, trading_days_per_year=252)
    assert kpis["Obs_Days"] == 5
    assert pd.isna(kpis["Vol"])
    assert pd.isna(kpis["Sharpe"])


def test_compute_kpis_computes_risk_metrics_with_enough_obs():
    frame = _series_frame(40)
    kpis = compute_kpis(frame, rf_rate_annual=0.0, trading_days_per_year=252)
    assert kpis["Vol"] > 0
    assert kpis["Positive_Days_Pct"] == pytest.approx(39 / 40)
    assert kpis["Max_DD"] <= 0.0


def test_compute_kpis_raises_on_empty_frame():
    with pytest.raises(ValueError, match="empty period frame"):
        compute_kpis(pd.DataFrame(), rf_rate_annual=0.0, trading_days_per_year=252)
