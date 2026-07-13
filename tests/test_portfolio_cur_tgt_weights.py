"""Tester för CUR/TGT-viktningen ([AL1]).

Fonder som saknar pris innan de startade ska exkluderas de dagarna och deras vikt
fördelas om över de fonder som har pris – inte tyst sättas till 0 % vid full vikt.
"""

import numpy as np
import pandas as pd
import pytest

from src.portfolio import _portfolio_returns_from_weights


def test_full_history_matches_fixed_weighted_sum():
    # Ingen fond saknar historik → ska motsvara vanlig fastviktad avkastning.
    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    px = pd.DataFrame({"A": [100.0, 110.0, 121.0], "B": [200.0, 200.0, 210.0]}, index=dates)
    w = pd.Series({"A": 0.5, "B": 0.5})

    port = _portfolio_returns_from_weights(px, w)

    assert port.iloc[0] == pytest.approx(0.0)  # basdag
    assert port.iloc[1] == pytest.approx(0.5 * 0.10 + 0.5 * 0.0)
    assert port.iloc[2] == pytest.approx(0.5 * 0.10 + 0.5 * 0.05)


def test_late_starting_fund_is_reweighted_not_diluted():
    # B saknar pris de två första dagarna och startar dag 3.
    dates = pd.date_range("2026-01-01", periods=4, freq="D")
    px = pd.DataFrame(
        {
            "A": [100.0, 110.0, 121.0, 133.1],       # +10 % varje dag
            "B": [np.nan, np.nan, 50.0, 55.0],        # start dag 3, +10 % dag 4
        },
        index=dates,
    )
    w = pd.Series({"A": 0.5, "B": 0.5})

    port = _portfolio_returns_from_weights(px, w, portfolio_name="TEST", label="CUR")

    # Dag 0: basdag → 0.
    assert port.iloc[0] == pytest.approx(0.0)
    # Dag 1: B frånvarande → A får hela vikten, inte utspädd till 0,05.
    assert port.iloc[1] == pytest.approx(0.10)
    # Dag 2: B:s första prisdag räknas som basdag (0 %); 0,5/0,5-viktning.
    assert port.iloc[2] == pytest.approx(0.5 * 0.10 + 0.5 * 0.0)
    # Dag 3: båda fonderna aktiva och stiger 10 %.
    assert port.iloc[3] == pytest.approx(0.10)


def test_fund_without_any_prices_is_dropped_from_weighting():
    # C saknar pris helt → ska exkluderas ur hela serien, A+B bär vikten.
    dates = pd.date_range("2026-01-01", periods=2, freq="D")
    px = pd.DataFrame(
        {
            "A": [100.0, 110.0],
            "B": [100.0, 105.0],
            "C": [np.nan, np.nan],
        },
        index=dates,
    )
    w = pd.Series({"A": 0.4, "B": 0.4, "C": 0.2})

    port = _portfolio_returns_from_weights(px, w, portfolio_name="TEST", label="TGT")

    # C:s vikt fördelas om över A och B (0,5/0,5 efter normering).
    assert port.iloc[0] == pytest.approx(0.0)
    assert port.iloc[1] == pytest.approx(0.5 * 0.10 + 0.5 * 0.05)


def test_late_start_logs_excluded_span(caplog):
    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    px = pd.DataFrame(
        {"A": [100.0, 110.0, 121.0], "B": [np.nan, np.nan, 50.0]},
        index=dates,
    )
    w = pd.Series({"A": 0.5, "B": 0.5})

    with caplog.at_level("WARNING"):
        _portfolio_returns_from_weights(px, w, portfolio_name="TEST", label="CUR")

    assert any("fond=B" in rec.message and "saknar pris före start" in rec.message
               for rec in caplog.records)


def test_no_weighted_assets_raises():
    dates = pd.date_range("2026-01-01", periods=2, freq="D")
    px = pd.DataFrame({"A": [100.0, 110.0]}, index=dates)
    w = pd.Series({"X": 1.0})

    with pytest.raises(ValueError, match="No weighted assets"):
        _portfolio_returns_from_weights(px, w)
