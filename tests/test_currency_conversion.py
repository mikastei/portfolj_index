import pandas as pd
import pytest

from src.portfolio import _prices_to_base


def _mapping(rows):
    return pd.DataFrame(rows, columns=["Yahoo_Ticker", "Price_Currency"])


def test_same_currency_passes_through_unchanged():
    idx = pd.to_datetime(["2026-06-01", "2026-06-02"])
    prices = pd.DataFrame({"SEK.ST": [100.0, 101.0]}, index=idx)
    mapping = _mapping([{"Yahoo_Ticker": "SEK.ST", "Price_Currency": "SEK"}])

    out = _prices_to_base(prices, ["SEK.ST"], mapping, "SEK")

    pd.testing.assert_series_equal(out["SEK.ST"], prices["SEK.ST"], check_names=False)


def test_foreign_currency_multiplied_by_fx_rate():
    idx = pd.to_datetime(["2026-06-01", "2026-06-02"])
    prices = pd.DataFrame(
        {"AAPL": [100.0, 102.0], "USDSEK=X": [10.0, 10.5]},
        index=idx,
    )
    mapping = _mapping([{"Yahoo_Ticker": "AAPL", "Price_Currency": "USD"}])

    out = _prices_to_base(prices, ["AAPL"], mapping, "SEK")

    assert out["AAPL"].tolist() == pytest.approx([1000.0, 1071.0])


def test_missing_fx_series_raises():
    idx = pd.to_datetime(["2026-06-01"])
    prices = pd.DataFrame({"AAPL": [100.0]}, index=idx)
    mapping = _mapping([{"Yahoo_Ticker": "AAPL", "Price_Currency": "USD"}])

    with pytest.raises(ValueError, match="Missing FX series"):
        _prices_to_base(prices, ["AAPL"], mapping, "SEK")


def test_empty_price_currency_falls_back_to_base_currency():
    idx = pd.to_datetime(["2026-06-01", "2026-06-02"])
    prices = pd.DataFrame({"VOLV-B.ST": [200.0, 201.0]}, index=idx)
    mapping = _mapping([{"Yahoo_Ticker": "VOLV-B.ST", "Price_Currency": ""}])

    out = _prices_to_base(prices, ["VOLV-B.ST"], mapping, "SEK")

    pd.testing.assert_series_equal(out["VOLV-B.ST"], prices["VOLV-B.ST"], check_names=False)
