"""Högrisk-sleeve-attribution ([AV]): betalar sig de tematiska/EM-bets:en?

Mäter avkastningsbidraget från EGEN:s högrisk-innehav – kategorierna
``Tillväxtmarknader`` och ``Tematiska & Sektorfonder`` – jämfört med att i stället
ha legat i ACWI (samma proxy som policyindexets aktiebucket) som *alternativkostnad*,
per rapporthorisont. Svarar på frågan "betalar sig mina tematiska bets?".

Ingen ny bucket läggs i policyreferensen. Det är redan avgjort att ingen trovärdig
passiv proxy finns för tematiska/sektorfonder som grupp; ACWI används enbart som
alternativkostnad för hela sleeven (den kapital som annars legat i aktiebucketen).

Bygger på den befintliga kategori-attributionslogiken:

  * REAL-kategoriserierna (``PORT_<portf>_REAL_CAT_*``) ger dagliga
    kategoriavkastningar – samma tidsviktade delportföljer som avsnitt 3 och
    attributionen i avsnitt 5.
  * ``Fact_Portfolio_Alloc_Monthly`` ger kategorivikterna vid varje månadsslut.
    Vikterna hålls konstanta inom månaden och träder i kraft dagen efter
    månadsslutet (samma "månadskonstanta vikt"-konvention som TGT:s
    kategoriavkastningar i :mod:`attribution`). Intra-sleeve-vikterna normeras så
    att sleeven är en värdeviktad delportfölj av de två kategorierna.
  * ACWI-proxyn är policyns aktiebucket (``config.toml`` → ``policy.buckets.Aktier``,
    i praktiken ``BM_ACWI_UCITS``) i SEK.

Per horisont redovisas sleeve-avkastning, ACWI-avkastning, meravkastning
(sleeve − ACWI), sleevens tidssnittade portföljvikt och bidrag ≈ snittvikt ×
meravkastning (alternativkostnaden uttryckt i procentenheter av totalportföljen).
Måttet (kumulativ resp. CAGR) följer horisontens definition, som i avsnitt 2.

Bidraget är en förstaordningsattribution (vikt × relativavkastning), inte en
Carino-länkad exakt dekomponering – tillräckligt för beslutsfrågan och medvetet
enkelt. Allt är deterministiskt och härleds ur BI-filen + kategoriserierna.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.config import POLICY_BUCKETS
from src.portfolio import slug

from .data import BIData
from .window import ONE_YEAR_DAYS, Horizon

# Kategorierna som utgör högrisk-sleeven. Matchas mot Dim_Instrument/Dim_Series.
HIGH_RISK_CATEGORIES: tuple[str, ...] = ("Tillväxtmarknader", "Tematiska & Sektorfonder")


def acwi_series_id() -> str:
    """Series_ID för policyns aktiebucket-proxy (ACWI i SEK), härlett ur config."""
    bench_id = POLICY_BUCKETS.get("Aktier")
    if not bench_id:
        raise ValueError(
            "policy.buckets.Aktier saknas i config.toml – ACWI-proxyn kan inte härledas."
        )
    return f"BM_{slug(bench_id)}"


@dataclass(frozen=True)
class SleevePeriodResult:
    """Sleeve mot ACWI för en horisont; alla avkastningar i horisontens mått."""

    period_key: str
    label: str
    measure: str  # 'cumulative' | 'cagr'
    date_range: str
    sleeve_return: float
    acwi_return: float
    excess: float  # sleeve_return − acwi_return
    avg_weight: float  # sleevens tidssnittade portföljvikt över horisonten
    contribution: float  # ≈ avg_weight × excess (alternativkostnad, p.e. av totalen)


@dataclass(frozen=True)
class SleeveAttribution:
    """Högrisk-sleeve-attribution för en portfölj över rapportfönstret."""

    portfolio: str
    categories: tuple[str, ...]  # högrisk-kategorier som portföljen faktiskt håller
    acwi_series_id: str
    inception: pd.Timestamp
    as_of: pd.Timestamp
    periods: list[SleevePeriodResult]
    missing_categories: tuple[str, ...]  # högrisk-kategorier utan REAL-serie
    flags: list[str] = field(default_factory=list)


def _category_series_ids(data: BIData, portfolio: str) -> dict[str, str]:
    """{kategorinamn: Series_ID} för portföljens REAL_CAT-serier."""
    dim = data.dim_series
    mask = (dim["Portfolio_Key"] == portfolio) & (dim["Is_Category_Series"] == True)  # noqa: E712
    return {row["Category"]: row["Series_ID"] for _, row in dim[mask].iterrows()}


def _daily_returns(data: BIData, series_id: str) -> pd.Series:
    """Dagsavkastningar (RET) för en serie, datumindexerade och sorterade."""
    sub = data.fact_daily[data.fact_daily["Series_ID"] == series_id]
    if sub.empty:
        raise KeyError(f"Serien saknas i Fact_Series_Daily: {series_id}")
    sub = sub.sort_values("Date")
    return pd.Series(
        sub["RET"].to_numpy(dtype=float), index=pd.DatetimeIndex(sub["Date"]), name=series_id
    )


def _monthly_category_weights(
    data: BIData, portfolio: str, categories: list[str]
) -> pd.DataFrame:
    """Månadsslutsvikter per högrisk-kategori (Period_End_Date × kategori)."""
    alloc = data.fact_alloc_monthly[data.fact_alloc_monthly["Portfolio_Key"] == portfolio].copy()
    if alloc.empty:
        raise ValueError(f"Fact_Portfolio_Alloc_Monthly saknar portfölj {portfolio}")
    alloc["Period_End_Date"] = pd.to_datetime(alloc["Period_End_Date"])
    wide = (
        alloc.pivot_table(
            index="Period_End_Date", columns="Category", values="Weight", aggfunc="sum"
        )
        .sort_index()
        .reindex(columns=categories)
        .fillna(0.0)
    )
    return wide


def _daily_sleeve_weights(
    w_month: pd.DataFrame, daily_dates: pd.DatetimeIndex
) -> pd.DataFrame:
    """Månadskonstanta kategorivikter projicerade på dagsdatum.

    En månadsslutsvikt träder i kraft *dagen efter* månadsslutet och hålls konstant
    tills nästa månadsslut – samma konvention som attributionens dagliga
    konstantviktning inom kategori. Dagar före den första viktens ikraftträdande
    (fönstrets allra första partiella månad) faller tillbaka på den första kända
    månadsslutsvikten (ingångsinnehavet).
    """
    w_eff = w_month.copy()
    w_eff.index = w_eff.index + pd.Timedelta(days=1)
    combined_index = daily_dates.union(w_eff.index)
    w_daily = w_eff.reindex(combined_index).ffill().reindex(daily_dates)
    first_row = w_month.iloc[0]
    for col in w_daily.columns:
        w_daily[col] = w_daily[col].fillna(float(first_row[col]))
    return w_daily


def _annualise(total_return: float, span_days: int) -> float:
    years = span_days / ONE_YEAR_DAYS
    if years <= 0:
        return np.nan
    return float((1.0 + total_return) ** (1.0 / years) - 1.0)


def compute_sleeve_attribution(
    data: BIData,
    portfolio: str,
    inception: pd.Timestamp,
    as_of: pd.Timestamp,
    horizons: list[Horizon],
) -> SleeveAttribution | None:
    """Högrisk-sleeve mot ACWI per horisont. None om portföljen saknar sleeve-innehav."""
    cat_ids = _category_series_ids(data, portfolio)
    present = [c for c in HIGH_RISK_CATEGORIES if c in cat_ids]
    missing = tuple(c for c in HIGH_RISK_CATEGORIES if c not in cat_ids)
    if not present:
        return None

    acwi_id = acwi_series_id()
    available_series = set(data.fact_daily["Series_ID"].unique())
    if acwi_id not in available_series:
        raise KeyError(
            f"ACWI-proxyn {acwi_id} saknas i Fact_Series_Daily – kan inte mäta "
            "alternativkostnaden för högrisk-sleeven."
        )

    # Dagliga kategoriavkastningar över fönstret (inception, as_of].
    r_cat = pd.DataFrame({c: _daily_returns(data, cat_ids[c]) for c in present})
    r_cat = r_cat[(r_cat.index > inception) & (r_cat.index <= as_of)].sort_index()
    if r_cat.empty:
        return None
    daily_dates = pd.DatetimeIndex(r_cat.index)

    w_month = _monthly_category_weights(data, portfolio, present)
    w_daily = _daily_sleeve_weights(w_month, daily_dates)

    sleeve_w = w_daily[present].clip(lower=0.0)
    sleeve_tot = sleeve_w.sum(axis=1)
    intra = sleeve_w.div(sleeve_tot.replace(0.0, np.nan), axis=0).fillna(0.0)
    sleeve_ret_daily = (r_cat[present] * intra).sum(axis=1)

    acwi_daily = _daily_returns(data, acwi_id).reindex(daily_dates).fillna(0.0)

    periods: list[SleevePeriodResult] = []
    for h in horizons:
        if not h.available:
            continue
        mask = (daily_dates > h.start) & (daily_dates <= h.end)
        if not mask.any():
            continue
        sr = sleeve_ret_daily[mask]
        ar = acwi_daily[mask]
        wt = sleeve_tot[mask]
        r_sleeve_cum = float((1.0 + sr).prod() - 1.0)
        r_acwi_cum = float((1.0 + ar).prod() - 1.0)
        span_days = int((h.end - h.start).days)
        if h.measure == "cagr":
            r_sleeve = _annualise(r_sleeve_cum, span_days)
            r_acwi = _annualise(r_acwi_cum, span_days)
        else:
            r_sleeve, r_acwi = r_sleeve_cum, r_acwi_cum
        excess = r_sleeve - r_acwi
        avg_weight = float(wt.mean())
        periods.append(
            SleevePeriodResult(
                period_key=h.key,
                label=h.label,
                measure=h.measure,
                date_range=h.date_range(),
                sleeve_return=r_sleeve,
                acwi_return=r_acwi,
                excess=excess,
                avg_weight=avg_weight,
                contribution=avg_weight * excess,
            )
        )

    flags: list[str] = []
    if missing:
        flags.append(
            f"Portföljen håller inte samtliga högrisk-kategorier: saknar {list(missing)}. "
            "Sleeven mäts på de kategorier som faktiskt hålls."
        )
    flags.append(
        "Bidraget är en förstaordningsattribution (snittvikt × meravkastning), inte "
        "en Carino-länkad exakt dekomponering; det visar storleksordningen på "
        "alternativkostnaden, inte en kronexakt bidragspost."
    )
    flags.append(
        "ACWI är alternativkostnad, inte en policybucket för tematiskt/sektor – ingen "
        "trovärdig passiv proxy finns för den gruppen, så ingen ny bucket införs."
    )

    return SleeveAttribution(
        portfolio=portfolio,
        categories=tuple(present),
        acwi_series_id=acwi_id,
        inception=inception,
        as_of=as_of,
        periods=periods,
        missing_categories=missing,
        flags=flags,
    )


def run_sleeve_attribution(
    data: BIData,
    portfolios: list[str],
    inception: pd.Timestamp,
    as_of: pd.Timestamp,
    horizons: list[Horizon],
) -> dict[str, SleeveAttribution]:
    """Sleeve-attribution för de portföljer som faktiskt håller högrisk-innehav."""
    out: dict[str, SleeveAttribution] = {}
    for portfolio in portfolios:
        result = compute_sleeve_attribution(data, portfolio, inception, as_of, horizons)
        if result is not None:
            out[portfolio] = result
    return out
