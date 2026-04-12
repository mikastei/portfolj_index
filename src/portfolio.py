"""Portfolio and benchmark series construction."""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .prices import returns_from_prices

COL_AFFARSDAG = "Aff\u00e4rsdag"
TXN_KOPT = "K\u00d6PT"
TXN_SALT = "S\u00c5LT"
COL_BELOPP = "Belopp"
COL_PORTFOLJ = "Portf\u00f6lj"
COL_VALUTA = "Valuta"
COL_REFX = "Referensvalutakurs"
COL_VAX = "V\u00e4xlingskurs"
COL_PRICE_CCY = "Price_Currency"
COL_EFFECTIVE_DATE = "_Effective_Date"

logger = logging.getLogger(__name__)
DEBUG_ENABLED = os.getenv("PORTFOLIO_DEBUG") == "1"
STRICT_VALUATION = os.getenv("PORTFOLIO_STRICT") == "1"
STRICT_EXTREME_RET = os.getenv("STRICT_EXTREME_RET", "1") != "0"


def slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value).upper())
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "UNKNOWN"


def _build_index(returns: pd.Series, initial_index_value: float) -> pd.Series:
    return float(initial_index_value) * (1.0 + returns.fillna(0.0)).cumprod()


def _drawdown(index_series: pd.Series) -> pd.Series:
    running_max = index_series.cummax()
    return index_series / running_max - 1.0


def _series_frame(returns: pd.Series, initial_index_value: float) -> pd.DataFrame:
    returns = returns.fillna(0.0).copy()
    if not returns.empty:
        returns.iloc[0] = 0.0
    idx = _build_index(returns, initial_index_value)
    dd = _drawdown(idx)
    out = pd.DataFrame({"RET": returns, "IDX": idx, "DD": dd})
    out.index = pd.to_datetime(out.index)
    out.index.name = "Date"
    return out


def required_tickers(
    transactions: pd.DataFrame,
    mapping: pd.DataFrame,
    benchmarks: pd.DataFrame,
    fondertabell: pd.DataFrame,
    base_currency: str = "SEK",
) -> dict[str, list[str]]:
    """Collect all Yahoo tickers needed by source."""
    txn_isins = sorted({x for x in transactions["ISIN"].dropna().astype(str).str.strip() if x})
    map_lookup = mapping.copy()
    map_lookup["ISIN"] = map_lookup["ISIN"].astype(str).str.strip()
    isin_to_ticker = map_lookup.set_index("ISIN")["Yahoo_Ticker"].to_dict()

    missing_isin = [isin for isin in txn_isins if isin not in isin_to_ticker]
    if missing_isin:
        raise ValueError(f"Missing Mapping for ISIN(s): {missing_isin}")

    real_tickers = sorted(
        {str(isin_to_ticker[isin]).strip() for isin in txn_isins if str(isin_to_ticker[isin]).strip()}
    )
    benchmark_tickers = (
        benchmarks["Yahoo_Ticker"]
        .dropna()
        .astype(str)
        .str.strip()
        .loc[lambda s: s != ""]
        .unique()
        .tolist()
    )
    bm_tickers = sorted(set(benchmark_tickers))
    model_tickers = sorted({str(x).strip() for x in fondertabell["Yahoo"].dropna() if str(x).strip()})
    base_ccy = str(base_currency).upper().strip()
    asset_tickers = sorted(set(real_tickers) | set(model_tickers))
    fx_tickers = set(_fx_tickers_for_assets(asset_tickers, mapping, base_ccy))

    for fx in discover_fx_tickers(mapping, benchmarks, base_ccy):
        fx_tickers.add(fx)

    fx_tickers_list = sorted(fx_tickers)
    all_tickers = sorted(set(asset_tickers) | set(bm_tickers) | set(fx_tickers_list))
    logger.info("Benchmark tickers discovered: %s", bm_tickers)

    return {
        "real": real_tickers,
        "benchmarks": bm_tickers,
        "model": model_tickers,
        "fx": fx_tickers_list,
        "all": all_tickers,
    }


def discover_fx_tickers(
    mapping: pd.DataFrame,
    benchmarks: pd.DataFrame,
    base_currency: str = "SEK",
) -> list[str]:
    base_ccy = str(base_currency).upper().strip()
    mapping_ccy: set[str] = set()
    if COL_PRICE_CCY in mapping.columns:
        mapping_ccy = {
            str(x).upper().strip()
            for x in mapping[COL_PRICE_CCY].dropna()
            if str(x).strip()
        }
    benchmark_ccy: set[str] = set()
    if COL_PRICE_CCY in benchmarks.columns:
        benchmark_ccy = {
            str(x).upper().strip()
            for x in benchmarks[COL_PRICE_CCY].dropna()
            if str(x).strip()
        }
    fx = {f"{ccy}{base_ccy}=X" for ccy in (mapping_ccy | benchmark_ccy) if ccy != base_ccy}
    return sorted(fx)


@dataclass
class EngineInputs:
    transactions: pd.DataFrame
    mapping: pd.DataFrame
    portfolio_metadata: pd.DataFrame
    benchmarks: pd.DataFrame
    fondertabell: pd.DataFrame
    prices: pd.DataFrame
    base_currency: str = "SEK"


def _portfolio_meta_row(portfolio_metadata: pd.DataFrame) -> pd.Series:
    if portfolio_metadata.empty:
        raise ValueError("Portfolio_Metadata is empty")
    row = portfolio_metadata.iloc[0]
    if pd.isna(row["Portfolio_Name"]) or pd.isna(row["Index_Start_Date"]) or pd.isna(
        row["Initial_Index_Value"]
    ):
        raise ValueError("Portfolio_Metadata has null required values")
    return row


def _portfolio_name_col(df: pd.DataFrame) -> str | None:
    for col in ("Portfolio_Name", COL_PORTFOLJ, "Portfolj", "Portfolio"):
        if col in df.columns:
            return col
    return None


def _first_unique_nonempty(values: pd.Series) -> object:
    cleaned = []
    for value in values.dropna():
        text = str(value).strip()
        if text and text.upper() not in {"NAN", "NONE"}:
            cleaned.append(text)
    unique_values = list(dict.fromkeys(cleaned))
    if len(unique_values) == 1:
        return unique_values[0]
    return None


