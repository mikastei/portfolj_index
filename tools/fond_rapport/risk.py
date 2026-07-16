"""Diversifieringseffekt och riskreduktion (styrdokumentets portföljriskavsnitt).

Definitioner (02_Nyckeltalsdefinitioner.md):

- **Summerad risk** = Σ wᵢ·σᵢ – viktat snitt av komponenternas annualiserade
  dagliga standardavvikelse.
- **Portföljrisk** = √(wᵀ·Σ·w). I rapporten används den *realiserade* REAL-volen
  (annualiserad std av portföljens dagliga avkastning över fönstret) – exakt
  samma tal som Vol-kolumnen i KPI-tabellen. Den är den kovariansbaserade risken
  med portföljens faktiska dagliga vikter; att den sammanfaller med √(w̄ᵀΣw̄) för
  de tidssnittade vikterna verifieras numeriskt per körning (``model_gap``).
- **Diversifieringseffekt** = Summerad risk − Portföljrisk (procentenheter).
- **Riskreduktion** = 1 − Portföljrisk / Summerad risk.

Fönsterkonsistens: komponenternas σᵢ räknas på dagliga SEK-avkastningar ur
samma prismatris som serierna byggs av, över exakt samma (start, as_of]-fönster
och med samma annualisering (ddof=1, √252) som portföljens Vol i metrics.py.

Vikter: dagviktat snitt av månadsvikterna i ``Fact_Portfolio_Alloc_Monthly``
(REAL) enligt samma konvention som costs.py – vikterna vid ett periodslut får
representera den gångna perioden; ligger fönsterslutet efter sista periodslutet
förlängs den sista viktvektorn.

Instrument som saknar prishistorik i fönstret (NaN i prismatrisen före fondens
första notering) **exkluderas och kvarvarande vikter renormaliseras**;
exkluderingarna redovisas i resultatet och i rapporten. Alternativet – att
kräva minsta täckning och avstå från beräkning – förkastades eftersom snitt-
vikten för ett sent tillkommet innehav redan är proportionellt liten.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.config import TRADING_DAYS_PER_YEAR

from .attribution import _fund_daily_returns_sek
from .data import BIData
from .metrics import WindowSlice
from .window import Horizon

# Horisonter där de två nyckeltalen redovisas (matchar KPI-blockets tabeller).
RISK_HORIZON_KEYS = ["Since_Start", "1Y"]

# Komponentavkastningar hämtas med lookback före fönsterstart så att första
# handelsdagens avkastning refererar senaste stängning på eller före start –
# samma bas-konvention som WindowSlice.
PRICE_LOOKBACK_DAYS = 7

# |√(w̄ᵀΣw̄) − realiserad vol| över detta varnas det för: snittvikterna
# representerar då inte längre den faktiska viktbanan (kraftig drift i fönstret).
MODEL_GAP_WARN = 0.015  # 1,5 procentenheter

RISK_REDUCTION_LEVELS = [
    (0.15, "svag spridning"),
    (0.25, "god spridning"),
]
RISK_REDUCTION_TOP_LEVEL = "stark spridning"


def risk_reduction_level(risk_reduction: float) -> str:
    """Tolkningsetikett enligt styrdokumentet: <15 % svag, 15–25 god, >25 stark."""
    if pd.isna(risk_reduction):
        return "–"
    for threshold, label in RISK_REDUCTION_LEVELS:
        if risk_reduction < threshold:
            return label
    return RISK_REDUCTION_TOP_LEVEL


@dataclass(frozen=True)
class PortfolioRiskWindow:
    """Diversifieringsnyckeltal för en portfölj över ett fönster."""

    portfolio: str
    period: str  # 'Since_Start' | '1Y'
    start: pd.Timestamp
    end: pd.Timestamp
    weights: pd.Series  # dagviktade snittvikter per Instrument_Key (renormaliserade)
    component_vols: pd.Series  # annualiserad σᵢ per Instrument_Key
    excluded: list[str]  # instrument utan full prishistorik i fönstret
    excluded_weight: float  # bortrenormaliserad viktandel
    summed_risk: float  # Σ w̄ᵢ·σᵢ (fraktion/år)
    portfolio_risk: float  # realiserad REAL-vol över fönstret (fraktion/år)
    model_risk: float  # √(w̄ᵀΣw̄) – konsistenskontroll mot portfolio_risk
    diversification: float  # summed_risk − portfolio_risk (fraktion, visas i pp)
    risk_reduction: float  # 1 − portfolio_risk / summed_risk
    level: str  # tolkningsetikett för riskreduktionen

    @property
    def model_gap(self) -> float:
        return self.model_risk - self.portfolio_risk


def annualized_vol(returns: pd.Series | pd.DataFrame):
    """Samma annualisering som portfölj-Vol i metrics.py (ddof=1, √252)."""
    return returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)


def risk_decomposition(
    fund_returns: pd.DataFrame, weights: pd.Series, portfolio_vol: float
) -> tuple[float, float, float, float]:
    """(Summerad risk, √(wᵀΣw), diversifieringseffekt, riskreduktion).

    ``fund_returns`` är dagliga avkastningar kolumn-per-instrument över fönstret,
    ``weights`` viktvektorn (summa 1) på samma kolumner, ``portfolio_vol`` den
    portföljrisk som dekomponeringen ställs mot (realiserad REAL-vol).
    """
    w = weights.reindex(fund_returns.columns).fillna(0.0).to_numpy(dtype=float)
    sigma = annualized_vol(fund_returns).to_numpy(dtype=float)
    summed = float(w @ sigma)
    cov = fund_returns.cov(ddof=1).to_numpy(dtype=float) * TRADING_DAYS_PER_YEAR
    model = float(np.sqrt(max(w @ cov @ w, 0.0)))
    diversification = summed - portfolio_vol
    risk_reduction = 1.0 - portfolio_vol / summed if summed > 0 else np.nan
    return summed, model, diversification, risk_reduction


def day_weighted_avg_weights(
    alloc: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> pd.Series:
    """Dagviktat snitt av månadsviktvektorerna över (start, end].

    Samma tidsviktning som costs.py: periodslutet pe_i representerar perioden
    (pe_{i-1}, pe_i] (första perioden [start, pe_0]) och vägs med sina
    kalenderdagar; ligger end efter sista periodslutet förlängs den sista
    viktvektorn till end. Instrument som saknas ett periodslut har vikt 0 där.
    """
    pivot = (
        alloc.pivot_table(
            index="Period_End_Date", columns="Instrument_Key", values="Weight", aggfunc="sum"
        )
        .sort_index()
        .fillna(0.0)
    )
    pivot = pivot[(pivot.index > start) & (pivot.index <= end)]
    if pivot.empty:
        raise ValueError(f"Inga månadsvikter i fönstret {start.date()} – {end.date()}.")
    boundaries = [start, *pivot.index.tolist()]
    days = pd.Series(
        [(b - a).days for a, b in zip(boundaries[:-1], boundaries[1:])], index=pivot.index
    ).astype(float)
    if end > pivot.index[-1]:
        days.iloc[-1] += (end - pivot.index[-1]).days
    avg = pivot.mul(days, axis=0).sum() / days.sum()
    return avg / avg.sum()


def _prepare_risk_window(
    data: BIData,
    price_cache: pd.DataFrame,
    portfolio: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[pd.Series, pd.DataFrame, list[str], float]:
    """(vikter, fondavkastningar, exkluderade, exkluderad_vikt) för fönstret (start, end].

    Delad förberedelse mellan riskdekomponeringen här och diversifieringsmåtten
    (DR/ENB/MCTR, :mod:`diversification`) – exakt samma instrumenturval,
    exkluderingsregler och fönster ligger till grund för båda; ingen parallell
    datamotor.
    """
    alloc = data.fact_alloc_monthly[data.fact_alloc_monthly["Portfolio_Key"] == portfolio]
    if alloc.empty:
        raise ValueError(f"Fact_Portfolio_Alloc_Monthly saknar portfölj {portfolio}")
    weights = day_weighted_avg_weights(alloc, start, end)

    # Exkludera innehav utan full prishistorik i fönstret (NaN i råmatrisen –
    # returns_from_prices skulle annars ge falska nolldagar) och renormalisera.
    in_window = price_cache[(price_cache.index > start) & (price_cache.index <= end)]
    excluded = [
        t
        for t in weights.index
        if t not in price_cache.columns or in_window[t].isna().any()
    ]
    excluded_weight = float(weights.reindex(excluded).sum()) if excluded else 0.0
    weights = weights.drop(excluded)
    if weights.empty:
        raise ValueError(f"Alla innehav i {portfolio} saknar prishistorik i fönstret.")
    weights = weights / weights.sum()

    lookback = start - pd.Timedelta(days=PRICE_LOOKBACK_DAYS)
    fund_rets = _fund_daily_returns_sek(data, list(weights.index), lookback, price_cache)
    fund_rets = fund_rets[(fund_rets.index > start) & (fund_rets.index <= end)]
    return weights, fund_rets, excluded, excluded_weight


def compute_portfolio_risk_window(
    data: BIData,
    price_cache: pd.DataFrame,
    portfolio: str,
    period: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> PortfolioRiskWindow:
    """Nyckeltalen för en portfölj över (start, end] ur BI-data + prismatris."""
    weights, fund_rets, excluded, excluded_weight = _prepare_risk_window(
        data, price_cache, portfolio, start, end
    )

    real = WindowSlice(data, f"PORT_{portfolio}_REAL", start, end)
    if not real.valid:
        raise ValueError(f"PORT_{portfolio}_REAL saknar data i fönstret {start.date()} – {end.date()}.")
    portfolio_vol = float(annualized_vol(real.returns.astype(float)))

    summed, model, diversification, risk_reduction = risk_decomposition(
        fund_rets, weights, portfolio_vol
    )
    return PortfolioRiskWindow(
        portfolio=portfolio,
        period=period,
        start=start,
        end=end,
        weights=weights,
        component_vols=annualized_vol(fund_rets),
        excluded=excluded,
        excluded_weight=excluded_weight,
        summed_risk=summed,
        portfolio_risk=portfolio_vol,
        model_risk=model,
        diversification=diversification,
        risk_reduction=risk_reduction,
        level=risk_reduction_level(risk_reduction),
    )


def compute_risk(
    data: BIData, price_cache: pd.DataFrame, horizons: list[Horizon]
) -> dict[str, list[PortfolioRiskWindow]]:
    """Nyckeltalen per portfölj för KPI-blockets horisonter (Since_Start, 1Y)."""
    portfolios = sorted(data.fact_alloc_monthly["Portfolio_Key"].unique())
    selected = [h for h in horizons if h.key in RISK_HORIZON_KEYS and h.available]
    # Samma ordning som KPI-blockets tabeller: Sedan start först, därefter 1Y.
    selected.sort(key=lambda h: RISK_HORIZON_KEYS.index(h.key))
    return {
        p: [
            compute_portfolio_risk_window(data, price_cache, p, h.key, h.start, h.end)
            for h in selected
        ]
        for p in portfolios
    }
