"""Portfolio and benchmark series construction."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .prices import download_adj_close, returns_from_prices

COL_AFFARSDAG = "Aff\u00e4rsdag"
TXN_KOPT = "K\u00d6PT"
TXN_SALT = "S\u00c5LT"
COL_BELOPP = "Belopp"
COL_PORTFOLJ = "Portf\u00f6lj"
COL_VALUTA = "Valuta"
COL_REFX = "Referensvalutakurs"
COL_VAX = "V\u00e4xlingskurs"

logger = logging.getLogger(__name__)
DEBUG_ENABLED = os.getenv("PORTFOLIO_DEBUG") == "1"
STRICT_VALUATION = os.getenv("PORTFOLIO_STRICT") == "1"


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
    bm_tickers = sorted({str(x).strip() for x in benchmarks["Yahoo_Ticker"].dropna() if str(x).strip()})
    model_tickers = sorted({str(x).strip() for x in fondertabell["Yahoo"].dropna() if str(x).strip()})
    all_tickers = sorted(set(real_tickers) | set(bm_tickers) | set(model_tickers))

    return {
        "real": real_tickers,
        "benchmarks": bm_tickers,
        "model": model_tickers,
        "all": all_tickers,
    }


@dataclass
class EngineInputs:
    transactions: pd.DataFrame
    mapping: pd.DataFrame
    portfolio_metadata: pd.DataFrame
    benchmarks: pd.DataFrame
    fondertabell: pd.DataFrame
    prices: pd.DataFrame


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


def _real_portfolio_returns(
    transactions: pd.DataFrame,
    mapping: pd.DataFrame,
    prices: pd.DataFrame,
    base_currency: str = "SEK",
    portfolio_name: str | None = None,
) -> pd.Series:
    tx = transactions.copy()
    tx[COL_AFFARSDAG] = pd.to_datetime(tx[COL_AFFARSDAG], errors="coerce")
    tx = tx.dropna(subset=[COL_AFFARSDAG, "ISIN", "Antal", "Transaktionstyp"])
    if tx.empty:
        return pd.Series(0.0, index=prices.index)
    tx["ISIN"] = tx["ISIN"].astype(str).str.strip()
    tx["Antal"] = pd.to_numeric(tx["Antal"], errors="coerce").fillna(0.0)
    tx["Transaktionstyp"] = tx["Transaktionstyp"].astype(str).str.strip().str.upper()
    sign = tx["Transaktionstyp"].map({TXN_KOPT: 1.0, TXN_SALT: -1.0})
    tx["signed_qty"] = tx["Antal"] * sign.fillna(0.0)

    map_df = mapping.copy()
    map_df["ISIN"] = map_df["ISIN"].astype(str).str.strip()
    map_df["Yahoo_Ticker"] = map_df["Yahoo_Ticker"].astype(str).str.strip()
    isin_to_ticker = map_df.set_index("ISIN")["Yahoo_Ticker"]

    tx["Yahoo_Ticker"] = tx["ISIN"].map(isin_to_ticker)
    missing = sorted(tx.loc[tx["Yahoo_Ticker"].isna(), "ISIN"].unique())
    if missing:
        raise ValueError(f"Missing Mapping for ISIN(s): {missing}")

    flows = (
        tx.groupby([COL_AFFARSDAG, "Yahoo_Ticker"], as_index=False)["signed_qty"]
        .sum()
        .pivot(index=COL_AFFARSDAG, columns="Yahoo_Ticker", values="signed_qty")
        .fillna(0.0)
        .sort_index()
    )
    shares = flows.cumsum()
    shares = shares.reindex(prices.index).ffill().fillna(0.0)

    real_cols = [c for c in shares.columns if c in prices.columns]
    if not real_cols:
        return pd.Series(0.0, index=prices.index)

    base_ccy = str(base_currency).upper().strip()
    px_local = prices[real_cols].copy()

    # Currency metadata per ticker from Mapping.Price_Currency.
    ccy_map = (
        map_df.groupby("Yahoo_Ticker", as_index=True)["Price_Currency"]
        .first()
        .astype(str)
        .str.upper()
        .str.strip()
        .replace({"": base_ccy, "NAN": base_ccy, "NONE": base_ccy})
        .to_dict()
    )
    for ticker in real_cols:
        if ticker not in ccy_map:
            ccy_map[ticker] = base_ccy

    # FX download for non-base currencies, aligned to same trading calendar.
    pair_to_yf = {
        f"{ccy}{base_ccy}": f"{ccy}{base_ccy}=X"
        for ccy in sorted({ccy_map[t] for t in real_cols})
        if ccy and ccy != base_ccy
    }
    if pair_to_yf:
        fx_raw = download_adj_close(
            tickers=list(pair_to_yf.values()),
            start_date=prices.index.min(),
            end_date=None,
            forward_fill=True,
        )
        fx = fx_raw.rename(columns={yf_t: pair for pair, yf_t in pair_to_yf.items()})
        fx = fx.reindex(prices.index).ffill()
    else:
        fx = pd.DataFrame(index=prices.index)

    effective_shares = shares[real_cols].copy()
    contributions = pd.DataFrame(index=prices.index, columns=real_cols, dtype=float)
    debug_dates = [pd.Timestamp("2024-01-08"), pd.Timestamp("2024-01-09")]

    for ticker in real_cols:
        inst_ccy = ccy_map.get(ticker, base_ccy)
        price_local = px_local[ticker]
        first_price_date = price_local.first_valid_index()

        first_fx_date = None
        if inst_ccy != base_ccy:
            pair = f"{inst_ccy}{base_ccy}"
            if pair not in fx.columns:
                raise ValueError(f"Missing FX data column for pair: {pair}")
            fx_rate = fx[pair]
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
            effective_shares.loc[:, ticker] = 0.0
        else:
            effective_shares.loc[effective_shares.index < first_valued_date, ticker] = 0.0

        price_base = price_local * fx_rate
        missing_price_active = effective_shares[ticker].ne(0) & price_base.isna()
        if missing_price_active.any():
            first_missing = missing_price_active[missing_price_active].index[0]
            msg = (
                f"Missing price_base for active position "
                f"(portfolio={portfolio_name}, ticker={ticker}, date={first_missing.date().isoformat()})"
            )
            if STRICT_VALUATION:
                raise ValueError(msg)
            logger.warning(msg)
        value_contribution = (effective_shares[ticker] * price_base).fillna(0.0)
        contributions[ticker] = value_contribution

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
                            float(effective_shares.loc[d, ticker])
                            if d in effective_shares.index and pd.notna(effective_shares.loc[d, ticker])
                            else 0.0
                        ),
                        (
                            float(value_contribution.loc[d])
                            if d in value_contribution.index and pd.notna(value_contribution.loc[d])
                            else 0.0
                        ),
                    )

    values = contributions.sum(axis=1)
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

        belopp_sum_raw = belopp.groupby(tx[COL_AFFARSDAG]).sum().reindex(values.index).fillna(0.0)
        belopp_sum = belopp_base.groupby(tx[COL_AFFARSDAG]).sum().reindex(values.index).fillna(0.0)
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
    if extreme_moves.any():
        date = ret.index[extreme_moves][0]
        raise ValueError(
            "Extreme daily return detected "
            f"(portfolio={portfolio_name}, date={date.date().isoformat()}, ret_t={float(ret.loc[date]):.8f}, "
            f"MV_prev={float(prev_value.loc[date]) if pd.notna(prev_value.loc[date]) else 0.0:.6f}, "
            f"MV_t={float(values.loc[date]) if pd.notna(values.loc[date]) else 0.0:.6f}, "
            f"CF_t={float(cashflow.loc[date]) if pd.notna(cashflow.loc[date]) else 0.0:.6f})"
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
    real_tickers: list[str],
    model_tickers: list[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

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
                    "Instrument_Type": None,
                    "Category": None,
                    "Include_From_Date": idx_start,
                    "Index_Start_Date": idx_start,
                    "Initial_Index_Value": idx0,
                }
            )

    default_meta = _portfolio_rows(portfolio_metadata)[0]
    idx_start = pd.to_datetime(default_meta["Index_Start_Date"])
    idx0 = float(default_meta["Initial_Index_Value"])

    for _, row in benchmarks.iterrows():
        rows.append(
            {
                "Series_ID": f"BM_{slug(row['Benchmark_ID'])}",
                "Series_Type": "BM",
                "Portfolio_Name": None,
                "Variant": None,
                "Benchmark_ID": row["Benchmark_ID"],
                "Yahoo_Ticker": row["Yahoo_Ticker"],
                "Instrument_Type": None,
                "Category": None,
                "Include_From_Date": pd.to_datetime(row["Include_From_Date"], errors="coerce"),
                "Index_Start_Date": idx_start,
                "Initial_Index_Value": idx0,
            }
        )

    mp = mapping.copy()
    mp["Yahoo_Ticker"] = mp["Yahoo_Ticker"].astype(str).str.strip()
    mp = mp[mp["Yahoo_Ticker"] != ""]
    map_info = mp.groupby("Yahoo_Ticker", as_index=False).agg(
        Instrument_Type=("Instrument_Type", "first"),
        Category=("Category", "first"),
    )

    for ticker in sorted(set(real_tickers) | set(model_tickers)):
        info = map_info[map_info["Yahoo_Ticker"] == ticker]
        rows.append(
            {
                "Series_ID": f"AST_{slug(ticker)}",
                "Series_Type": "AST",
                "Portfolio_Name": None,
                "Variant": None,
                "Benchmark_ID": None,
                "Yahoo_Ticker": ticker,
                "Instrument_Type": info["Instrument_Type"].iloc[0] if not info.empty else None,
                "Category": info["Category"].iloc[0] if not info.empty else None,
                "Include_From_Date": idx_start,
                "Index_Start_Date": idx_start,
                "Initial_Index_Value": np.nan,
            }
        )

    return pd.DataFrame(rows)


def build_portfolios_and_benchmarks(inputs: EngineInputs) -> dict[str, pd.DataFrame]:
    prices = inputs.prices.sort_index()
    asset_returns = returns_from_prices(prices)

    out: dict[str, pd.DataFrame] = {}

    meta_rows = _portfolio_rows(inputs.portfolio_metadata)
    tx_all = inputs.transactions.copy()
    if "Portfolio_ID" not in tx_all.columns and "Depå" in tx_all.columns:
        # Depå används som Portfolio_ID i Nordnet-export.
        tx_all["Portfolio_ID"] = tx_all["Depå"]

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

        prices_p = prices[prices.index >= start_date]
        asset_returns_p = asset_returns[asset_returns.index >= start_date]

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

        real_ret = _real_portfolio_returns(
            tx_p,
            inputs.mapping,
            prices_p,
            portfolio_name=portfolio_name,
        )
        out[f"PORT_{slug(portfolio_name)}_REAL"] = _series_frame(real_ret, initial_index_value)

        try:
            cur_w = _weights_from_fonder(fonder_p, "Andel", portfolio_name=portfolio_name)
            cur_ret = _portfolio_returns_from_weights(asset_returns_p, cur_w)
            out[f"PORT_{slug(portfolio_name)}_CUR"] = _series_frame(cur_ret, initial_index_value)
        except ValueError as exc:
            if "Portfolio has no weights" in str(exc):
                logger.warning("Skipping CUR for portfolio=%s: %s", portfolio_name, exc)
            else:
                raise

        try:
            tgt_w = _weights_from_fonder(fonder_p, "AndelP", portfolio_name=portfolio_name)
            tgt_ret = _portfolio_returns_from_weights(asset_returns_p, tgt_w)
            out[f"PORT_{slug(portfolio_name)}_TGT"] = _series_frame(tgt_ret, initial_index_value)
        except ValueError as exc:
            if "Portfolio has no weights" in str(exc):
                logger.warning("Skipping TGT for portfolio=%s: %s", portfolio_name, exc)
            else:
                raise

    default_idx0 = float(meta_rows[0]["Initial_Index_Value"])
    for _, bm in inputs.benchmarks.iterrows():
        ticker = str(bm["Yahoo_Ticker"]).strip()
        if ticker not in asset_returns.columns:
            raise ValueError(f"Missing Yahoo data for benchmark ticker: {ticker}")
        include_from = pd.to_datetime(bm["Include_From_Date"], errors="coerce")
        bm_ret = asset_returns[ticker]
        if pd.notna(include_from):
            bm_ret = bm_ret[bm_ret.index >= include_from]
        out[f"BM_{slug(bm['Benchmark_ID'])}"] = _series_frame(bm_ret, default_idx0)

    return out


def build_portfolio_series_map(
    portfolio_metadata: pd.DataFrame,
    fondertabell: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    meta_rows = _portfolio_rows(portfolio_metadata)
    fonder_port_col = _portfolio_name_col(fondertabell)
    if len(meta_rows) > 1 and fonder_port_col is None:
        raise ValueError("Fondertabell must include a portfolio column when multiple portfolios exist")

    for meta in meta_rows:
        portfolio_name = str(meta["Portfolio_Name"])
        if fonder_port_col is None:
            fonder_p = fondertabell
        else:
            fonder_p = fondertabell[fondertabell[fonder_port_col].astype(str).str.strip() == portfolio_name]

        cur_w = _weights_from_fonder(fonder_p, "Andel", portfolio_name=portfolio_name)
        tgt_w = _weights_from_fonder(fonder_p, "AndelP", portfolio_name=portfolio_name)

        for ticker, weight in cur_w.items():
            rows.append(
                {
                    "Portfolio_Name": portfolio_name,
                    "Series_ID": f"PORT_{slug(portfolio_name)}_CUR",
                    "Yahoo_Ticker": ticker,
                    "Weight": float(weight),
                    "Weight_Source": "Andel",
                }
            )
        for ticker, weight in tgt_w.items():
            rows.append(
                {
                    "Portfolio_Name": portfolio_name,
                    "Series_ID": f"PORT_{slug(portfolio_name)}_TGT",
                    "Yahoo_Ticker": ticker,
                    "Weight": float(weight),
                    "Weight_Source": "AndelP",
                }
            )
    return pd.DataFrame(rows)