def _instrument_metadata_by_ticker(mapping: pd.DataFrame) -> pd.DataFrame:
    if "Yahoo_Ticker" not in mapping.columns:
        return pd.DataFrame(
            columns=[
                "Yahoo_Ticker",
                "ISIN",
                "Display_Name",
                COL_PRICE_CCY,
                "Instrument_Type",
                "Category",
            ]
        )

    map_df = mapping.copy()
    map_df["Yahoo_Ticker"] = map_df["Yahoo_Ticker"].fillna("").astype(str).str.strip()
    map_df = map_df[map_df["Yahoo_Ticker"] != ""]
    if map_df.empty:
        return pd.DataFrame(
            columns=[
                "Yahoo_Ticker",
                "ISIN",
                "Display_Name",
                COL_PRICE_CCY,
                "Instrument_Type",
                "Category",
            ]
        )

    if "Name" in map_df.columns:
        map_df["Display_Name"] = map_df["Name"].fillna("").astype(str).str.strip()
    else:
        map_df["Display_Name"] = ""
    map_df["Display_Name"] = map_df["Display_Name"].where(map_df["Display_Name"] != "", map_df["Yahoo_Ticker"])

    if COL_PRICE_CCY in map_df.columns:
        map_df[COL_PRICE_CCY] = map_df[COL_PRICE_CCY].fillna("").astype(str).str.upper().str.strip()
    else:
        map_df[COL_PRICE_CCY] = ""

    for column in ("ISIN", "Instrument_Type", "Category"):
        if column not in map_df.columns:
            map_df[column] = ""
        map_df[column] = map_df[column].fillna("").astype(str).str.strip()

    grouped = (
        map_df.groupby("Yahoo_Ticker", as_index=False)
        .agg(
            ISIN=("ISIN", _first_unique_nonempty),
            Display_Name=("Display_Name", _first_unique_nonempty),
            Price_Currency=(COL_PRICE_CCY, _first_unique_nonempty),
            Instrument_Type=("Instrument_Type", _first_unique_nonempty),
            Category=("Category", _first_unique_nonempty),
        )
    )
    grouped["Display_Name"] = grouped["Display_Name"].where(
        grouped["Display_Name"].notna() & (grouped["Display_Name"].astype(str).str.strip() != ""),
        grouped["Yahoo_Ticker"],
    )
    return grouped


def _portfolio_rows(portfolio_metadata: pd.DataFrame) -> list[pd.Series]:
    if portfolio_metadata.empty:
        raise ValueError("Portfolio_Metadata is empty")
    required = ["Portfolio_Name", "Index_Start_Date", "Initial_Index_Value"]
    missing = [c for c in required if c not in portfolio_metadata.columns]
    if missing:
        raise ValueError(f"Portfolio_Metadata is missing required columns: {missing}")
    rows = portfolio_metadata.dropna(subset=required)
    if rows.empty:
        raise ValueError("Portfolio_Metadata has no valid rows")
    return [row for _, row in rows.iterrows()]


def _weights_from_fonder(
    fondertabell: pd.DataFrame,
    weight_col: str,
    portfolio_name: str | None = None,
) -> pd.Series:
    df = fondertabell[["Yahoo", weight_col]].copy()
    df["Yahoo"] = df["Yahoo"].astype(str).str.strip()
    df = df[df["Yahoo"] != ""]
    df[weight_col] = pd.to_numeric(df[weight_col], errors="coerce").fillna(0.0)
    grouped = df.groupby("Yahoo", as_index=True)[weight_col].sum().fillna(0.0)
    positive = grouped[grouped > 0]
    if positive.empty:
        raise ValueError(f"Portfolio has no weights (portfolio={portfolio_name}, column={weight_col})")
    total = float(positive.sum())
    if abs(total - 1.0) >= 1e-6:
        raise ValueError(
            f"Weights must sum to 1.0 within tolerance (portfolio={portfolio_name}, column={weight_col}, sum={total:.12f})"
        )
    # Safety-normalize even when already validated to 1.0.
    return positive / total


def _portfolio_returns_from_weights(asset_returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    cols = [c for c in weights.index if c in asset_returns.columns]
    if not cols:
        raise ValueError("No weighted assets are present in downloaded Yahoo price data")
    w = weights.loc[cols]
    w = w / w.sum()
    return asset_returns[cols].mul(w, axis=1).sum(axis=1)


def _currency_map_from_mapping(
    mapping: pd.DataFrame,
    tickers: list[str],
    base_currency: str,
) -> dict[str, str]:
    base_ccy = str(base_currency).upper().strip()
    mp = mapping.copy()
    mp["Yahoo_Ticker"] = mp["Yahoo_Ticker"].astype(str).str.strip()
    mp[COL_PRICE_CCY] = (
        mp[COL_PRICE_CCY].astype(str).str.upper().str.strip().replace({"": base_ccy, "NAN": base_ccy, "NONE": base_ccy})
    )
    ccy_map = mp.groupby("Yahoo_Ticker", as_index=True)[COL_PRICE_CCY].first().to_dict()
    out: dict[str, str] = {}
    for t in tickers:
        out[t] = ccy_map.get(t, base_ccy)
    return out


def _fx_tickers_for_assets(
    asset_tickers: list[str],
    mapping: pd.DataFrame,
    base_currency: str,
) -> list[str]:
    base_ccy = str(base_currency).upper().strip()
    ccy_map = _currency_map_from_mapping(mapping, asset_tickers, base_ccy)
    fx = {
        f"{ccy}{base_ccy}=X"
        for ccy in ccy_map.values()
        if ccy and ccy != base_ccy
    }
    return sorted(fx)


def _prices_to_base(
    prices: pd.DataFrame,
    asset_tickers: list[str],
    mapping: pd.DataFrame,
    base_currency: str,
) -> pd.DataFrame:
    base_ccy = str(base_currency).upper().strip()
    ccy_map = _currency_map_from_mapping(mapping, asset_tickers, base_ccy)
    out = pd.DataFrame(index=prices.index)
    for ticker in asset_tickers:
        if ticker not in prices.columns:
            continue
        price_local = prices[ticker]
        ccy = ccy_map.get(ticker, base_ccy)
        if ccy == base_ccy:
            out[ticker] = price_local
            continue
        fx_ticker = f"{ccy}{base_ccy}=X"
        if fx_ticker not in prices.columns:
            raise ValueError(f"Missing FX series for currency pair {fx_ticker}")
        fx_rate = prices[fx_ticker]
        price_base = price_local * fx_rate
        missing_base = price_local.notna() & price_base.isna()
        if missing_base.any():
            first_missing = missing_base[missing_base].index[0]
            logger.error(
                "price_base missing while price_local exists: ticker=%s currency=%s expected_fx_ticker=%s first_missing_date=%s",
                ticker,
                ccy,
                fx_ticker,
                pd.Timestamp(first_missing).date().isoformat(),
            )
            raise ValueError(
                f"Missing price_base for ticker={ticker} with currency={ccy} using FX {fx_ticker}"
            )
        out[ticker] = price_base
    return out


def _portfolio_price_frame(
    prices: pd.DataFrame,
    tickers: list[str],
    start_date: pd.Timestamp,
    extra_tickers: list[str] | None = None,
) -> pd.DataFrame:
    cols = [t for t in tickers if t in prices.columns]
    if not cols:
        return pd.DataFrame(index=prices[prices.index >= start_date].index)
    px = prices.loc[prices.index >= start_date, cols].copy()
    if px.empty:
        return px
    # Portfolio calendar should follow its own assets only.
    px = px[px.notna().any(axis=1)]
    if extra_tickers:
        extras = [t for t in extra_tickers if t in prices.columns and t not in px.columns]
        if extras:
            px = px.join(prices.loc[px.index, extras], how="left")
    return px


def _portfolio_price_frame_full_calendar(
    prices: pd.DataFrame,
    tickers: list[str],
    start_date: pd.Timestamp,
    extra_tickers: list[str] | None = None,
) -> pd.DataFrame:
    calendar_index = prices.index[prices.index >= start_date]
    cols = [t for t in tickers if t in prices.columns]
    if extra_tickers:
        cols.extend([t for t in extra_tickers if t in prices.columns and t not in cols])
    if not cols:
        return pd.DataFrame(index=calendar_index)
    return prices.loc[calendar_index, cols].copy()


def _real_categories_for_portfolio(
    transactions: pd.DataFrame,
    mapping: pd.DataFrame,
) -> list[str]:
    tx_isins = sorted({str(x).strip() for x in transactions["ISIN"].dropna() if str(x).strip()})
    if not tx_isins:
        return []

    map_df = mapping.copy()
    map_df["ISIN"] = map_df["ISIN"].astype(str).str.strip()
    map_df["Category"] = map_df["Category"].fillna("").astype(str).str.strip()

    isin_category = map_df.drop_duplicates(subset=["ISIN"]).set_index("ISIN")["Category"].to_dict()
    missing = [isin for isin in tx_isins if not str(isin_category.get(isin, "")).strip()]
    if missing:
        raise ValueError(f"Missing Category for ISIN(s): {missing}")

    return sorted({isin_category[isin] for isin in tx_isins})


def _transactions_for_category(
    transactions: pd.DataFrame,
    mapping: pd.DataFrame,
    category: str,
) -> pd.DataFrame:
    tx = transactions.copy()
    tx["ISIN"] = tx["ISIN"].astype(str).str.strip()

    map_df = mapping.copy()
    map_df["ISIN"] = map_df["ISIN"].astype(str).str.strip()
    map_df["Category"] = map_df["Category"].fillna("").astype(str).str.strip()
    isin_category = map_df.drop_duplicates(subset=["ISIN"]).set_index("ISIN")["Category"].to_dict()
    return tx[tx["ISIN"].map(isin_category) == str(category).strip()].copy()


def _real_category_slug_map(
    transactions: pd.DataFrame,
    mapping: pd.DataFrame,
) -> dict[str, str]:
    slug_map: dict[str, str] = {}
    for category in _real_categories_for_portfolio(transactions, mapping):
        category_slug = slug(category)
        existing = slug_map.get(category_slug)
        if existing is not None and existing != category:
            raise ValueError(
                f"Category slug collision detected: '{existing}' and '{category}' both map to '{category_slug}'"
            )
        slug_map[category_slug] = category
    return slug_map


def _normalize_txn_type(v: object) -> str:
    s = str(v).strip().upper()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^A-Z]", "", s)
    return s


