"""Tester för fond-rapportens diversifieringseffekt och riskreduktion.

Syntetisk data med analytiskt facit: två tillgångar med konstruerade
avkastningsmönster där stickprovskorrelationen är exakt 0 respektive exakt 1,
så att Σwσ, √(wᵀΣw) och riskreduktionen kan räknas för hand.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import TRADING_DAYS_PER_YEAR
from tools.fond_rapport.data import BIData
from tools.fond_rapport.risk import (
    compute_portfolio_risk_window,
    day_weighted_avg_weights,
    risk_decomposition,
    risk_reduction_level,
)

N_DAYS = 40  # multipel av 4 så att de ortogonala mönstren ger exakt nollkorrelation
A, B = 0.02, 0.01

EMPTY = pd.DataFrame()


def _dates(n: int = N_DAYS) -> pd.DatetimeIndex:
    return pd.bdate_range("2024-01-01", periods=n)


def _zero_corr_returns() -> pd.DataFrame:
    """rA = [+a,−a,…], rB = [+b,+b,−b,−b,…]: medel 0, stickprovskorrelation exakt 0."""
    r_a = np.tile([A, -A], N_DAYS // 2)
    r_b = np.tile([B, B, -B, -B], N_DAYS // 4)
    return pd.DataFrame({"FOND_A": r_a, "FOND_B": r_b}, index=_dates())


def _sample_sigma(amplitude: float) -> float:
    """Annualiserad std för ett ±amplitude-mönster med medel 0 (ddof=1)."""
    return amplitude * np.sqrt(N_DAYS / (N_DAYS - 1)) * np.sqrt(TRADING_DAYS_PER_YEAR)


def test_risk_decomposition_zero_correlation_matches_analytic():
    rets = _zero_corr_returns()
    weights = pd.Series({"FOND_A": 0.5, "FOND_B": 0.5})
    sigma_a, sigma_b = _sample_sigma(A), _sample_sigma(B)
    expected_summed = 0.5 * sigma_a + 0.5 * sigma_b
    expected_model = np.sqrt(0.25 * sigma_a**2 + 0.25 * sigma_b**2)

    portfolio_rets = rets.mul(weights, axis=1).sum(axis=1)
    portfolio_vol = float(portfolio_rets.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))

    summed, model, diversification, risk_reduction = risk_decomposition(
        rets, weights, portfolio_vol
    )
    assert summed == pytest.approx(expected_summed, rel=1e-12)
    assert model == pytest.approx(expected_model, rel=1e-12)
    # Dagligt ombalanserad portfölj: realiserad vol == modellvol exakt.
    assert portfolio_vol == pytest.approx(expected_model, rel=1e-12)
    assert diversification == pytest.approx(expected_summed - expected_model, rel=1e-9)
    assert risk_reduction == pytest.approx(1.0 - expected_model / expected_summed, rel=1e-9)
    assert risk_reduction > 0


def test_risk_decomposition_perfect_correlation_gives_zero_reduction():
    r_a = np.tile([A, -A], N_DAYS // 2)
    rets = pd.DataFrame({"FOND_A": r_a, "FOND_B": 0.5 * r_a}, index=_dates())
    weights = pd.Series({"FOND_A": 0.6, "FOND_B": 0.4})
    portfolio_rets = rets.mul(weights, axis=1).sum(axis=1)
    portfolio_vol = float(portfolio_rets.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))

    summed, model, diversification, risk_reduction = risk_decomposition(
        rets, weights, portfolio_vol
    )
    # Perfekt korrelation: √(wᵀΣw) = Σwσ – ingen diversifieringseffekt.
    assert model == pytest.approx(summed, rel=1e-12)
    assert diversification == pytest.approx(0.0, abs=1e-12)
    assert risk_reduction == pytest.approx(0.0, abs=1e-12)


def test_risk_reduction_level_thresholds():
    assert risk_reduction_level(0.10) == "svag spridning"
    assert risk_reduction_level(0.1499) == "svag spridning"
    assert risk_reduction_level(0.15) == "god spridning"
    assert risk_reduction_level(0.2499) == "god spridning"
    assert risk_reduction_level(0.25) == "stark spridning"
    assert risk_reduction_level(float("nan")) == "–"


def test_day_weighted_avg_weights_weights_periods_by_days():
    # Två periodslut: 10 dagar med 100 % A, därefter 30 dagar med 100 % B.
    start = pd.Timestamp("2024-01-01")
    alloc = pd.DataFrame(
        {
            "Portfolio_Key": ["T", "T"],
            "Instrument_Key": ["FOND_A", "FOND_B"],
            "Period_End_Date": [pd.Timestamp("2024-01-11"), pd.Timestamp("2024-02-10")],
            "Weight": [1.0, 1.0],
        }
    )
    avg = day_weighted_avg_weights(alloc, start, pd.Timestamp("2024-02-10"))
    assert avg["FOND_A"] == pytest.approx(0.25)
    assert avg["FOND_B"] == pytest.approx(0.75)


def _synthetic_bidata(rets: pd.DataFrame, weights: pd.Series) -> tuple[BIData, pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    """BIData + prismatris för en dagligt ombalanserad portfölj av två SEK-fonder."""
    dates = rets.index
    prices = 100.0 * (1.0 + rets).cumprod()
    # Prisraden dagen före första avkastningsdagen är basen (avkastning 0 den dagen).
    base_date = dates[0] - pd.tseries.offsets.BDay(1)
    prices = pd.concat([pd.DataFrame({c: 100.0 for c in rets.columns}, index=[base_date]), prices])

    port_rets = rets.mul(weights, axis=1).sum(axis=1)
    idx = 100.0 * (1.0 + port_rets).cumprod()
    fact_daily = pd.DataFrame(
        {
            "Series_ID": "PORT_T_REAL",
            "Date": dates,
            "IDX": idx.to_numpy(),
            "RET": port_rets.to_numpy(),
            "DD": 0.0,
        }
    )
    # Bassrad så att asof(start) hittar nivå 100 vid basdatumet.
    base_row = pd.DataFrame(
        {"Series_ID": ["PORT_T_REAL"], "Date": [base_date], "IDX": [100.0], "RET": [0.0], "DD": [0.0]}
    )
    fact_daily = pd.concat([base_row, fact_daily], ignore_index=True)

    alloc_monthly = pd.DataFrame(
        {
            "Portfolio_Key": "T",
            "Instrument_Key": list(weights.index),
            "Period_End_Date": dates[-1],
            "Weight": list(weights.to_numpy()),
        }
    )
    dim_instrument = pd.DataFrame(
        {
            "Instrument_Key": list(weights.index),
            "ISIN": ["ISIN_A", "ISIN_B"],
            "Display_Name": list(weights.index),
            "Price_Currency": "SEK",
            "Category": "Breda fonder",
        }
    )
    data = BIData(
        dim_date=EMPTY,
        dim_portfolio=EMPTY,
        dim_series=EMPTY,
        dim_instrument=dim_instrument,
        fact_daily=fact_daily,
        fact_kpi=EMPTY,
        fact_alloc=EMPTY,
        fact_alloc_monthly=alloc_monthly,
    )
    return data, prices, base_date, dates[-1]


def test_compute_portfolio_risk_window_end_to_end_zero_correlation():
    rets = _zero_corr_returns()
    weights = pd.Series({"FOND_A": 0.5, "FOND_B": 0.5})
    data, prices, start, end = _synthetic_bidata(rets, weights)

    result = compute_portfolio_risk_window(data, prices, "T", "Since_Start", start, end)

    sigma_a, sigma_b = _sample_sigma(A), _sample_sigma(B)
    expected_summed = 0.5 * sigma_a + 0.5 * sigma_b
    expected_model = np.sqrt(0.25 * sigma_a**2 + 0.25 * sigma_b**2)
    assert result.excluded == []
    assert result.summed_risk == pytest.approx(expected_summed, rel=1e-9)
    assert result.portfolio_risk == pytest.approx(expected_model, rel=1e-9)
    assert result.model_risk == pytest.approx(expected_model, rel=1e-9)
    assert result.model_gap == pytest.approx(0.0, abs=1e-12)
    assert result.diversification == pytest.approx(expected_summed - expected_model, rel=1e-9)
    assert result.risk_reduction == pytest.approx(1.0 - expected_model / expected_summed, rel=1e-9)
    assert result.risk_reduction > 0
    assert result.level == "stark spridning"


def test_compute_portfolio_risk_window_excludes_instrument_without_history():
    rets = _zero_corr_returns()
    weights = pd.Series({"FOND_A": 0.5, "FOND_B": 0.5})
    data, prices, start, end = _synthetic_bidata(rets, weights)
    # FOND_B saknar prishistorik första halvan av fönstret → exkluderas + omviktas.
    prices.loc[prices.index[: N_DAYS // 2], "FOND_B"] = np.nan

    result = compute_portfolio_risk_window(data, prices, "T", "Since_Start", start, end)

    assert result.excluded == ["FOND_B"]
    assert result.excluded_weight == pytest.approx(0.5)
    assert result.weights.index.tolist() == ["FOND_A"]
    assert result.weights.sum() == pytest.approx(1.0)
    # Enfondsportfölj efter exkludering: summerad risk = fondens egen vol.
    assert result.summed_risk == pytest.approx(_sample_sigma(A), rel=1e-9)
