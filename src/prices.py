"""Market price download and transformation."""

from __future__ import annotations

import logging
import os
import time
from importlib.util import find_spec
from pathlib import Path

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

CACHE_PATH = Path("data") / "cache_prices.parquet"
_PARQUET_WARNED_MISSING_ENGINE = False
_PARQUET_ENGINE_AVAILABLE: bool | None = None


def _extract_close(raw: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=tickers, dtype=float)

    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" not in raw.columns.get_level_values(0):
            raise ValueError("Yahoo response did not contain 'Close'")
        out = raw["Close"].copy()
    else:
        if "Close" in raw.columns:
            out = raw[["Close"]].copy()
            if len(tickers) == 1:
                out.columns = [tickers[0]]
        else:
            out = raw.copy()
            if len(tickers) == 1 and out.shape[1] == 1:
                out.columns = [tickers[0]]

    for ticker in tickers:
        if ticker not in out.columns:
            out[ticker] = pd.NA

    out.index = pd.to_datetime(out.index)
    out = out.sort_index()
    out = out[tickers]
    return out.astype(float)


def _read_cache(cache_path: Path) -> pd.DataFrame:
    if not cache_path.exists():
        return pd.DataFrame()
    try:
        cached = pd.read_parquet(cache_path)
    except Exception as exc:
        logger.warning("Could not read parquet cache (%s), ignoring cache: %s", cache_path, exc)
        return pd.DataFrame()
    if cached.empty:
        return cached
    cached.index = pd.to_datetime(cached.index)
    return cached.sort_index()


def _write_cache(cache_path: Path, df: pd.DataFrame) -> None:
    global _PARQUET_WARNED_MISSING_ENGINE, _PARQUET_ENGINE_AVAILABLE

    if _PARQUET_ENGINE_AVAILABLE is None:
        _PARQUET_ENGINE_AVAILABLE = bool(find_spec("pyarrow") or find_spec("fastparquet"))
    if not _PARQUET_ENGINE_AVAILABLE:
        if not _PARQUET_WARNED_MISSING_ENGINE:
            logger.warning(
                "Parquet cache disabled: missing pyarrow/fastparquet; skipping cache write for this run."
            )
            _PARQUET_WARNED_MISSING_ENGINE = True
        return

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(cache_path)
    except Exception as exc:
        logger.warning("Could not write parquet cache (%s): %s", cache_path, exc)