def _txn_sign(v: object) -> float:
    n = _normalize_txn_type(v)
    if n.startswith("K") or n in {"BUY"}:
        return 1.0
    if n.startswith("S") or n in {"SELL"}:
        return -1.0
    return 0.0


def _align_to_price_calendar(tx_dates: pd.Series, price_index: pd.Index) -> pd.Series:
    dates = pd.to_datetime(tx_dates, errors="coerce")
    aligned = pd.Series(pd.NaT, index=dates.index, dtype="datetime64[ns]")
    if dates.empty:
        return aligned

    calendar = pd.DatetimeIndex(price_index).sort_values().unique()
    if calendar.empty:
        return aligned

    valid_dates = dates.dropna()
    if valid_dates.empty:
        return aligned

    positions = calendar.searchsorted(valid_dates.to_numpy())
    in_range = positions < len(calendar)
    if in_range.any():
        matched_index = valid_dates.index[in_range]
        aligned.loc[matched_index] = calendar.take(positions[in_range]).to_numpy()
    return aligned


def _real_position_state(
    transactions: pd.DataFrame,
    mapping: pd.DataFrame,
    prices: pd.DataFrame,
    base_currency: str = "SEK",
    portfolio_name: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.Series, pd.DataFrame]:
    tx = transactions.copy()
    tx[COL_AFFARSDAG] = pd.to_datetime(tx[COL_AFFARSDAG], errors="coerce")
    tx = tx.dropna(subset=[COL_AFFARSDAG, "ISIN", "Antal", "Transaktionstyp"])
    tx["ISIN"] = tx["ISIN"].astype(str).str.strip()
    tx["Antal"] = pd.to_numeric(tx["Antal"], errors="coerce").fillna(0.0)
    tx["Transaktionstyp"] = tx["Transaktionstyp"].astype(str).str.strip().str.upper()
    tx["txn_sign"] = tx["Transaktionstyp"].map(_txn_sign).astype(float)
    tx["signed_qty"] = tx["Antal"] * tx["txn_sign"]
    tx[COL_EFFECTIVE_DATE] = _align_to_price_calendar(tx[COL_AFFARSDAG], prices.index)
    unknown_types = sorted(tx.loc[tx["txn_sign"] == 0, "Transaktionstyp"].dropna().unique())
    if unknown_types:
        logger.warning("Unknown transaction types treated as 0-sign: %s", unknown_types)

    empty_frame = pd.DataFrame(index=prices.index)
    empty_series = pd.Series(dtype=object)
    if tx.empty:
        return tx, empty_frame, empty_frame.copy(), empty_frame.copy(), empty_series, empty_frame.copy()

    map_df = mapping.copy()
    map_df["ISIN"] = map_df["ISIN"].astype(str).str.strip()
    map_df["Yahoo_Ticker"] = map_df["Yahoo_Ticker"].astype(str).str.strip()
    isin_to_ticker_all = map_df.set_index("ISIN")["Yahoo_Ticker"]

    tx["Yahoo_Ticker"] = tx["ISIN"].map(isin_to_ticker_all)
    missing = sorted(tx.loc[tx["Yahoo_Ticker"].isna(), "ISIN"].unique())
    if missing:
        raise ValueError(f"Missing Mapping for ISIN(s): {missing}")

    flows_isin = (
        tx.dropna(subset=[COL_EFFECTIVE_DATE])
        .groupby([COL_EFFECTIVE_DATE, "ISIN"], as_index=False)["signed_qty"]
        .sum()
        .pivot(index=COL_EFFECTIVE_DATE, columns="ISIN", values="signed_qty")
        .fillna(0.0)
        .sort_index()
    )
    shares_isin = flows_isin.cumsum()
    shares_isin = shares_isin.reindex(prices.index).ffill().fillna(0.0)

    isin_to_ticker = tx.dropna(subset=["ISIN", "Yahoo_Ticker"]).drop_duplicates(subset=["ISIN"]).set_index("ISIN")[
        "Yahoo_Ticker"
    ]
    real_isins = [isin for isin in shares_isin.columns if isin in isin_to_ticker.index]
    real_tickers = sorted({isin_to_ticker.loc[isin] for isin in real_isins if isin_to_ticker.loc[isin] in prices.columns})
    if not real_isins or not real_tickers:
        return tx, empty_frame, empty_frame.copy(), empty_frame.copy(), isin_to_ticker, empty_frame.copy()

    base_ccy = str(base_currency).upper().strip()
    px_local = prices[real_tickers].copy()
    ccy_map = _currency_map_from_mapping(map_df, real_tickers, base_ccy)
    px_base_all = _prices_to_base(prices, real_tickers, map_df, base_ccy)

    effective_shares = shares_isin[real_isins].copy()
    contributions = pd.DataFrame(index=prices.index, columns=real_isins, dtype=float)
    price_base_df = pd.DataFrame(index=prices.index, columns=real_isins, dtype=float)
    debug_dates = [pd.Timestamp("2024-01-08"), pd.Timestamp("2024-01-09")]

    for isin in real_isins:
        ticker = str(isin_to_ticker.loc[isin]).strip()
        inst_ccy = ccy_map.get(ticker, base_ccy)
        price_local = px_local[ticker]
        first_price_date = price_local.first_valid_index()

        first_fx_date = None
        if inst_ccy != base_ccy:
            fx_ticker = f"{inst_ccy}{base_ccy}=X"
            if fx_ticker not in prices.columns:
                raise ValueError(f"Missing FX series for {fx_ticker} required by {ticker}")
            fx_rate = prices[fx_ticker]
            first_fx_date = fx_rate.first_valid_index()
        else:
            fx_rate = pd.Series(1.0, index=prices.index)

        if first_price_date is None or (inst_ccy != base_ccy and first_fx_date is None):
            first_valued_date = None
        elif inst_ccy != base_ccy:
            first_valued_date = max(first_price_date, first_fx_date)
        else:
            first_valued_date = first_price_date

        if first_valued_date is None:
            effective_shares.loc[:, isin] = 0.0
        else:
            effective_shares.loc[effective_shares.index < first_valued_date, isin] = 0.0

        price_base = px_base_all[ticker]
        price_base_df[isin] = price_base
        missing_price_active = effective_shares[isin].ne(0) & price_base.isna()
        if missing_price_active.any():
            first_missing = missing_price_active[missing_price_active].index[0]
            msg = (
                f"Missing price_base for active position "
                f"(portfolio={portfolio_name}, isin={isin}, ticker={ticker}, date={first_missing.date().isoformat()})"
            )
            if STRICT_VALUATION:
                raise ValueError(msg)
            logger.warning(msg)
        value_contribution = (effective_shares[isin] * price_base).fillna(0.0)
        contributions[isin] = value_contribution

        if DEBUG_ENABLED:
            for d in debug_dates:
                if d in contributions.index:
                    logger.info(
                        (
                            "Valuation debug %s ticker=%s inst_ccy=%s first_price_date=%s "
                            "first_fx_date=%s first_valued_date=%s price_local=%.6f fx_rate=%.6f "
                            "price_base=%.6f position=%.6f value_contribution=%.6f"
                        ),
                        d.date().isoformat(),
                        ticker,
                        inst_ccy,
                        first_price_date.date().isoformat() if first_price_date is not None else None,
                        first_fx_date.date().isoformat() if first_fx_date is not None else None,
                        first_valued_date.date().isoformat() if first_valued_date is not None else None,
                        float(price_local.loc[d]) if d in price_local.index and pd.notna(price_local.loc[d]) else np.nan,
                        float(fx_rate.loc[d]) if d in fx_rate.index and pd.notna(fx_rate.loc[d]) else np.nan,
                        float(price_base.loc[d]) if d in price_base.index and pd.notna(price_base.loc[d]) else np.nan,
                        (
                            float(effective_shares.loc[d, isin])
                            if d in effective_shares.index and pd.notna(effective_shares.loc[d, isin])
                            else 0.0
                        ),
                        (
                            float(value_contribution.loc[d])
                            if d in value_contribution.index and pd.notna(value_contribution.loc[d])
                            else 0.0
                        ),
                    )

    return tx, effective_shares, contributions, price_base_df, isin_to_ticker, px_local


