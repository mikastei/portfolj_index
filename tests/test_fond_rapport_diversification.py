"""Tester för fond-rapportens diversifieringsmått: DR, ENB, MCTR ([AZ]).

Syntetisk data med analytiskt facit, i samma stil som test_fond_rapport_risk.py:
konstruerade avkastningsmönster där korrelationen mellan instrument är exakt känd
(0, delvis eller 1), så att DR/ENB/MCTR kan räknas för hand.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import TRADING_DAYS_PER_YEAR
from tools.fond_rapport.data import BIData
from tools.fond_rapport.diversification import (
    compute_diversification_window,
    diversification_ratio,
    effective_number_of_bets,
    risk_contributions,
)
from tools.fond_rapport.risk import compute_portfolio_risk_window

EMPTY = pd.DataFrame()


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2024-01-01", periods=n)


def _hadamard8() -> np.ndarray:
    """8x8 Hadamard-matris (±1). Kolumnerna är parvis ortogonala och – förutom
    kolumn 0 (allt ettor) – nollsummerande, vilket ger exakt nollkorrelation
    mellan valfria av kolumnerna 1..7 utan att förlita sig på slumptalsapproximation.
    """
    h2 = np.array([[1.0, 1.0], [1.0, -1.0]])
    return np.kron(np.kron(h2, h2), h2)


# --- Diversification Ratio ----------------------------------------------------


def test_diversification_ratio_matches_risk_reduction_identity():
    summed, model = 0.10, 0.07
    risk_reduction = 1.0 - model / summed
    dr = diversification_ratio(summed, model)
    assert dr == pytest.approx(1.0 / (1.0 - risk_reduction), rel=1e-12)
    assert dr == pytest.approx(summed / model, rel=1e-12)


def test_diversification_ratio_zero_portfolio_risk_is_nan():
    assert np.isnan(diversification_ratio(0.10, 0.0))


# --- ENB ------------------------------------------------------------------------


def test_enb_identity_correlation_gives_n():
    h = _hadamard8()
    rets = pd.DataFrame(
        0.01 * h[:, 1:5], index=_dates(8), columns=["FOND_A", "FOND_B", "FOND_C", "FOND_D"]
    )
    corr = rets.corr().to_numpy()
    assert corr == pytest.approx(np.eye(4), abs=1e-9)
    enb = effective_number_of_bets(rets)
    assert enb == pytest.approx(4.0, rel=1e-9)


def test_enb_perfect_correlation_gives_one():
    base = np.tile([0.01, -0.01], 10)
    rets = pd.DataFrame(
        {"FOND_A": base, "FOND_B": 0.5 * base, "FOND_C": 2.0 * base}, index=_dates(20)
    )
    enb = effective_number_of_bets(rets)
    assert enb == pytest.approx(1.0, abs=1e-9)


def test_enb_bounded_between_one_and_n_for_partial_correlation():
    n_days = 40
    r_a = np.tile([0.02, -0.02], n_days // 2)
    r_b = np.tile([0.01, 0.01, -0.01, -0.01], n_days // 4)
    rets = pd.DataFrame({"FOND_A": r_a, "FOND_B": r_b}, index=_dates(n_days))
    enb = effective_number_of_bets(rets)
    assert 1.0 <= enb <= 2.0 + 1e-9


# --- MCTR (riskbidrag) -----------------------------------------------------------


def test_risk_contributions_sum_to_one():
    n_days = 40
    r_a = np.tile([0.02, -0.02], n_days // 2)
    r_b = np.tile([0.01, 0.01, -0.01, -0.01], n_days // 4)
    r_c = np.tile([0.015, -0.005, -0.015, 0.005], n_days // 4)
    rets = pd.DataFrame({"FOND_A": r_a, "FOND_B": r_b, "FOND_C": r_c}, index=_dates(n_days))
    weights = pd.Series({"FOND_A": 0.5, "FOND_B": 0.3, "FOND_C": 0.2})
    contrib = risk_contributions(rets, weights)
    assert contrib.sum() == pytest.approx(1.0, rel=1e-9)


def test_risk_contributions_uncorrelated_matches_analytic_variance_share():
    """Okorrelerade tillgångar: bidragᵢ = wᵢ²σᵢ² / Σⱼ wⱼ²σⱼ² (ingen kovariansterm)."""
    n_days = 40
    a, b = 0.02, 0.01
    r_a = np.tile([a, -a], n_days // 2)
    r_b = np.tile([b, b, -b, -b], n_days // 4)
    rets = pd.DataFrame({"FOND_A": r_a, "FOND_B": r_b}, index=_dates(n_days))
    weights = pd.Series({"FOND_A": 0.5, "FOND_B": 0.5})

    sigma_a = float(rets["FOND_A"].std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
    sigma_b = float(rets["FOND_B"].std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
    var_a = (0.5 * sigma_a) ** 2
    var_b = (0.5 * sigma_b) ** 2
    expected_a = var_a / (var_a + var_b)
    expected_b = var_b / (var_a + var_b)

    contrib = risk_contributions(rets, weights)
    assert contrib["FOND_A"] == pytest.approx(expected_a, rel=1e-9)
    assert contrib["FOND_B"] == pytest.approx(expected_b, rel=1e-9)


# --- End-to-end via compute_diversification_window -------------------------------


def _synthetic_bidata(
    rets: pd.DataFrame, weights: pd.Series
) -> tuple[BIData, pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    """BIData + prismatris för en dagligt ombalanserad portfölj av SEK-fonder."""
    dates = rets.index
    prices = 100.0 * (1.0 + rets).cumprod()
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
            "ISIN": [f"ISIN_{k}" for k in weights.index],
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


def test_compute_diversification_window_end_to_end_matches_direct_calls():
    n_days = 40
    a, b = 0.02, 0.01
    r_a = np.tile([a, -a], n_days // 2)
    r_b = np.tile([b, b, -b, -b], n_days // 4)
    rets = pd.DataFrame({"FOND_A": r_a, "FOND_B": r_b}, index=_dates(n_days))
    weights_in = pd.Series({"FOND_A": 0.5, "FOND_B": 0.5})
    data, prices, start, end = _synthetic_bidata(rets, weights_in)

    risk = compute_portfolio_risk_window(data, prices, "T", "Since_Start", start, end)
    div = compute_diversification_window(data, prices, risk)

    assert div.portfolio == "T"
    assert div.period == "Since_Start"
    assert div.dr == pytest.approx(risk.summed_risk / risk.portfolio_risk, rel=1e-9)
    assert div.dr == pytest.approx(1.0 / (1.0 - risk.risk_reduction), rel=1e-9)
    assert div.n == 2
    assert 1.0 <= div.enb <= 2.0 + 1e-9

    contrib_sum = sum(r.risk_contribution for r in div.contributions)
    weight_sum = sum(r.weight for r in div.contributions)
    assert contrib_sum == pytest.approx(1.0, rel=1e-9)
    assert weight_sum == pytest.approx(1.0, rel=1e-9)
    assert {r.instrument for r in div.contributions} == {"FOND_A", "FOND_B"}
    # Sorterat fallande på riskbidrag.
    assert [r.risk_contribution for r in div.contributions] == sorted(
        (r.risk_contribution for r in div.contributions), reverse=True
    )


def test_compute_diversification_window_excludes_same_instrument_as_risk():
    n_days = 40
    a, b = 0.02, 0.01
    r_a = np.tile([a, -a], n_days // 2)
    r_b = np.tile([b, b, -b, -b], n_days // 4)
    rets = pd.DataFrame({"FOND_A": r_a, "FOND_B": r_b}, index=_dates(n_days))
    weights_in = pd.Series({"FOND_A": 0.5, "FOND_B": 0.5})
    data, prices, start, end = _synthetic_bidata(rets, weights_in)
    prices.loc[prices.index[: n_days // 2], "FOND_B"] = np.nan

    risk = compute_portfolio_risk_window(data, prices, "T", "Since_Start", start, end)
    div = compute_diversification_window(data, prices, risk)

    assert risk.excluded == ["FOND_B"]
    assert div.n == 1
    assert div.contributions[0].instrument == "FOND_A"
    assert div.contributions[0].risk_contribution == pytest.approx(1.0, rel=1e-9)
    assert div.contributions[0].weight == pytest.approx(1.0)
    assert div.enb == pytest.approx(1.0, rel=1e-9)
