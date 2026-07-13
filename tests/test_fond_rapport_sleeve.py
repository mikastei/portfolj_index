"""Tester för högrisk-sleeve-attributionen (tools/fond_rapport/sleeve.py, [AV]).

Täcker: ACWI-proxyns härledning ur config, den värdeviktade sleeve-avkastningen mot
ACWI per horisont, bidragsidentiteten (snittvikt × meravkastning), enkategori-fallet
(sleeve = kategoriserien själv), saknade kategorier, samt degradering när portföljen
saknar högrisk-innehav eller ACWI-proxyn saknas. Allt deterministiskt med konstant-
avkastnings-serier så att facit kan skrivas analytiskt.
"""

import numpy as np
import pandas as pd
import pytest

from tools.fond_rapport.data import BIData
from tools.fond_rapport.sleeve import (
    HIGH_RISK_CATEGORIES,
    acwi_series_id,
    compute_sleeve_attribution,
    run_sleeve_attribution,
)
from tools.fond_rapport.window import ONE_YEAR_DAYS, Horizon

ACWI_ID = acwi_series_id()
TM = "Tillväxtmarknader"
TEMA = "Tematiska & Sektorfonder"


def _daily_frame(series_id: str, dates: pd.DatetimeIndex, ret: float) -> pd.DataFrame:
    idx = 100.0 * (1.0 + ret) ** np.arange(len(dates))
    return pd.DataFrame(
        {"Series_ID": series_id, "Date": dates, "RET": ret, "IDX": idx, "DD": 0.0}
    )


def _empty() -> pd.DataFrame:
    return pd.DataFrame()


def _make_bi(
    dates: pd.DatetimeIndex,
    cat_returns: dict[str, float],
    acwi_ret: float,
    weights: dict[str, float],
    period_ends: list[str],
    portfolio: str = "TEST",
) -> BIData:
    """Syntetisk BIData: en kategoriserie per kategori + ACWI + månadsvikter."""
    cat_series_id = {cat: f"PORT_{portfolio}_REAL_CAT_{i}" for i, cat in enumerate(cat_returns)}
    daily_parts = [
        _daily_frame(cat_series_id[cat], dates, ret) for cat, ret in cat_returns.items()
    ]
    daily_parts.append(_daily_frame(ACWI_ID, dates, acwi_ret))
    fact_daily = pd.concat(daily_parts, ignore_index=True)

    dim_series = pd.DataFrame(
        [
            {
                "Series_ID": cat_series_id[cat],
                "Portfolio_Key": portfolio,
                "Is_Category_Series": True,
                "Category": cat,
            }
            for cat in cat_returns
        ]
    )

    alloc_rows = []
    for pe in period_ends:
        for cat, w in weights.items():
            alloc_rows.append(
                {
                    "Portfolio_Key": portfolio,
                    "Period_End_Date": pd.Timestamp(pe),
                    "Category": cat,
                    "Weight": w,
                }
            )
    fact_alloc_monthly = pd.DataFrame(alloc_rows)

    return BIData(
        dim_date=_empty(),
        dim_portfolio=_empty(),
        dim_series=dim_series,
        dim_instrument=_empty(),
        fact_daily=fact_daily,
        fact_kpi=_empty(),
        fact_alloc=_empty(),
        fact_alloc_monthly=fact_alloc_monthly,
    )


def _horizon(start, end, measure="cumulative", key="Since_Start", label="Sedan start") -> Horizon:
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    return Horizon(
        key=key,
        label=label,
        start=start,
        end=end,
        available=True,
        measure=measure,
        span_years=(end - start).days / ONE_YEAR_DAYS,
        note="",
    )


def test_acwi_series_id_resolved_from_config():
    # config.toml: policy.buckets.Aktier = "BM_ACWI_UCITS" → Series_ID BM_BM_ACWI_UCITS.
    assert acwi_series_id() == "BM_BM_ACWI_UCITS"
    assert HIGH_RISK_CATEGORIES == (TM, TEMA)


def test_value_weighted_sleeve_return_and_contribution_identity():
    dates = pd.bdate_range("2025-02-03", periods=40)
    r_tm, r_tema, r_acwi = 0.001, -0.0005, 0.0002
    bi = _make_bi(
        dates,
        {TM: r_tm, TEMA: r_tema},
        r_acwi,
        {TM: 0.20, TEMA: 0.10},
        ["2025-01-31", "2025-02-28"],
    )
    # Fönstret rymmer alla 40 dagar (start dagen före första datum).
    h = _horizon(dates[0] - pd.Timedelta(days=1), dates[-1])
    sa = compute_sleeve_attribution(bi, "TEST", pd.Timestamp("2025-01-31"), dates[-1], [h])
    assert sa is not None
    assert sa.categories == (TM, TEMA)
    assert sa.missing_categories == ()
    p = sa.periods[0]

    n = len(dates)
    # Intra-sleeve-vikter: TM 2/3, TEMA 1/3 → daglig sleeve-avkastning konstant.
    sleeve_daily = (2 / 3) * r_tm + (1 / 3) * r_tema
    exp_sleeve = (1.0 + sleeve_daily) ** n - 1.0
    exp_acwi = (1.0 + r_acwi) ** n - 1.0
    assert p.sleeve_return == pytest.approx(exp_sleeve, rel=1e-12)
    assert p.acwi_return == pytest.approx(exp_acwi, rel=1e-12)
    assert p.avg_weight == pytest.approx(0.30, rel=1e-12)
    assert p.excess == pytest.approx(exp_sleeve - exp_acwi, rel=1e-12)
    # Bidragsidentiteten.
    assert p.contribution == pytest.approx(p.avg_weight * p.excess, rel=1e-12)