def _real_category_returns(
    transactions: pd.DataFrame,
    mapping: pd.DataFrame,
    prices: pd.DataFrame,
    base_currency: str = "SEK",
    portfolio_name: str | None = None,
) -> pd.Series:
    _tx, _effective_shares, contributions, price_base_df, _isin_to_ticker, _px_local = _real_position_state(
        transactions,
        mapping,
        prices,
        base_currency=base_currency,
        portfolio_name=portfolio_name,
    )
    if contributions.empty or contributions.shape[1] == 0:
        return pd.Series(0.0, index=prices.index, dtype=float)

    asset_returns = price_base_df.pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    prev_values = contributions.shift(1).fillna(0.0)
    prev_total = prev_values.sum(axis=1)
    weights = prev_values.div(prev_total.replace(0.0, np.nan), axis=0).fillna(0.0)
    ret = asset_returns.mul(weights, axis=0).sum(axis=1)
    ret = ret.where(prev_total > 0.0, 0.0).fillna(0.0).astype(float)
    if not ret.empty:
        ret.iloc[0] = 0.0
    return ret


def _real_portfolio_returns(
    transactions: pd.DataFrame,
    mapping: pd.DataFrame,
    prices: pd.DataFrame,
    base_currency: str = "SEK",
    portfolio_name: str | None = None,
) -> pd.Series:
    tx, effective_shares, contributions, price_base_df, isin_to_ticker, px_local = _real_position_state(
        transactions,
        mapping,
        prices,
        base_currency=base_currency,
        portfolio_name=portfolio_name,
    )
    if tx.empty or contributions.empty or contributions.shape[1] == 0:
        return pd.Series(0.0, index=prices.index, dtype=float)

    values = contributions.sum(axis=1)
    tx_belopp_base = pd.Series(0.0, index=tx.index, dtype=float)
    base_ccy = str(base_currency).upper().strip()
    if COL_BELOPP in tx.columns:
        belopp = pd.to_numeric(tx[COL_BELOPP], errors="coerce").fillna(0.0)
        if COL_VALUTA not in tx.columns:
            raise ValueError(f"Missing required column '{COL_VALUTA}' for cashflow conversion")

        valuta = tx[COL_VALUTA].astype(str).str.upper().str.strip()
        refx = pd.to_numeric(tx[COL_REFX], errors="coerce") if COL_REFX in tx.columns else pd.Series(np.nan, index=tx.index)
        vax = pd.to_numeric(tx[COL_VAX], errors="coerce") if COL_VAX in tx.columns else pd.Series(np.nan, index=tx.index)

        is_base = valuta == base_ccy
        conversion_rate = refx.where(refx.notna(), vax)
        needs_conversion = ~is_base
        missing_rate = needs_conversion & conversion_rate.isna()
        if missing_rate.any():
            bad_rows = tx.loc[missing_rate, [COL_AFFARSDAG, "ISIN", COL_VALUTA]].head(5)
            raise ValueError(
                f"Cannot convert Belopp to {base_ccy}: missing Referensvalutakurs/V\u00e4xlingskurs. "
                f"Examples: {bad_rows.to_dict(orient='records')}"
            )
        invalid_refx = needs_conversion & refx.notna() & (refx <= 0)
        if invalid_refx.any():
            bad_rows = tx.loc[invalid_refx, [COL_AFFARSDAG, "ISIN", COL_VALUTA, COL_REFX]].head(5)
            raise ValueError(f"Invalid Referensvalutakurs <= 0. Examples: {bad_rows.to_dict(orient='records')}")
        invalid_vax = needs_conversion & refx.isna() & vax.notna() & (vax <= 0)
        if invalid_vax.any():
            bad_rows = tx.loc[invalid_vax, [COL_AFFARSDAG, "ISIN", COL_VALUTA, COL_VAX]].head(5)
            raise ValueError(f"Invalid V\u00e4xlingskurs <= 0. Examples: {bad_rows.to_dict(orient='records')}")

        belopp_base = belopp.copy()
        belopp_base.loc[needs_conversion] = (
            belopp.loc[needs_conversion] * conversion_rate.loc[needs_conversion]
        )
        tx_belopp_base = pd.to_numeric(belopp_base, errors="coerce").fillna(0.0).astype(float)

        belopp_sum_raw = belopp.groupby(tx[COL_EFFECTIVE_DATE]).sum().reindex(values.index).fillna(0.0)
        belopp_sum = tx_belopp_base.groupby(tx[COL_EFFECTIVE_DATE]).sum().reindex(values.index).fillna(0.0)
        cashflow = -belopp_sum
    else:
        belopp_sum_raw = pd.Series(0.0, index=values.index)
        belopp_sum = pd.Series(0.0, index=values.index)
        cashflow = pd.Series(0.0, index=values.index)

    values = pd.to_numeric(values, errors="coerce").astype(float)
    cashflow = pd.to_numeric(cashflow, errors="coerce").astype(float)
    prev_value = pd.to_numeric(values.shift(1), errors="coerce").astype(float)

    valid = prev_value > 0
    denom = prev_value.where(valid)
    ret = ((values - cashflow) / denom) - 1.0
    ret = ret.replace([np.inf, -np.inf], np.nan).where(valid, 0.0).fillna(0.0).astype(float)
    if not ret.empty:
        ret.iloc[0] = 0.0

    large_moves = ret.abs() > 0.15
    for date in ret.index[large_moves]:
        logger.warning(
            "Large daily return portfolio=%s date=%s ret_t=%.8f MV_prev=%.6f MV_t=%.6f CF_t=%.6f",
            portfolio_name,
            date.date().isoformat(),
            float(ret.loc[date]),
            float(prev_value.loc[date]) if pd.notna(prev_value.loc[date]) else 0.0,
            float(values.loc[date]) if pd.notna(values.loc[date]) else 0.0,
            float(cashflow.loc[date]) if pd.notna(cashflow.loc[date]) else 0.0,
        )
        mv_prev = float(prev_value.loc[date]) if pd.notna(prev_value.loc[date]) else 0.0
        cf_abs = abs(float(cashflow.loc[date])) if pd.notna(cashflow.loc[date]) else 0.0
        if mv_prev > 0 and cf_abs > 0.5 * mv_prev:
            logger.warning(
                "Large cashflow vs MV_prev portfolio=%s date=%s |CF_t|/MV_prev=%.4f",
                portfolio_name,
                date.date().isoformat(),
                cf_abs / mv_prev,
            )

    extreme_moves = ret.abs() > 0.30
    for date in ret.index[extreme_moves]:
        held = effective_shares.loc[date]
        held_isins = held[held != 0].index.tolist()
        held_tickers = [str(isin_to_ticker.loc[i]).strip() for i in held_isins if i in isin_to_ticker.index]
        missing_price_tickers = [
            str(isin_to_ticker.loc[i]).strip()
            for i in held_isins
            if i in price_base_df.columns and pd.isna(price_base_df.loc[date, i]) and i in isin_to_ticker.index
        ]
        day_mask = tx[COL_EFFECTIVE_DATE].dt.normalize() == pd.Timestamp(date).normalize()
        tx_day = tx.loc[day_mask].copy()
        if not tx_day.empty:
            tx_day["belopp_base"] = tx_belopp_base.loc[tx_day.index].astype(float)
        else:
            tx_day["belopp_base"] = pd.Series(dtype=float)

        cf_rows_count = int(len(tx_day))
        sum_belopp_base = float(tx_day["belopp_base"].sum()) if cf_rows_count else 0.0
        cf_t_day = float(cashflow.loc[date]) if pd.notna(cashflow.loc[date]) else 0.0
        typ_breakdown = (
            tx_day.groupby("Transaktionstyp")["belopp_base"].sum().sort_values(ascending=False).to_dict()
            if cf_rows_count
            else {}
        )

        portfolio_col = None
        for c in ("Portfolio_ID", "Dep\u00e5", "Portfolio_Name", COL_PORTFOLJ):
            if c in tx_day.columns:
                portfolio_col = c
                break
        detail_cols = [COL_EFFECTIVE_DATE, COL_AFFARSDAG, "Transaktionstyp", "ISIN", "Antal", COL_BELOPP, COL_VALUTA]
        if portfolio_col:
            detail_cols.insert(1, portfolio_col)
        rate_col = COL_REFX if COL_REFX in tx_day.columns else (COL_VAX if COL_VAX in tx_day.columns else None)
        if rate_col:
            detail_cols.append(rate_col)
        detail_cols.append("belopp_base")

        tx_top10 = (
            tx_day.assign(_abs_belopp_base=tx_day["belopp_base"].abs())
            .sort_values("_abs_belopp_base", ascending=False)
            .loc[:, detail_cols + ["_abs_belopp_base"]]
            .head(10)
            .drop(columns=["_abs_belopp_base"])
        )

        traded_isins = sorted(tx_day["ISIN"].dropna().astype(str).str.strip().unique().tolist()) if not tx_day.empty else []
        traded_tickers = sorted(
            {str(isin_to_ticker.loc[i]).strip() for i in traded_isins if i in isin_to_ticker.index}
        )
        check_tickers = sorted(set(held_tickers) | set(traded_tickers))
        held_price_alignment = []
        for t in check_tickers:
            in_index = date in px_local.index
            local_available = in_index and t in px_local.columns and pd.notna(px_local.loc[date, t])
            base_available = False
            matching_isins = [i for i in held_isins + traded_isins if i in isin_to_ticker.index and str(isin_to_ticker.loc[i]).strip() == t]
            for mi in matching_isins:
                if mi in price_base_df.columns and date in price_base_df.index and pd.notna(price_base_df.loc[date, mi]):
                    base_available = True
                    break
            held_price_alignment.append(
                {
                    "ticker": t,
                    "date_in_price_index": bool(in_index),
                    "price_local_available": bool(local_available),
                    "price_base_available": bool(base_available),
                }
            )

        logger.error(
            "Extreme RET diagnostics portfolio=%s date=%s ret_t=%.8f MV_prev=%.6f MV_t=%.6f CF_t=%.6f "
            "cf_rows_count=%s sum_belopp_base=%.6f breakdown_by_transaktionstyp=%s missing_price_tickers=%s",
            portfolio_name,
            date.date().isoformat(),
            float(ret.loc[date]),
            float(prev_value.loc[date]) if pd.notna(prev_value.loc[date]) else 0.0,
            float(values.loc[date]) if pd.notna(values.loc[date]) else 0.0,
            cf_t_day,
            cf_rows_count,
            sum_belopp_base,
            typ_breakdown,
            missing_price_tickers,
        )
        if not tx_top10.empty:
            logger.error("Extreme RET top CF rows (max 10):\n%s", tx_top10.to_string(index=False))
        logger.error("Extreme RET held ticker price alignment: %s", held_price_alignment)

        msg = (
            "Extreme daily return detected "
            f"(portfolio={portfolio_name}, date={date.date().isoformat()}, ret_t={float(ret.loc[date]):.8f}, "
            f"MV_prev={float(prev_value.loc[date]) if pd.notna(prev_value.loc[date]) else 0.0:.6f}, "
            f"MV_t={float(values.loc[date]) if pd.notna(values.loc[date]) else 0.0:.6f}, "
            f"CF_t={float(cashflow.loc[date]) if pd.notna(cashflow.loc[date]) else 0.0:.6f}, "
            f"missing_price_tickers={missing_price_tickers})"
        )
        if missing_price_tickers and not STRICT_EXTREME_RET:
            logger.warning("%s -> STRICT_EXTREME_RET=0, setting ret_t=0 for this date", msg)
            ret.loc[date] = 0.0
            continue
        raise ValueError(
            f"Extreme daily return detected for portfolio={portfolio_name} on {date.date().isoformat()}. "
            "See log output for transaction and price-alignment diagnostics."
        )

    d2 = pd.Timestamp("2026-02-18")
    if DEBUG_ENABLED and d2 in ret.index and str(portfolio_name or "").strip().upper() == "EGEN":
        logger.info(
            (
                "TWR debug %s EGEN: sum(Belopp)_raw=%.6f sum(belopp_base)_SEK=%.6f "
                "CF_t=%.6f MV_prev=%.6f MV_t=%.6f ret_t=%.8f"
            ),
            d2.date().isoformat(),
            float(belopp_sum_raw.loc[d2]) if pd.notna(belopp_sum_raw.loc[d2]) else 0.0,
            float(belopp_sum.loc[d2]) if pd.notna(belopp_sum.loc[d2]) else 0.0,
            float(cashflow.loc[d2]) if pd.notna(cashflow.loc[d2]) else 0.0,
            float(prev_value.loc[d2]) if pd.notna(prev_value.loc[d2]) else 0.0,
            float(values.loc[d2]) if pd.notna(values.loc[d2]) else 0.0,
            float(ret.loc[d2]) if pd.notna(ret.loc[d2]) else 0.0,
        )

    return ret

