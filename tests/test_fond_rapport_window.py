"""Tester för fond-rapportens fönster-, horisont- och KPI-logik.

Använder syntetisk data så att testerna är deterministiska och inte beror på
produktions-BI-filen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tools.fond_rapport.data import BIData
from tools.fond_rapport.metrics import WindowSlice, compute_kpis, horizon_return
from tools.fond_rapport.window import (
    build_horizons,
    derive_inception,
    rebase_series,
    resolve_as_of,
)

EMPTY = pd.DataFrame()


def _bidata(fact_daily: pd.DataFrame) -> BIData:
    return BIData(
        dim_date=EMPTY,
        dim_portfolio=EMPTY,
        dim_series=EMPTY,
        dim_instrument=EMPTY,
        fact_daily=fact_daily,
        fact_kpi=EMPTY,
        fact_alloc=EMPTY,
        fact_alloc_monthly=EMPTY,
    )


def _series(series_id: str, dates: pd.DatetimeIndex, idx: np.ndarray) -> pd.DataFrame:
    ret = np.concatenate([[0.0], idx[1:] / idx[:-1] - 1.0])
    return pd.DataFrame({"Date": dates, "Series_ID": series_id, "RET": ret, "IDX": idx})


# --- inception ----------------------------------------------------------------


def test_derive_inception_is_last_flat_day_before_first_move():
    dates = pd.bdate_range("2024-01-01", periods=10)
    idx = np.array([100.0] * 5 + [100.0, 101.0, 102.0, 101.5, 103.0])
    # Första icke-noll-avkastningen inträffar på index 6 (dag efter sista platta).
    data = _bidata(_series("PORT_EGEN_REAL", dates, idx))
    assert derive_inception(data) == pd.Timestamp(dates[5])


def test_derive_inception_no_flat_prehistory_uses_first_day():
    dates = pd.bdate_range("2024-01-01", periods=5)
    idx = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
    data = _bidata(_series("PORT_EGEN_REAL", dates, idx))
    assert derive_inception(data) == pd.Timestamp(dates[0])


# --- as-of --------------------------------------------------------------------


def test_resolve_as_of_defaults_to_latest_and_rejects_future():
    dates = pd.bdate_range("2024-01-01", periods=5)
    data = _bidata(_series("PORT_EGEN_REAL", dates, np.linspace(100, 104, 5)))
    assert resolve_as_of(data, None) == pd.Timestamp(dates[-1])
    with pytest.raises(ValueError):
        resolve_as_of(data, "2030-01-01")


# --- horisonter ---------------------------------------------------------------


def test_horizons_measure_and_gating():
    inception = pd.Timestamp("2024-08-21")
    as_of = pd.Timestamp("2026-07-03")
    hz = {h.key: h for h in build_horizons(inception, as_of)}

    assert hz["YTD"].measure == "cumulative"  # under ett år
    assert hz["YTD"].start == pd.Timestamp("2026-01-01")
    assert hz["1Y"].measure == "cagr"  # exakt ett kalenderår -> annualiseras
    assert hz["1Y"].start == pd.Timestamp("2025-07-03")
    assert hz["Since_Start"].measure == "cagr"
    assert hz["Since_Start"].start == inception

    # 3Y gate:as tills fönstret rymmer tre år.
    assert hz["3Y"].available is False
    assert "3 års data" in hz["3Y"].note
    assert hz["Since_Start"].available and hz["1Y"].available and hz["YTD"].available


def test_since_start_is_cumulative_before_one_year_old():
    inception = pd.Timestamp("2026-03-01")
    as_of = pd.Timestamp("2026-07-03")
    hz = {h.key: h for h in build_horizons(inception, as_of)}
    # EGEN är yngre än ett år -> "sedan start" annualiseras aldrig.
    assert hz["Since_Start"].measure == "cumulative"
    assert hz["1Y"].available is False  # 1Y-start ligger före inception


# --- rebasering ---------------------------------------------------------------


def test_rebase_series_hits_exactly_100_and_slices():
    dates = pd.bdate_range("2024-01-01", periods=20)
    idx = pd.Series(np.linspace(80, 120, 20), index=dates)
    inception = dates[5]
    as_of = dates[15]
    reb = rebase_series(idx, inception, as_of)
    assert reb.iloc[0] == pytest.approx(100.0, abs=1e-12)
    assert reb.index.min() == inception and reb.index.max() == as_of
    # Rebasering bevarar kvoter: sista/första == råa sista/första.
    assert reb.iloc[-1] / reb.iloc[0] == pytest.approx(idx.loc[as_of] / idx.loc[inception])


# --- KPI:er -------------------------------------------------------------------


def test_horizon_return_cumulative_vs_cagr():
    dates = pd.bdate_range("2024-01-01", periods=400)
    idx = 100.0 * (1.03) ** (np.arange(400) / 252.0)  # jämn tillväxt
    data = _bidata(_series("S", dates, idx))
    start, end = dates[0], dates[-1]
    sl = WindowSlice(data, "S", start, end)

    total = idx[-1] / idx[0] - 1.0
    assert horizon_return(sl, "cumulative") == pytest.approx(total)

    years = (end - start).days / 365.25
    expected_cagr = (1.0 + total) ** (1.0 / years) - 1.0
    assert horizon_return(sl, "cagr") == pytest.approx(expected_cagr)


def test_compute_kpis_matches_manual():
    dates = pd.bdate_range("2024-01-01", periods=60)
    rng = np.random.default_rng(0)
    rets = np.concatenate([[0.0], rng.normal(0.0005, 0.01, 59)])
    idx = 100.0 * np.cumprod(1.0 + rets)
    data = _bidata(_series("S", dates, idx))
    sl = WindowSlice(data, "S", dates[0], dates[-1])
    kpis = compute_kpis(sl)

    assert kpis["Return_Total"] == pytest.approx(idx[-1] / idx[0] - 1.0)
    dd = (idx / np.maximum.accumulate(idx) - 1.0).min()
    assert kpis["Max_DD"] == pytest.approx(dd)
    assert kpis["Vol"] > 0
