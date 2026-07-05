"""Tester för fond-rapportens avgifts- och kostnadsanalys (Steg 2b).

Använder syntetisk data så att testerna är deterministiska och inte beror på
produktions-BI-filen. TER anges i Dim_Instrument som procent (1.0 = 1 %/år);
costs-modulen räknar internt i fraktioner.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tools.fond_rapport.costs import (
    _courtage_in_window,
    _period_durations,
    compute_costs,
    compute_courtage,
    compute_portfolio_ter,
    verify_costs,
)
from tools.fond_rapport.data import BIData

EMPTY = pd.DataFrame()


def _dim_instrument() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Instrument_Key": ["A", "B", "C", "IDX_GLOBAL"],
            "ISIN": ["ISIN_A", "ISIN_B", "ISIN_C", None],
            "Display_Name": ["Fond A", "Fond B", "Fond C", "Global indexfond"],
            "Category": ["Breda fonder", "Räntor & Lågrisk", "Breda fonder", "Breda fonder"],
            "Geography": ["Global", "Sverige", "Global", "Global"],
            "TER": [1.0, 0.5, np.nan, 0.2],
            "TER_Status": ["ok", "ok", "no_data", "ok"],
        }
    )


def _alloc_monthly(portfolio: str = "EGEN") -> pd.DataFrame:
    rows = []
    # Periodslut 1 (2024-01-31): A 50 %, B 25 %, C 25 % – täckning 75 %.
    for key, weight in (("A", 0.50), ("B", 0.25), ("C", 0.25)):
        rows.append((portfolio, key, pd.Timestamp("2024-01-31"), weight, 1_000_000.0))
    # Periodslut 2 (2024-02-29): A 100 % – full täckning.
    rows.append((portfolio, "A", pd.Timestamp("2024-02-29"), 1.0, 2_000_000.0))
    return pd.DataFrame(
        rows,
        columns=["Portfolio_Key", "Instrument_Key", "Period_End_Date", "Weight", "Portfolio_MV_SEK"],
    ).assign(ISIN="x", Display_Name="x", Category="Breda fonder")


def _snapshot(portfolio: str = "EGEN") -> pd.DataFrame:
    rows = []
    for variant, spec in (
        ("REAL", [("A", 0.5), ("B", 0.5)]),
        ("TGT", [("A", 1.0)]),
    ):
        for key, weight in spec:
            rows.append((portfolio, f"PORT_{portfolio}_{variant}", key, weight))
    return pd.DataFrame(
        rows, columns=["Portfolio_Key", "Series_ID", "Instrument_Key", "Weight"]
    )


def _courtage() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Portfolio_Key": ["EGEN", "EGEN", "EGEN"],
            "Instrument_Key": ["A", "A", "B"],
            "Display_Name": ["Fond A", "Fond A", "Fond B"],
            "Category": ["Breda fonder", "Breda fonder", "Räntor & Lågrisk"],
            "Period_End_Date": pd.to_datetime(["2023-12-31", "2024-01-31", "2024-03-31"]),
            "Courtage_SEK": [99.0, 100.0, 50.0],
            "Txn_Count": [1, 2, 1],
        }
    )


def _bidata(portfolios: tuple[str, ...] = ("EGEN",)) -> BIData:
    alloc_monthly = pd.concat([_alloc_monthly(p) for p in portfolios], ignore_index=True)
    snapshot = pd.concat([_snapshot(p) for p in portfolios], ignore_index=True)
    return BIData(
        dim_date=EMPTY,
        dim_portfolio=EMPTY,
        dim_series=EMPTY,
        dim_instrument=_dim_instrument(),
        fact_daily=EMPTY,
        fact_kpi=EMPTY,
        fact_alloc=snapshot,
        fact_alloc_monthly=alloc_monthly,
        fact_courtage=_courtage(),
    )


INCEPTION = pd.Timestamp("2024-01-01")
AS_OF = pd.Timestamp("2024-02-29")


# --- tidsviktning ---------------------------------------------------------------


def test_period_durations_backward_convention():
    period_ends = pd.DatetimeIndex(["2024-01-31", "2024-02-29"])
    days = _period_durations(period_ends, INCEPTION, AS_OF)
    assert days.tolist() == [30.0, 29.0]


def test_period_durations_extends_last_period_to_as_of():
    period_ends = pd.DatetimeIndex(["2024-01-31", "2024-02-29"])
    days = _period_durations(period_ends, INCEPTION, pd.Timestamp("2024-03-10"))
    assert days.tolist() == [30.0, 39.0]


# --- viktad TER -----------------------------------------------------------------


def test_weighted_ter_renorm_lower_and_coverage():
    result = compute_portfolio_ter(_bidata(), "EGEN", INCEPTION, AS_OF)
    first = result.monthly.iloc[0]
    # Täckt vikt 75 %; renorm = (0,50·1,0 % + 0,25·0,5 %)/0,75; undre gräns /1,0.
    assert first["Coverage"] == pytest.approx(0.75)
    assert first["TER_Renorm"] == pytest.approx(0.00625 / 0.75)
    assert first["TER_Lower"] == pytest.approx(0.00625)
    second = result.monthly.iloc[1]
    assert second["Coverage"] == pytest.approx(1.0)
    assert second["TER_Renorm"] == pytest.approx(0.01)


def test_time_weighted_ter_uses_calendar_days():
    result = compute_portfolio_ter(_bidata(), "EGEN", INCEPTION, AS_OF)
    expected_renorm = (0.00625 / 0.75 * 30 + 0.01 * 29) / (30 + 29)
    expected_lower = (0.00625 * 30 + 0.01 * 29) / (30 + 29)
    expected_coverage = (0.75 * 30 + 1.0 * 29) / (30 + 29)
    assert result.ter_tw_renorm == pytest.approx(expected_renorm)
    assert result.ter_tw_lower == pytest.approx(expected_lower)
    assert result.coverage_tw == pytest.approx(expected_coverage)
    assert result.uncovered_periods == 0


def test_zero_coverage_period_excluded_from_renorm_but_bounds_lower():
    data = _bidata()
    alloc = data.fact_alloc_monthly.copy()
    # Gör första periodslutet helt otäckt: bara C (utan TER).
    alloc = alloc[~((alloc["Period_End_Date"] == "2024-01-31") & alloc["Instrument_Key"].isin(["A", "B"]))]
    alloc.loc[alloc["Period_End_Date"] == "2024-01-31", "Weight"] = 1.0
    data = BIData(
        dim_date=EMPTY, dim_portfolio=EMPTY, dim_series=EMPTY,
        dim_instrument=_dim_instrument(), fact_daily=EMPTY, fact_kpi=EMPTY,
        fact_alloc=_snapshot(), fact_alloc_monthly=alloc, fact_courtage=_courtage(),
    )
    result = compute_portfolio_ter(data, "EGEN", INCEPTION, AS_OF)
    assert result.uncovered_periods == 1
    assert np.isnan(result.monthly.iloc[0]["TER_Renorm"])
    # Renorm-snittet bygger enbart på den täckta perioden …
    assert result.ter_tw_renorm == pytest.approx(0.01)
    # … medan undre gränsen räknar den otäckta perioden som 0.
    assert result.ter_tw_lower == pytest.approx((0.0 * 30 + 0.01 * 29) / 59)


def test_missing_instruments_are_reported():
    result = compute_portfolio_ter(_bidata(), "EGEN", INCEPTION, AS_OF)
    assert result.missing["Instrument_Key"].tolist() == ["C"]
    assert result.missing.iloc[0]["Maxvikt"] == pytest.approx(0.25)


def test_snapshot_ter_and_coverage():
    result = compute_portfolio_ter(_bidata(), "EGEN", INCEPTION, AS_OF)
    assert result.snapshot_ter["REAL"] == pytest.approx(0.0075)  # 50/50 av 1,0 % och 0,5 %
    assert result.snapshot_ter["TGT"] == pytest.approx(0.01)
    assert result.snapshot_coverage["REAL"] == pytest.approx(1.0)


# --- courtage --------------------------------------------------------------------


def test_courtage_window_excludes_buckets_before_inception():
    ct = _courtage_in_window(_courtage(), INCEPTION, AS_OF)
    # 2023-12-bucketen slutar före inception; 2024-01 ingår.
    assert ct["Period_End_Date"].dt.strftime("%Y-%m").tolist() == ["2024-01"]


def test_courtage_window_includes_bucket_containing_as_of():
    ct = _courtage_in_window(_courtage(), INCEPTION, pd.Timestamp("2024-03-10"))
    # Mars-bucketens månadsstart (1 mars) ligger på/före as-of 10 mars.
    assert ct["Courtage_SEK"].sum() == pytest.approx(150.0)


def test_courtage_pct_per_year_uses_day_weighted_mv():
    summary = compute_courtage(_bidata(), "EGEN", INCEPTION, AS_OF)
    assert summary.total_sek == pytest.approx(100.0)
    assert summary.n_txn == 2
    avg_mv = (1_000_000.0 * 30 + 2_000_000.0 * 29) / 59
    years = 59 / 365.25
    assert summary.avg_mv_sek == pytest.approx(avg_mv)
    assert summary.pct_per_year == pytest.approx(100.0 / (avg_mv * years))


# --- samlad analys och verifiering -------------------------------------------------


def test_compute_costs_fee_gaps_and_verification():
    data = _bidata(portfolios=("EGEN", "PA"))
    costs = compute_costs(data, INCEPTION, AS_OF)
    # Identiska syntetiska portföljer: ingen TER-differens EGEN mot PA.
    assert costs.fee_gap_egen_pa == pytest.approx(0.0)
    # EGEN tidsviktat mot egen TGT-lista (1,0 %).
    expected_tw = (0.00625 / 0.75 * 30 + 0.01 * 29) / 59
    assert costs.fee_gap_egen_tgt == pytest.approx(expected_tw - 0.01)
    assert costs.fee_gap_egen_tgt_cum == pytest.approx(costs.fee_gap_egen_tgt * 59 / 365.25)
    assert costs.cheapest_broad_global == ("Global indexfond", pytest.approx(0.002))
    assert costs.pa_courtage_rows == 0
    assert any("saknar TER" in flag for flag in costs.flags)

    verification = verify_costs(data, costs)
    assert bool(verification["OK"].all())