def build_series_definition(
    portfolio_metadata: pd.DataFrame,
    benchmarks: pd.DataFrame,
    mapping: pd.DataFrame,
    transactions: pd.DataFrame,
    real_tickers: list[str],
    model_tickers: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    instrument_meta = _instrument_metadata_by_ticker(mapping).set_index("Yahoo_Ticker", drop=False)
    tx_all = transactions.copy()
    if "Portfolio_ID" not in tx_all.columns and "Dep\u00e5" in tx_all.columns:
        tx_all["Portfolio_ID"] = tx_all["Dep\u00e5"]

    portfolio_col = "Portfolio_ID" if "Portfolio_ID" in portfolio_metadata.columns else "Portfolio_Name"
    tx_port_col = (
        "Portfolio_ID"
        if "Portfolio_ID" in tx_all.columns and portfolio_col == "Portfolio_ID"
        else _portfolio_name_col(tx_all)
    )

    for meta in _portfolio_rows(portfolio_metadata):
        portfolio_name = str(meta["Portfolio_Name"])
        idx_start = pd.to_datetime(meta["Index_Start_Date"])
        idx0 = float(meta["Initial_Index_Value"])

        for suffix in ("REAL", "CUR", "TGT"):
            rows.append(
                {
                    "Series_ID": f"PORT_{slug(portfolio_name)}_{suffix}",
                    "Series_Type": "PORT",
                    "Portfolio_Name": portfolio_name,
                    "Variant": suffix,
                    "Benchmark_ID": None,
                    "Yahoo_Ticker": None,
                    "ISIN": None,
                    "Display_Name": None,
                    "Price_Currency": None,
                    "Instrument_Type": None,
                    "Category": None,
                    "Include_From_Date": idx_start,
                    "Index_Start_Date": idx_start,
                    "Initial_Index_Value": idx0,
                }
            )

        if tx_port_col is None:
            tx_p = tx_all
        else:
            portfolio_key = str(meta[portfolio_col]).strip() if portfolio_col in meta.index else portfolio_name
            tx_p = tx_all[tx_all[tx_port_col].astype(str).str.strip() == portfolio_key]

        for category_slug, category in _real_category_slug_map(tx_p, mapping).items():
            rows.append(
                {
                    "Series_ID": f"PORT_{slug(portfolio_name)}_REAL_CAT_{category_slug}",
                    "Series_Type": "PORT",
                    "Portfolio_Name": portfolio_name,
                    "Variant": "REAL",
                    "Benchmark_ID": None,
                    "Yahoo_Ticker": None,
                    "ISIN": None,
                    "Display_Name": None,
                    "Price_Currency": None,
                    "Instrument_Type": None,
                    "Category": category,
                    "Include_From_Date": idx_start,
                    "Index_Start_Date": idx_start,
                    "Initial_Index_Value": idx0,
                }
            )

    default_meta = _portfolio_rows(portfolio_metadata)[0]
    idx_start = pd.to_datetime(default_meta["Index_Start_Date"])
    idx0 = float(default_meta["Initial_Index_Value"])

    for _, row in benchmarks.iterrows():
        ticker = str(row["Yahoo_Ticker"]).strip()
        info = instrument_meta.loc[ticker] if ticker in instrument_meta.index else None
        benchmark_price_currency = None
        if COL_PRICE_CCY in row.index:
            price_ccy_raw = row[COL_PRICE_CCY]
            if pd.notna(price_ccy_raw) and str(price_ccy_raw).strip():
                benchmark_price_currency = str(price_ccy_raw).strip().upper()

        rows.append(
            {
                "Series_ID": f"BM_{slug(row['Benchmark_ID'])}",
                "Series_Type": "BM",
                "Portfolio_Name": None,
                "Variant": None,
                "Benchmark_ID": row["Benchmark_ID"],
                "Yahoo_Ticker": ticker,
                "ISIN": info["ISIN"] if info is not None else None,
                "Display_Name": info["Display_Name"] if info is not None else None,
                "Price_Currency": benchmark_price_currency or (info[COL_PRICE_CCY] if info is not None else None),
                "Instrument_Type": info["Instrument_Type"] if info is not None else None,
                "Category": info["Category"] if info is not None else None,
                "Include_From_Date": pd.to_datetime(row["Include_From_Date"], errors="coerce"),
                "Index_Start_Date": idx_start,
                "Initial_Index_Value": idx0,
            }
        )

    for ticker in sorted(set(real_tickers) | set(model_tickers)):
        info = instrument_meta.loc[ticker] if ticker in instrument_meta.index else None
        rows.append(
            {
                "Series_ID": f"AST_{slug(ticker)}",
                "Series_Type": "AST",
                "Portfolio_Name": None,
                "Variant": None,
                "Benchmark_ID": None,
                "Yahoo_Ticker": ticker,
                "ISIN": info["ISIN"] if info is not None else None,
                "Display_Name": info["Display_Name"] if info is not None else ticker,
                "Price_Currency": info[COL_PRICE_CCY] if info is not None else None,
                "Instrument_Type": info["Instrument_Type"] if info is not None else None,
                "Category": info["Category"] if info is not None else None,
                "Include_From_Date": idx_start,
                "Index_Start_Date": idx_start,
                "Initial_Index_Value": np.nan,
            }
        )

    return pd.DataFrame(rows)


def build_portfolios_and_benchmarks(inputs: EngineInputs) -> dict[str, pd.DataFrame]:
    prices = inputs.prices.sort_index()

    out: dict[str, pd.DataFrame] = {}

    meta_rows = _portfolio_rows(inputs.portfolio_metadata)
    tx_all = inputs.transactions.copy()
    if "Portfolio_ID" not in tx_all.columns and "Dep\u00e5" in tx_all.columns:
        # Dep\u00e5 anv\u00e4nds som Portfolio_ID i Nordnet-export.
        tx_all["Portfolio_ID"] = tx_all["Dep\u00e5"]

    fonder_all = inputs.fondertabell.copy()

    meta_port_col = "Portfolio_ID" if "Portfolio_ID" in inputs.portfolio_metadata.columns else "Portfolio_Name"
    tx_port_col = "Portfolio_ID" if "Portfolio_ID" in tx_all.columns and meta_port_col == "Portfolio_ID" else _portfolio_name_col(tx_all)
    if len(meta_rows) > 1 and tx_port_col is None:
        raise ValueError("Transactions must include a portfolio column when multiple portfolios exist")

    if COL_PORTFOLJ in fonder_all.columns:
        fonder_port_col = COL_PORTFOLJ
    else:
        fonder_port_col = _portfolio_name_col(fonder_all)
    if len(meta_rows) > 1 and fonder_port_col is None:
        raise ValueError("Fondertabell must include a portfolio column when multiple portfolios exist")

    for meta in meta_rows:
        portfolio_name = str(meta["Portfolio_Name"])
        portfolio_key = str(meta[meta_port_col]).strip() if meta_port_col in meta.index else portfolio_name
        start_date = pd.to_datetime(meta["Index_Start_Date"])
        initial_index_value = float(meta["Initial_Index_Value"])

        if tx_port_col is None:
            tx_p = tx_all
        else:
            tx_p = tx_all[tx_all[tx_port_col].astype(str).str.strip() == portfolio_key]

        if fonder_port_col is None:
            fonder_p = fonder_all
        else:
            if fonder_port_col == COL_PORTFOLJ:
                # Fondertabell uses portfolio names (e.g. PA, EGEN), not Portfolio_ID.
                fonder_key = portfolio_name
            else:
                fonder_key = portfolio_key
            fonder_p = fonder_all[fonder_all[fonder_port_col].astype(str).str.strip() == str(fonder_key).strip()]
        if fonder_p.empty:
            available = []
            if fonder_port_col is not None:
                available = sorted({str(x).strip() for x in fonder_all[fonder_port_col].dropna().unique()})
            raise ValueError(
                f"Fondertabell has no rows for portfolio '{portfolio_name}' "
                f"(column={fonder_port_col}, available={available})"
            )

        real_tickers = []
        if not tx_p.empty and "ISIN" in tx_p.columns:
            map_df = inputs.mapping.copy()
            map_df["ISIN"] = map_df["ISIN"].astype(str).str.strip()
            map_df["Yahoo_Ticker"] = map_df["Yahoo_Ticker"].astype(str).str.strip()
            isin_to_ticker = map_df.set_index("ISIN")["Yahoo_Ticker"].to_dict()
            tx_isins = tx_p["ISIN"].dropna().astype(str).str.strip()
            real_tickers = sorted({isin_to_ticker.get(isin, "") for isin in tx_isins if isin_to_ticker.get(isin, "")})
        prices_real = _portfolio_price_frame(prices, real_tickers, start_date)
        real_fx_tickers = _fx_tickers_for_assets(real_tickers, inputs.mapping, inputs.base_currency)
        prices_real = _portfolio_price_frame(prices, real_tickers, start_date, extra_tickers=real_fx_tickers)
        if prices_real.empty:
            prices_real = prices[prices.index >= start_date].copy()

        real_ret = _real_portfolio_returns(
            tx_p,
            inputs.mapping,
            prices_real,
            base_currency=inputs.base_currency,
            portfolio_name=portfolio_name,
        )
        out[f"PORT_{slug(portfolio_name)}_REAL"] = _series_frame(real_ret, initial_index_value)

        for category_slug, category in _real_category_slug_map(tx_p, inputs.mapping).items():
            tx_category = _transactions_for_category(tx_p, inputs.mapping, category)
            tx_category_isins = tx_category["ISIN"].dropna().astype(str).str.strip()
            category_tickers = sorted(
                {isin_to_ticker.get(isin, "") for isin in tx_category_isins if isin_to_ticker.get(isin, "")}
            )
            category_fx_tickers = _fx_tickers_for_assets(category_tickers, inputs.mapping, inputs.base_currency)
            prices_category = _portfolio_price_frame_full_calendar(
                prices,
                category_tickers,
                start_date,
                extra_tickers=category_fx_tickers,
            )
            if prices_category.empty:
                prices_category = prices[prices.index >= start_date].copy()

            category_ret = _real_category_returns(
                tx_category,
                inputs.mapping,
                prices_category,
                base_currency=inputs.base_currency,
                portfolio_name=f"{portfolio_name}:{category}",
            )
            out[f"PORT_{slug(portfolio_name)}_REAL_CAT_{category_slug}"] = _series_frame(
                category_ret,
                initial_index_value,
            )

        try:
            cur_w = _weights_from_fonder(fonder_p, "Andel", portfolio_name=portfolio_name)
            cur_assets = list(cur_w.index)
            cur_fx_tickers = _fx_tickers_for_assets(cur_assets, inputs.mapping, inputs.base_currency)
            prices_cur = _portfolio_price_frame(prices, cur_assets, start_date, extra_tickers=cur_fx_tickers)
            prices_cur_base = _prices_to_base(prices_cur, cur_assets, inputs.mapping, inputs.base_currency)
            cur_ret = _portfolio_returns_from_weights(returns_from_prices(prices_cur_base), cur_w)
            out[f"PORT_{slug(portfolio_name)}_CUR"] = _series_frame(cur_ret, initial_index_value)
        except ValueError as exc:
            if "Portfolio has no weights" in str(exc):
                logger.warning("Skipping CUR for portfolio=%s: %s", portfolio_name, exc)
            else:
                raise

        try:
            tgt_w = _weights_from_fonder(fonder_p, "AndelP", portfolio_name=portfolio_name)
            tgt_assets = list(tgt_w.index)
            tgt_fx_tickers = _fx_tickers_for_assets(tgt_assets, inputs.mapping, inputs.base_currency)
            prices_tgt = _portfolio_price_frame(prices, tgt_assets, start_date, extra_tickers=tgt_fx_tickers)
            prices_tgt_base = _prices_to_base(prices_tgt, tgt_assets, inputs.mapping, inputs.base_currency)
            tgt_ret = _portfolio_returns_from_weights(returns_from_prices(prices_tgt_base), tgt_w)
            out[f"PORT_{slug(portfolio_name)}_TGT"] = _series_frame(tgt_ret, initial_index_value)
        except ValueError as exc:
            if "Portfolio has no weights" in str(exc):
                logger.warning("Skipping TGT for portfolio=%s: %s", portfolio_name, exc)
            else:
                raise

    default_idx0 = float(meta_rows[0]["Initial_Index_Value"])
    for _, bm in inputs.benchmarks.iterrows():
        ticker = str(bm["Yahoo_Ticker"]).strip()
        if ticker not in prices.columns:
            logger.warning("Benchmark ticker missing from price data: %s", ticker)
            continue
        include_from = pd.to_datetime(bm["Include_From_Date"], errors="coerce")
        bm_prices = prices[[ticker]].dropna(how="all")
        if bm_prices.empty:
            logger.warning("Benchmark ticker has no usable price rows: %s", ticker)
            continue
        bm_ret = returns_from_prices(bm_prices)[ticker]
        if pd.notna(include_from):
            bm_ret = bm_ret[bm_ret.index >= include_from]
        if bm_ret.empty:
            logger.warning("Benchmark ticker has no returns after Include_From_Date: %s", ticker)
            continue
        out[f"BM_{slug(bm['Benchmark_ID'])}"] = _series_frame(bm_ret, default_idx0)

    return out


def _latest_real_weights(
    transactions: pd.DataFrame,
    mapping: pd.DataFrame,
    prices: pd.DataFrame,
    base_currency: str = "SEK",
    portfolio_name: str | None = None,
) -> pd.Series:
    _tx, _effective_shares, contributions, _price_base_df, isin_to_ticker, _px_local = _real_position_state(
        transactions,
        mapping,
        prices,
        base_currency=base_currency,
        portfolio_name=portfolio_name,
    )
    if contributions.empty or contributions.shape[1] == 0:
        raise ValueError(f"Portfolio has no real holdings snapshot (portfolio={portfolio_name})")

    total_value = contributions.sum(axis=1).fillna(0.0)
    positive_dates = total_value[total_value > 0]
    if positive_dates.empty:
        raise ValueError(f"Portfolio has no positive real holdings value (portfolio={portfolio_name})")

    snapshot_date = positive_dates.index.max()
    snapshot = contributions.loc[snapshot_date]
    snapshot = snapshot[snapshot > 0].dropna()
    if snapshot.empty:
        raise ValueError(
            f"Portfolio has no positive real holdings contributions on snapshot date "
            f"(portfolio={portfolio_name}, date={pd.Timestamp(snapshot_date).date().isoformat()})"
        )

    by_ticker: dict[str, float] = {}
    for isin, value in snapshot.items():
        ticker = str(isin_to_ticker.loc[isin]).strip() if isin in isin_to_ticker.index else ""
        if not ticker:
            continue
        by_ticker[ticker] = by_ticker.get(ticker, 0.0) + float(value)

    weights = pd.Series(by_ticker, dtype=float)
    weights = weights[weights > 0]
    if weights.empty:
        raise ValueError(f"Portfolio real holdings snapshot did not resolve to tickers (portfolio={portfolio_name})")
    return weights / weights.sum()


def build_portfolio_series_map(
    portfolio_metadata: pd.DataFrame,
    transactions: pd.DataFrame,
    mapping: pd.DataFrame,
    fondertabell: pd.DataFrame,
    prices: pd.DataFrame,
    base_currency: str = "SEK",
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    instrument_meta = _instrument_metadata_by_ticker(mapping).set_index("Yahoo_Ticker", drop=False)
    meta_rows = _portfolio_rows(portfolio_metadata)
    tx_all = transactions.copy()
    if "Portfolio_ID" not in tx_all.columns and "Dep\u00e5" in tx_all.columns:
        tx_all["Portfolio_ID"] = tx_all["Dep\u00e5"]
    fonder_port_col = _portfolio_name_col(fondertabell)
    meta_port_col = "Portfolio_ID" if "Portfolio_ID" in portfolio_metadata.columns else "Portfolio_Name"
    tx_port_col = "Portfolio_ID" if "Portfolio_ID" in tx_all.columns and meta_port_col == "Portfolio_ID" else _portfolio_name_col(tx_all)
    if len(meta_rows) > 1 and fonder_port_col is None:
        raise ValueError("Fondertabell must include a portfolio column when multiple portfolios exist")
    if len(meta_rows) > 1 and tx_port_col is None:
        raise ValueError("Transactions must include a portfolio column when multiple portfolios exist")

    for meta in meta_rows:
        portfolio_name = str(meta["Portfolio_Name"])
        portfolio_key = str(meta[meta_port_col]).strip() if meta_port_col in meta.index else portfolio_name
        start_date = pd.to_datetime(meta["Index_Start_Date"])

        if tx_port_col is None:
            tx_p = tx_all
        else:
            tx_p = tx_all[tx_all[tx_port_col].astype(str).str.strip() == portfolio_key]

        if fonder_port_col is None:
            fonder_p = fondertabell
        else:
            fonder_p = fondertabell[fondertabell[fonder_port_col].astype(str).str.strip() == portfolio_name]

        real_tickers = []
        if not tx_p.empty and "ISIN" in tx_p.columns:
            map_df = mapping.copy()
            map_df["ISIN"] = map_df["ISIN"].astype(str).str.strip()
            map_df["Yahoo_Ticker"] = map_df["Yahoo_Ticker"].astype(str).str.strip()
            isin_to_ticker = map_df.set_index("ISIN")["Yahoo_Ticker"].to_dict()
            tx_isins = tx_p["ISIN"].dropna().astype(str).str.strip()
            real_tickers = sorted({isin_to_ticker.get(isin, "") for isin in tx_isins if isin_to_ticker.get(isin, "")})
        real_fx_tickers = _fx_tickers_for_assets(real_tickers, mapping, base_currency)
        prices_real = _portfolio_price_frame(prices, real_tickers, start_date, extra_tickers=real_fx_tickers)
        if prices_real.empty:
            prices_real = prices[prices.index >= start_date].copy()

        try:
            real_w = _latest_real_weights(
                tx_p,
                mapping,
                prices_real,
                base_currency=base_currency,
                portfolio_name=portfolio_name,
            )
            for ticker, weight in real_w.items():
                info = instrument_meta.loc[ticker] if ticker in instrument_meta.index else None
                rows.append(
                    {
                        "Portfolio_Name": portfolio_name,
                        "Series_ID": f"PORT_{slug(portfolio_name)}_REAL",
                        "ISIN": info["ISIN"] if info is not None else None,
                        "Display_Name": info["Display_Name"] if info is not None else ticker,
                        "Price_Currency": info[COL_PRICE_CCY] if info is not None else None,
                        "Yahoo_Ticker": ticker,
                        "Weight": float(weight),
                        "Weight_Source": "REAL",
                    }
                )
        except ValueError as exc:
            logger.warning("Skipping REAL snapshot for portfolio=%s: %s", portfolio_name, exc)

        cur_w = _weights_from_fonder(fonder_p, "Andel", portfolio_name=portfolio_name)
        tgt_w = _weights_from_fonder(fonder_p, "AndelP", portfolio_name=portfolio_name)

        for ticker, weight in cur_w.items():
            info = instrument_meta.loc[ticker] if ticker in instrument_meta.index else None
            rows.append(
                {
                    "Portfolio_Name": portfolio_name,
                    "Series_ID": f"PORT_{slug(portfolio_name)}_CUR",
                    "ISIN": info["ISIN"] if info is not None else None,
                    "Display_Name": info["Display_Name"] if info is not None else ticker,
                    "Price_Currency": info[COL_PRICE_CCY] if info is not None else None,
                    "Yahoo_Ticker": ticker,
                    "Weight": float(weight),
                    "Weight_Source": "Andel",
                }
            )
        for ticker, weight in tgt_w.items():
            info = instrument_meta.loc[ticker] if ticker in instrument_meta.index else None
            rows.append(
                {
                    "Portfolio_Name": portfolio_name,
                    "Series_ID": f"PORT_{slug(portfolio_name)}_TGT",
                    "ISIN": info["ISIN"] if info is not None else None,
                    "Display_Name": info["Display_Name"] if info is not None else ticker,
                    "Price_Currency": info[COL_PRICE_CCY] if info is not None else None,
                    "Yahoo_Ticker": ticker,
                    "Weight": float(weight),
                    "Weight_Source": "AndelP",
                }
            )
    return pd.DataFrame(rows)
