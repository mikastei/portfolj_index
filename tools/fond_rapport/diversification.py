"""Diversifieringsmått: DR, ENB, MCTR ([AZ]).

Bygger vidare på riskdekomponeringen i :mod:`risk` (Summerad risk, Portföljrisk,
Diversifieringseffekt, Riskreduktion) med tre operationaliseringar av "hur många
oberoende avkastningsmotorer bär portföljen" – se beslutsunderlaget
``30-Funktioner/Portföljanalys/Protokoll/260621_Beslutsunderlag_Diversifieringsmått.md``
i Hjärnkontoret-anteckningarna. Ingen parallell datamotor: samma dagviktade
snittvikter, exkluderingsregler och fönster som
:func:`risk.compute_portfolio_risk_window` – delas via ``risk._prepare_risk_window``.

- **Diversification Ratio** (DR = Summerad risk / Portföljrisk) är riskreduktionen
  uttryckt som kvot i stället för procentenhetsdifferens: DR = 1/(1 − Riskreduktion).
  Jämförbar rakt av över tid och mellan portföljer.
- **ENB** (effektivt antal oberoende vad): egenvärdena λᵢ i korrelationsmatrisen för
  komponentavkastningarna normaliseras till en sannolikhetsfördelning pᵢ = λᵢ/Σλ;
  ENB = exp(Shannon-entropin av p). N helt okorrelerade innehav ger ENB = N; N
  perfekt korrelerade innehav ger ENB → 1 – oavsett hur många fonder som faktiskt
  hålls.
- **MCTR** (riskbidrag per innehav): med samma vikter w och den annualiserade
  kovariansmatrisen Σ (samma bas som riskdekomponeringens modellkontroll),
  bidragᵢ = wᵢ·(Σw)ᵢ / (wᵀΣw). Summerar till 100 % av portföljrisken. Kvoten
  riskbidrag/vikt > 1 markerar en riskdrivare, < 1 en diversifierare.

Strukturmått, inte kvalitetsmått – styrdokumentets varning om korrelationsjakt
gäller även här (se metodnoten i rapporten). ENB påverkas av fönsterval och
NAV-utjämning i portföljens fonder, precis som veckoregressionen i policyblocket
(avsnitt 2) motiveras av samma NAV-lagg.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.config import TRADING_DAYS_PER_YEAR

from .data import BIData
from .risk import PortfolioRiskWindow, _prepare_risk_window


@dataclass(frozen=True)
class ContributionRow:
    """Riskbidrag för ett enskilt innehav (MCTR)."""

    instrument: str
    display_name: str
    weight: float  # dagviktat snitt (samma bas som risk.py, efter exkludering)
    risk_contribution: float  # wᵢ·(Σw)ᵢ / (wᵀΣw), fraktion av portföljrisken
    ratio: float  # risk_contribution / weight – >1 riskdrivare, <1 diversifierare


@dataclass(frozen=True)
class DiversificationWindow:
    """DR, ENB och MCTR för en portfölj över samma fönster som PortfolioRiskWindow."""

    portfolio: str
    period: str  # 'Since_Start' | '1Y', samma horisonter som risk.py
    dr: float
    enb: float
    n: int  # antal fonder i korrelationsmatrisen (efter exkludering, jfr risk.excluded)
    contributions: list[ContributionRow]  # sorterat fallande på risk_contribution


def diversification_ratio(summed_risk: float, portfolio_risk: float) -> float:
    """DR = Summerad risk / Portföljrisk. Identitet: DR = 1/(1 − Riskreduktion)."""
    if portfolio_risk == 0:
        return float("nan")
    return summed_risk / portfolio_risk


def effective_number_of_bets(fund_returns: pd.DataFrame) -> float:
    """ENB via Shannon-entropin på egenvärdena av korrelationsmatrisen.

    1 ≤ ENB ≤ N: identitetsmatris (allt okorrelerat) ger ENB = N; perfekt
    korrelerade serier (korrelationsmatris av rang 1) ger ENB → 1.
    """
    corr = fund_returns.corr().to_numpy(dtype=float)
    eigenvalues = np.clip(np.linalg.eigvalsh(corr), 0.0, None)
    total = eigenvalues.sum()
    if total <= 0:
        return float("nan")
    p = eigenvalues / total
    nonzero = p[p > 0]
    entropy = float(-(nonzero * np.log(nonzero)).sum())
    return float(np.exp(entropy))


def risk_contributions(fund_returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """MCTR per instrument: bidragᵢ = wᵢ·(Σw)ᵢ / (wᵀΣw). Summerar till 1,0."""
    w = weights.reindex(fund_returns.columns).fillna(0.0).to_numpy(dtype=float)
    cov = fund_returns.cov(ddof=1).to_numpy(dtype=float) * TRADING_DAYS_PER_YEAR
    sigma_w = cov @ w
    portfolio_variance = float(w @ sigma_w)
    if portfolio_variance <= 0:
        contrib = np.full_like(w, np.nan)
    else:
        contrib = w * sigma_w / portfolio_variance
    return pd.Series(contrib, index=fund_returns.columns)


def compute_diversification_window(
    data: BIData, price_cache: pd.DataFrame, risk: PortfolioRiskWindow
) -> DiversificationWindow:
    """DR/ENB/MCTR för samma portfölj/period/fönster som en beräknad PortfolioRiskWindow."""
    weights, fund_rets, _excluded, _excluded_weight = _prepare_risk_window(
        data, price_cache, risk.portfolio, risk.start, risk.end
    )
    dr = diversification_ratio(risk.summed_risk, risk.portfolio_risk)
    enb = effective_number_of_bets(fund_rets)
    contrib = risk_contributions(fund_rets, weights)

    names = data.dim_instrument.set_index("Instrument_Key")["Display_Name"]
    rows = [
        ContributionRow(
            instrument=key,
            display_name=str(names.get(key, key)),
            weight=float(weights[key]),
            risk_contribution=float(contrib[key]),
            ratio=float(contrib[key] / weights[key]) if weights[key] != 0 else float("nan"),
        )
        for key in weights.index
    ]
    rows.sort(key=lambda r: r.risk_contribution, reverse=True)

    return DiversificationWindow(
        portfolio=risk.portfolio,
        period=risk.period,
        dr=dr,
        enb=enb,
        n=len(weights),
        contributions=rows,
    )


def compute_diversification(
    data: BIData, price_cache: pd.DataFrame, risks: dict[str, list[PortfolioRiskWindow]]
) -> dict[str, list[DiversificationWindow]]:
    """DR/ENB/MCTR för samma portföljer/horisonter som compute_risk gav."""
    return {
        portfolio: [compute_diversification_window(data, price_cache, r) for r in rows]
        for portfolio, rows in risks.items()
    }