def test_cagr_horizon_annualises():
    dates = pd.bdate_range("2024-01-01", periods=400)  # > 1 år
    bi = _make_bi(
        dates, {TM: 0.0004, TEMA: 0.0004}, 0.0002, {TM: 0.15, TEMA: 0.15}, ["2023-12-29"]
    )
    h = _horizon(dates[0] - pd.Timedelta(days=1), dates[-1], measure="cagr", key="1Y", label="1 år")
    sa = compute_sleeve_attribution(bi, "TEST", dates[0] - pd.Timedelta(days=1), dates[-1], [h])
    p = sa.periods[0]
    n = len(dates)
    cum_sleeve = (1.0 + 0.0004) ** n - 1.0
    span_days = (h.end - h.start).days
    exp = (1.0 + cum_sleeve) ** (ONE_YEAR_DAYS / span_days) - 1.0
    assert p.measure == "cagr"
    assert p.sleeve_return == pytest.approx(exp, rel=1e-12)


def test_single_category_sleeve_equals_that_category():
    # Bara Tillväxtmarknader hålls → sleeve-avkastning = kategoriseriens egen.
    dates = pd.bdate_range("2025-03-03", periods=20)
    bi = _make_bi(dates, {TM: 0.0007}, 0.0002, {TM: 0.10}, ["2025-02-28"])
    h = _horizon(dates[0] - pd.Timedelta(days=1), dates[-1])
    sa = compute_sleeve_attribution(bi, "TEST", pd.Timestamp("2025-02-28"), dates[-1], [h])
    assert sa.categories == (TM,)
    assert sa.missing_categories == (TEMA,)
    p = sa.periods[0]
    assert p.sleeve_return == pytest.approx((1.0007) ** len(dates) - 1.0, rel=1e-12)
    assert p.avg_weight == pytest.approx(0.10, rel=1e-12)


def test_returns_none_without_high_risk_categories():
    dates = pd.bdate_range("2025-03-03", periods=10)
    bi = _make_bi(dates, {"Breda fonder": 0.0003}, 0.0002, {"Breda fonder": 0.5}, ["2025-02-28"])
    h = _horizon(dates[0] - pd.Timedelta(days=1), dates[-1])
    assert compute_sleeve_attribution(bi, "TEST", dates[0], dates[-1], [h]) is None


def test_missing_acwi_proxy_raises():
    dates = pd.bdate_range("2025-03-03", periods=10)
    bi = _make_bi(dates, {TM: 0.0007}, 0.0002, {TM: 0.10}, ["2025-02-28"])
    # Ta bort ACWI-serien ur fakta.
    bi.fact_daily.drop(bi.fact_daily[bi.fact_daily["Series_ID"] == ACWI_ID].index, inplace=True)
    h = _horizon(dates[0] - pd.Timedelta(days=1), dates[-1])
    with pytest.raises(KeyError, match="ACWI-proxyn"):
        compute_sleeve_attribution(bi, "TEST", dates[0], dates[-1], [h])


def test_unavailable_horizon_skipped():
    dates = pd.bdate_range("2025-03-03", periods=10)
    bi = _make_bi(dates, {TM: 0.0007}, 0.0002, {TM: 0.10}, ["2025-02-28"])
    avail = _horizon(dates[0] - pd.Timedelta(days=1), dates[-1])
    gated = Horizon(
        key="3Y", label="3 år", start=dates[0], end=dates[-1], available=False,
        measure="cagr", span_years=3.0, note="Kräver 3 års data.",
    )
    sa = compute_sleeve_attribution(bi, "TEST", dates[0], dates[-1], [gated, avail])
    assert [p.period_key for p in sa.periods] == ["Since_Start"]


def test_run_sleeve_attribution_filters_portfolios_without_sleeve():
    dates = pd.bdate_range("2025-03-03", periods=10)
    bi = _make_bi(dates, {TM: 0.0007}, 0.0002, {TM: 0.10}, ["2025-02-28"], portfolio="TEST")
    h = _horizon(dates[0] - pd.Timedelta(days=1), dates[-1])
    out = run_sleeve_attribution(bi, ["TEST", "OTHER"], dates[0], dates[-1], [h])
    assert set(out) == {"TEST"}