def fetch_prices_yahoo(
    tickers: list[str],
    start_date: pd.Timestamp | str,
    end_date: pd.Timestamp | str | None = None,
    forward_fill: bool = True,
    cache_path: Path = CACHE_PATH,
) -> pd.DataFrame:
    """Fetch close prices with batch download, retry, cache and coverage checks."""
    requested_count = len(tickers)
    clean = sorted({str(t).strip() for t in tickers if str(t).strip()})
    if not clean:
        return pd.DataFrame()

    start_ts = pd.Timestamp(start_date).normalize()
    if end_date is None:
        requested_end = pd.Timestamp.today().normalize() - pd.Timedelta(days=1)
    else:
        requested_end = pd.Timestamp(end_date).normalize()
    end_exclusive = requested_end + pd.Timedelta(days=1)

    cached = _read_cache(cache_path)
    cache_hit = not cached.empty
    has_all_cols = cache_hit and all(t in cached.columns for t in clean)
    incremental = False

    fetch_needed = True
    fetch_start = start_ts
    if has_all_cols:
        last_cached = cached.index.max()
        if pd.notna(last_cached):
            fetch_start = max(start_ts, pd.Timestamp(last_cached).normalize() + pd.Timedelta(days=1))
        fetch_needed = fetch_start < end_exclusive
        incremental = fetch_needed

    downloaded = pd.DataFrame()
    if fetch_needed:
        query_tickers = " ".join(clean)
        last_error: Exception | None = None
        for attempt, sleep_s in enumerate((2, 4, 6), start=1):
            try:
                raw = yf.download(
                    tickers=query_tickers,
                    start=fetch_start.date(),
                    end=end_exclusive.date(),
                    auto_adjust=True,
                    progress=False,
                    threads=False,
                )
                downloaded = _extract_close(raw, clean)
                if not downloaded.empty:
                    break
                last_error = ValueError("Yahoo returned empty result")
            except Exception as exc:
                last_error = exc
            if attempt < 3:
                time.sleep(sleep_s)
        if downloaded.empty:
            raise ValueError(f"Failed to download prices after retries: {last_error}")

    if cache_hit:
        merged = cached.copy()
    else:
        merged = pd.DataFrame()
    for ticker in clean:
        if ticker not in merged.columns:
            merged[ticker] = pd.NA
    if not downloaded.empty:
        for ticker in clean:
            if ticker not in downloaded.columns:
                downloaded[ticker] = pd.NA
        merged = pd.concat([merged, downloaded[clean]], axis=0)
    if merged.empty:
        raise ValueError("Price fetch returned empty dataset")

    merged.index = pd.to_datetime(merged.index)
    merged = merged[~merged.index.duplicated(keep="last")]
    merged = merged.sort_index()
    if forward_fill:
        merged[clean] = merged[clean].ffill()

    prices = merged.loc[(merged.index >= start_ts) & (merged.index < end_exclusive), clean].copy()
    if prices.empty:
        raise ValueError("Price fetch resulted in empty period after slicing")
    if not prices.index.is_monotonic_increasing:
        prices = prices.sort_index()

    strict_coverage = os.getenv("PRICE_COVERAGE_STRICT", "1") != "0"
    coverage_rows: list[dict[str, object]] = []
    for ticker in clean:
        s = prices[ticker]
        first_valid = s.first_valid_index()
        if first_valid is None:
            raise ValueError(f"No price data for ticker {ticker}")
        first_valid = pd.Timestamp(first_valid)
        window_start = max(start_ts, first_valid)
        window = s.loc[(s.index >= window_start) & (s.index <= requested_end)]
        if window.empty:
            raise ValueError(
                f"No coverage window for ticker {ticker} "
                f"(first_valid={first_valid.date().isoformat()}, window_start={window_start.date().isoformat()})"
            )
        coverage_rows.append(
            {
                "ticker": ticker,
                "nan_share": float(window.isna().mean()),
                "first_valid": first_valid,
                "window_start": window_start,
            }
        )

    cov_df = pd.DataFrame(coverage_rows).sort_values("nan_share", ascending=False)
    warn_df = cov_df[cov_df["nan_share"] > 0.05]
    if not warn_df.empty:
        top_n = warn_df.head(10)
        logger.warning(
            "Low price coverage: %s ticker(s) above 5%% NaN; showing worst %s",
            len(warn_df),
            len(top_n),
        )
        for _, row in top_n.iterrows():
            logger.warning(
                "Coverage ticker=%s nan_share=%.4f first_valid=%s window_start=%s",
                row["ticker"],
                float(row["nan_share"]),
                pd.Timestamp(row["first_valid"]).date().isoformat(),
                pd.Timestamp(row["window_start"]).date().isoformat(),
            )

    fail_df = cov_df[cov_df["nan_share"] > 0.25]
    if not fail_df.empty:
        details = "; ".join(
            [
                (
                    f"{row['ticker']}:nan_share={float(row['nan_share']):.4f},"
                    f"first_valid={pd.Timestamp(row['first_valid']).date().isoformat()},"
                    f"window_start={pd.Timestamp(row['window_start']).date().isoformat()}"
                )
                for _, row in fail_df.iterrows()
            ]
        )
        if strict_coverage:
            raise ValueError(f"Too much missing price data (>25% NaN): {details}")
        logger.warning("Coverage strict mode disabled (PRICE_COVERAGE_STRICT=0). %s", details)

    _write_cache(cache_path, merged)
    logger.info(
        "Price fetch tickers=%s start=%s end=%s rows=%s cache=%s incremental=%s",
        requested_count,
        start_ts.date().isoformat(),
        requested_end.date().isoformat(),
        len(prices),
        "hit" if cache_hit else "miss",
        incremental,
    )
    return prices


def download_adj_close(
    tickers: list[str],
    start_date: pd.Timestamp | str,
    end_date: pd.Timestamp | str | None = None,
    forward_fill: bool = True,
    fx_tickers: list[str] | None = None,
) -> pd.DataFrame:
    """Download daily adjusted close-equivalent prices from Yahoo Finance."""
    logger.info(
        "download_adj_close received %d asset tickers and %d FX tickers",
        len(tickers),
        len(fx_tickers or []),
    )
    prices = fetch_prices_yahoo(
        tickers=tickers,
        start_date=start_date,
        end_date=end_date,
        forward_fill=forward_fill,
    )

    clean = sorted({str(t).strip() for t in tickers if str(t).strip()})
    missing = [t for t in clean if t not in prices.columns or prices[t].dropna().empty]
    if missing:
        raise ValueError(f"Missing Yahoo data for ticker(s): {missing}")
    for fx in sorted(set(fx_tickers or [])):
        if fx not in prices.columns:
            raise ValueError(f"FX ticker requested but missing from downloaded prices: {fx}")

    return prices


def returns_from_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Compute arithmetic daily returns with first value set to 0."""
    if prices.empty:
        return prices.copy()
    rets = prices.sort_index().pct_change()
    return rets.fillna(0.0)
