import pandas as pd
import pytest

from src import prices as prices_mod
from src.prices import fetch_prices_yahoo


def test_weekend_rows_dropped_from_calendar_and_cache(monkeypatch, tmp_path):
    # 2026-05-01 = fredag, 05-02 = lördag, 05-03 = söndag, 05-04 = måndag.
    idx = pd.to_datetime(["2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04"])
    raw = pd.DataFrame({"Close": [100.0, 93.0, 93.0, 101.0]}, index=idx)
    monkeypatch.setattr(prices_mod.yf, "download", lambda **kwargs: raw.copy())
    cache_path = tmp_path / "cache.parquet"

    out = fetch_prices_yahoo(["AAA"], "2026-05-01", "2026-05-04", cache_path=cache_path)

    assert (out.index.dayofweek < 5).all()
    assert list(out.index) == list(pd.to_datetime(["2026-05-01", "2026-05-04"]))
    cached = pd.read_parquet(cache_path)
    assert (pd.to_datetime(cached.index).dayofweek < 5).all()


def test_cache_with_empty_ticker_column_is_refetched(monkeypatch, tmp_path):
    idx = pd.to_datetime(["2026-05-04", "2026-05-05"])
    cache_path = tmp_path / "cache.parquet"
    stale = pd.DataFrame({"AAA": [100.0, 101.0], "BBB": [float("nan")] * 2}, index=idx)
    stale.to_parquet(cache_path)

    raw = pd.DataFrame(
        [[100.0, 50.0], [101.0, 51.0]],
        index=idx,
        columns=pd.MultiIndex.from_product([["Close"], ["AAA", "BBB"]]),
    )
    calls = []

    def fake_download(**kwargs):
        calls.append(kwargs)
        return raw.copy()

    monkeypatch.setattr(prices_mod.yf, "download", fake_download)

    out = fetch_prices_yahoo(["AAA", "BBB"], "2026-05-04", "2026-05-05", cache_path=cache_path)

    assert calls, "expected a full refetch when a cached column has no data"
    assert not out["BBB"].dropna().empty


def test_cache_refetched_when_requested_start_precedes_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / "cache.parquet"
    cached_idx = pd.to_datetime(["2026-05-04", "2026-05-05"])
    pd.DataFrame({"AAA": [100.0, 101.0]}, index=cached_idx).to_parquet(cache_path)

    full_idx = pd.to_datetime(["2026-04-01", "2026-04-02", "2026-05-04", "2026-05-05"])
    raw = pd.DataFrame({"Close": [95.0, 96.0, 100.0, 101.0]}, index=full_idx)
    monkeypatch.setattr(prices_mod.yf, "download", lambda **kwargs: raw.copy())

    out = fetch_prices_yahoo(["AAA"], "2026-04-01", "2026-05-05", cache_path=cache_path)

    assert out.index.min() == pd.Timestamp("2026-04-01")


def _sparse_price_frame():
    # 8 vardagar (2026-06-01 mån -> 2026-06-10 ons). >25% NaN i fönstret för AAA.
    idx = pd.to_datetime(
        ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05", "2026-06-08", "2026-06-09", "2026-06-10"]
    )
    return idx, pd.DataFrame(
        {"Close": [100.0, float("nan"), float("nan"), 101.0, float("nan"), 102.0, 103.0, 104.0]},
        index=idx,
    )


def test_price_coverage_strict_by_default_raises_on_too_many_gaps(monkeypatch, tmp_path):
    idx, raw = _sparse_price_frame()
    monkeypatch.setattr(prices_mod.yf, "download", lambda **kwargs: raw.copy())
    monkeypatch.delenv("PRICE_COVERAGE_STRICT", raising=False)
    cache_path = tmp_path / "cache.parquet"

    with pytest.raises(ValueError, match="Too much missing price data"):
        fetch_prices_yahoo(
            ["AAA"], idx.min(), idx.max(), forward_fill=False, cache_path=cache_path
        )


def test_price_coverage_strict_disabled_warns_instead_of_raising(monkeypatch, tmp_path):
    idx, raw = _sparse_price_frame()
    monkeypatch.setattr(prices_mod.yf, "download", lambda **kwargs: raw.copy())
    monkeypatch.setenv("PRICE_COVERAGE_STRICT", "0")
    cache_path = tmp_path / "cache.parquet"

    out = fetch_prices_yahoo(
        ["AAA"], idx.min(), idx.max(), forward_fill=False, cache_path=cache_path
    )

    assert out["AAA"].isna().sum() == 3


def test_price_coverage_strict_raises_with_forward_fill_on_real_gap(monkeypatch, tmp_path):
    # Regression för [AX]: med produktionsdefault forward_fill=True fylldes interna
    # NaN-luckor igen *innan* täckningen mättes, så den strikta kontrollen kunde i
    # praktiken aldrig lösa ut. Täckningen ska nu mätas på rådata före ffill och
    # därför fortfarande lösa ut på en riktig prislucka.
    idx, raw = _sparse_price_frame()
    monkeypatch.setattr(prices_mod.yf, "download", lambda **kwargs: raw.copy())
    monkeypatch.delenv("PRICE_COVERAGE_STRICT", raising=False)
    cache_path = tmp_path / "cache.parquet"

    with pytest.raises(ValueError, match="Too much missing price data"):
        fetch_prices_yahoo(
            ["AAA"], idx.min(), idx.max(), forward_fill=True, cache_path=cache_path
        )


def test_forward_fill_still_applied_to_returned_series(monkeypatch, tmp_path):
    # Täckningen mäts på rådata, men den returnerade serien ska fortfarande vara
    # forward-fill:ad som förut ([AX] ändrar bara var luckan *mäts*, inte utdatan).
    idx, raw = _sparse_price_frame()
    monkeypatch.setattr(prices_mod.yf, "download", lambda **kwargs: raw.copy())
    monkeypatch.setenv("PRICE_COVERAGE_STRICT", "0")  # annars skulle luckan lösa ut
    cache_path = tmp_path / "cache.parquet"

    out = fetch_prices_yahoo(
        ["AAA"], idx.min(), idx.max(), forward_fill=True, cache_path=cache_path
    )

    assert out["AAA"].isna().sum() == 0
