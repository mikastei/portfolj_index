"""Passiva policyreferenser: tvåbucketsindex (Aktier/Räntor) med årsvis ombalansering.

Referensindexen speglar det enda avsiktliga strategivalet – fördelningen mellan
aktier och räntor. Geografi-, EM- och tematiska val ska hamna i alfa; därför är
aktiebucketen MSCI ACWI (inkl. EM), inte separata World/EM-buckets.

Konstruktion:

- Två buckets, definierade i config.toml ``[policy] buckets`` som pekare till
  Benchmark_ID-rader i transaktioner.xlsx (Benchmarks-tabellen). Priserna hämtas
  med pipelinens ordinarie Yahoo-nedladdning (auto_adjust => total return) och
  FX-konverteras här till basvalutan (SEK).
- Fasta strategivikter per portfölj (``[policy.weights]``), reset till
  strategivikterna vid årsskiftet (första handelsdagen på det nya året får sin
  avkastning på strategivikterna – ombalanseringen sker "1 januari"), fri drift
  inom året utan löpande ombalansering.
- Viktsumman kontrolleras mot 1,0 varje dag (assertion).

Serier som produceras (in i Series_Definition/Master_TimeSeries_Long och vidare
till BI-stjärnschemat):

- ``POLICY_<PORTFÖLJ>`` – referensindexet per portfölj (t.ex. POLICY_EGEN 90/10).
- ``POLICY_BUCKET_AKTIER`` – aktiebucketen i SEK som egen serie. Den skiljer sig
  från BM-serien för samma ticker: BM-serier byggs i lokal prisvaluta (USD för
  ACWI), bucketserien är FX-konverterad till SEK.
- Räntebucketen får ingen egen POLICY-serie: dess proxy är SEK-noterad, så
  BM-serien (BM_BM_SHORT_CORP_BOND) är redan identisk med bucketen i SEK.

Framtida analysdimension (används INTE i referensindexen): 4-bucket-mappningen
för allokeringsattribution – Räntor & Lågrisk → Räntor; Tillväxtmarknader →
Tillväxt; geografi Sverige → Sverige; övrigt → Global.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .prices import returns_from_prices
from .portfolio import _series_frame, slug

logger = logging.getLogger(__name__)

# Viktsumman kontrolleras varje dag mot 1,0 inom denna tolerans.
WEIGHT_SUM_TOL = 1e-9

AKTIER_BUCKET_SERIES_ID = "POLICY_BUCKET_AKTIER"


def _benchmark_row(benchmarks: pd.DataFrame, benchmark_id: str) -> pd.Series:
    match = benchmarks[benchmarks["Benchmark_ID"].astype(str).str.strip() == benchmark_id]
    if match.empty:
        raise ValueError(
            f"Policybucket pekar på Benchmark_ID '{benchmark_id}' som saknas i Benchmarks-tabellen"
        )
    return match.iloc[0]


def _bucket_prices_sek(
    benchmarks: pd.DataFrame,
    prices: pd.DataFrame,
    benchmark_id: str,
    base_currency: str,
) -> pd.Series:
    """Bucketproxyns prisserie i basvalutan (SEK), via FX-serien i prismatrisen."""
    row = _benchmark_row(benchmarks, benchmark_id)
    ticker = str(row["Yahoo_Ticker"]).strip()
    if ticker not in prices.columns:
        raise ValueError(f"Policybucket {benchmark_id}: ticker {ticker} saknas i prismatrisen")
    price_local = prices[ticker]

    ccy = str(row.get("Price_Currency", "") or "").strip().upper()
    if not ccy or ccy == base_currency:
        return price_local
    fx_ticker = f"{ccy}{base_currency}=X"
    if fx_ticker not in prices.columns:
        raise ValueError(f"Policybucket {benchmark_id}: FX-serie {fx_ticker} saknas i prismatrisen")
    return price_local * prices[fx_ticker]


def policy_return_path(
    bucket_returns: pd.DataFrame,
    strategy_weights: dict[str, float],
) -> tuple[pd.Series, pd.DataFrame]:
    """Daglig policyavkastning och viktbana för fasta vikter med årsvis reset.

    ``bucket_returns`` har en kolumn per bucket (dagliga avkastningar i SEK).
    Vikterna resettas till strategivikterna inför första handelsdagen varje
    kalenderår och driftar däremellan med respektive buckets avkastning.
    Returnerar (dagsavkastning, viktbana) där viktbanan innehåller de vikter som
    ligger bakom respektive dags avkastning (start-av-dag-vikter).
    """
    columns = list(bucket_returns.columns)
    missing = [c for c in columns if c not in strategy_weights]
    if missing:
        raise ValueError(f"Strategivikt saknas för bucket(s): {missing}")
    w_target = np.array([float(strategy_weights[c]) for c in columns])
    if abs(float(w_target.sum()) - 1.0) > WEIGHT_SUM_TOL:
        raise ValueError(f"Strategivikterna måste summera till 1.0 (summa={w_target.sum():.12f})")

    index = bucket_returns.index
    rets = bucket_returns.to_numpy(dtype=float)
    port_ret = np.zeros(len(index))
    weight_path = np.zeros_like(rets)

    w = w_target.copy()
    prev_year: int | None = None
    for i, date in enumerate(index):
        if prev_year is not None and date.year != prev_year:
            # Reset 1 januari: nya årets första handelsdag får strategivikterna.
            w = w_target.copy()
        weight_path[i] = w
        assert abs(float(w.sum()) - 1.0) <= WEIGHT_SUM_TOL, (
            f"Policyvikter summerar inte till 1.0 per {pd.Timestamp(date).date()}: {w.sum():.15f}"
        )
        r = rets[i]
        port_ret[i] = float(w @ r)
        # Fri drift inom året: vikterna följer respektive buckets avkastning.
        w = w * (1.0 + r)
        w = w / float(w.sum())
        prev_year = int(date.year)

    return (
        pd.Series(port_ret, index=index),
        pd.DataFrame(weight_path, index=index, columns=columns),
    )


def build_policy_series(
    benchmarks: pd.DataFrame,
    portfolio_metadata: pd.DataFrame,
    prices: pd.DataFrame,
    base_currency: str,
    buckets: dict[str, str],
    weights_by_portfolio: dict[str, dict[str, float]],
) -> dict[str, pd.DataFrame]:
    """Policyserierna (RET/IDX/DD) per portfölj + aktiebucketen i SEK.

    Serierna startar vid portföljernas gemensamma Index_Start_Date med samma
    basindexvärde som övriga serier; fond-rapporten rebaserar sedan till EGEN:s
    inception via sin ordinarie fönsterlogik.
    """
    if not buckets or not weights_by_portfolio:
        logger.info("Policykonfiguration saknas – inga policyserier byggs")
        return {}

    start_date = pd.to_datetime(portfolio_metadata["Index_Start_Date"], errors="coerce").min()
    initial_index_value = float(
        pd.to_numeric(portfolio_metadata["Initial_Index_Value"], errors="coerce").dropna().iloc[0]
    )

    prices_sek = pd.DataFrame(
        {
            bucket: _bucket_prices_sek(benchmarks, prices, benchmark_id, base_currency)
            for bucket, benchmark_id in buckets.items()
        }
    ).dropna(how="any")
    prices_sek = prices_sek[prices_sek.index >= start_date]
    if prices_sek.empty:
        raise ValueError("Policybuckets saknar gemensam prishistorik efter Index_Start_Date")
    bucket_returns = returns_from_prices(prices_sek)

    out: dict[str, pd.DataFrame] = {}
    for portfolio, weights in weights_by_portfolio.items():
        ret, weight_path = policy_return_path(bucket_returns, weights)
        series_id = f"POLICY_{slug(portfolio)}"
        out[series_id] = _series_frame(ret, initial_index_value)
        logger.info(
            "Policyserie %s: %s rader %s – %s, vikter %s, viktsumma OK varje dag",
            series_id,
            len(ret),
            ret.index[0].date(),
            ret.index[-1].date(),
            {k: round(v, 4) for k, v in weights.items()},
        )
        del weight_path  # viktbanan konsumeras i tester/verifiering, inte här

    # Aktiebucketen i SEK som egen serie (BM-serien för samma ticker är i USD).
    # Räntebucketens proxy är SEK-noterad – BM-serien är redan bucketen i SEK.
    out[AKTIER_BUCKET_SERIES_ID] = _series_frame(bucket_returns["Aktier"], initial_index_value)
    return out


def build_policy_series_definition(
    benchmarks: pd.DataFrame,
    portfolio_metadata: pd.DataFrame,
    buckets: dict[str, str],
    weights_by_portfolio: dict[str, dict[str, float]],
) -> pd.DataFrame:
    """Series_Definition-rader för policyserierna (samma kolumner som övriga)."""
    if not buckets or not weights_by_portfolio:
        return pd.DataFrame()

    start_date = pd.to_datetime(portfolio_metadata["Index_Start_Date"], errors="coerce").min()
    initial_index_value = float(
        pd.to_numeric(portfolio_metadata["Initial_Index_Value"], errors="coerce").dropna().iloc[0]
    )

    def _base_row() -> dict[str, object]:
        return {
            "Series_Type": "POLICY",
            "Portfolio_Name": None,
            "Variant": None,
            "Benchmark_ID": None,
            "Yahoo_Ticker": None,
            "ISIN": None,
            "Display_Name": None,
            "Price_Currency": None,
            "Instrument_Type": None,
            "Category": None,
            "Geography": None,
            "Include_From_Date": start_date,
            "Index_Start_Date": start_date,
            "Initial_Index_Value": initial_index_value,
        }

    rows: list[dict[str, object]] = []
    for portfolio, weights in weights_by_portfolio.items():
        aktier = float(weights.get("Aktier", 0.0))
        rantor = float(weights.get("Rantor", 0.0))
        row = _base_row()
        row.update(
            {
                "Series_ID": f"POLICY_{slug(portfolio)}",
                "Portfolio_Name": str(portfolio),
                "Display_Name": (
                    f"Policyreferens {portfolio} ({aktier * 100:.0f}/{rantor * 100:.0f})"
                ),
                "Price_Currency": "SEK",
            }
        )
        rows.append(row)

    aktier_row = _benchmark_row(benchmarks, buckets["Aktier"])
    row = _base_row()
    row.update(
        {
            "Series_ID": AKTIER_BUCKET_SERIES_ID,
            "Benchmark_ID": buckets["Aktier"],
            "Yahoo_Ticker": str(aktier_row["Yahoo_Ticker"]).strip(),
            "Display_Name": f"Policybucket Aktier ({str(aktier_row['Yahoo_Ticker']).strip()} i SEK)",
            "Price_Currency": "SEK",
        }
    )
    rows.append(row)
    return pd.DataFrame(rows)
