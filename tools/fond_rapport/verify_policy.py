"""Oberoende korskörning av policyindexens nivåer mot BI-filen.

Körs från projektroten:

    python -m tools.fond_rapport.verify_policy [--input SÖKVÄG] [--price-cache SÖKVÄG]

Verifieringen utnyttjar att policyindexet är buy-and-hold inom kalenderåret
(reset till strategivikterna 1 januari, ingen löpande ombalansering). Då är
nivån vägoberoende inom året och kan räknas direkt ur priserna, utan daglig
kedjning:

    IDX(t) = IDX(ankare_y) · Σ_i w_i · P_i(t) / P_i(ankare_y)

där ankare_y är sista handelsdagen före år y (seriens första dag för det första
året) och P_i är bucketpriserna i SEK. Årsankarnivåerna byggs rekursivt med
samma formel. Pipelinens dagliga kedjning (Σ w(t)·r(t) med driftande vikter) är
matematiskt identisk – jämförelsen görs på varje månadsslut plus sista dagen och
ska bara skilja flyttalsdamm.

Tolerans: relativ avvikelse ≤ 1e-8 per jämförd nivå.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from src.config import (
    BASE_CURRENCY,
    BASE_DIR,
    BI_DATA_OUTPUT_PATH,
    POLICY_BUCKETS,
    POLICY_WEIGHTS,
)
from src.prices import CACHE_PATH

from .data import load_bi_data, series_index

REL_TOLERANCE = 1e-8


def _bucket_prices_sek(prices: pd.DataFrame) -> pd.DataFrame:
    """Bucketpriser i SEK ur prismatrisen, ticker/valuta via Benchmarks-uppslag."""
    from src.io_excel import load_inputs
    from src.config import PATH_TRANSAKTIONER, PATH_FONDER

    benchmarks = load_inputs(PATH_TRANSAKTIONER, PATH_FONDER)["benchmarks"]
    out: dict[str, pd.Series] = {}
    for bucket, benchmark_id in POLICY_BUCKETS.items():
        row = benchmarks[benchmarks["Benchmark_ID"].astype(str).str.strip() == benchmark_id]
        if row.empty:
            raise ValueError(f"Benchmark_ID {benchmark_id} saknas i Benchmarks-tabellen")
        ticker = str(row.iloc[0]["Yahoo_Ticker"]).strip()
        ccy = str(row.iloc[0].get("Price_Currency", "") or "").strip().upper()
        series = prices[ticker]
        if ccy and ccy != BASE_CURRENCY:
            series = series * prices[f"{ccy}{BASE_CURRENCY}=X"]
        out[bucket] = series
    return pd.DataFrame(out).dropna(how="any")


def independent_policy_levels(
    prices_sek: pd.DataFrame,
    weights: dict[str, float],
    dates: pd.DatetimeIndex,
    base_value: float,
) -> pd.Series:
    """Policyindexnivåer på ``dates`` via buy-and-hold-identiteten per kalenderår."""
    px = prices_sek.reindex(dates).dropna(how="any")
    if px.empty:
        raise ValueError("Prismatrisen täcker inte seriens datum")

    w = pd.Series(weights, dtype=float).reindex(px.columns)
    levels: dict[pd.Timestamp, float] = {}
    anchor_date = px.index[0]
    anchor_level = base_value
    for year, group in px.groupby(px.index.year):
        rel = group.div(px.loc[anchor_date]) @ w
        for date, value in (anchor_level * rel).items():
            levels[date] = float(value)
        # Nästa års ankare: årets sista handelsdag och dess nivå.
        anchor_date = group.index[-1]
        anchor_level = levels[anchor_date]
    return pd.Series(levels).sort_index()


def _comparison_dates(idx: pd.Series) -> pd.DatetimeIndex:
    """Månadsslut (sista handelsdag per månad) plus seriens sista dag."""
    month_ends = idx.groupby([idx.index.year, idx.index.month]).apply(lambda s: s.index.max())
    dates = sorted(set(month_ends.tolist()) | {idx.index.max()})
    return pd.DatetimeIndex(dates)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Korskör policyindexnivåerna oberoende.")
    parser.add_argument("--input", type=Path, default=BI_DATA_OUTPUT_PATH)
    parser.add_argument("--price-cache", type=Path, default=BASE_DIR / CACHE_PATH)
    args = parser.parse_args(argv)

    data = load_bi_data(args.input)
    prices = pd.read_parquet(args.price_cache)
    prices.index = pd.to_datetime(prices.index)
    prices_sek = _bucket_prices_sek(prices)

    all_ok = True
    for portfolio, weights in POLICY_WEIGHTS.items():
        series_id = f"POLICY_{str(portfolio).upper()}"
        idx = series_index(data, series_id)
        base_value = float(idx.iloc[0])
        check_dates = _comparison_dates(idx)

        independent = independent_policy_levels(
            prices_sek, weights, pd.DatetimeIndex(idx.index), base_value
        )
        compared = pd.DataFrame(
            {"pipeline": idx.reindex(check_dates), "oberoende": independent.reindex(check_dates)}
        ).dropna()
        rel_diff = (compared["pipeline"] - compared["oberoende"]).abs() / compared["oberoende"]
        worst = float(rel_diff.max())
        ok = worst <= REL_TOLERANCE
        all_ok &= ok
        print(
            f"{series_id}: {len(compared)} nivåer jämförda (månadsslut + sista dag), "
            f"max relativ avvikelse {worst:.2e} (tolerans {REL_TOLERANCE:.0e}) "
            f"{'OK' if ok else 'AVVIKER'}"
        )
        if not ok:
            failing = compared[rel_diff > REL_TOLERANCE]
            print(failing.to_string(), file=sys.stderr)

    print("\nResultat:", "OK – oberoende beräkning återger pipelinens nivåer." if all_ok else "AVVIKELSER finns – se ovan.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
