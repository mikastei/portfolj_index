"""Policyreferens-blocket: Beta/Alfa/R² för REAL mot passiv policyreferens.

Referensindexen (POLICY_EGEN 90/10, POLICY_PA 85/15) är passiva tvåbucketsindex
(Aktier = MSCI ACWI inkl. EM, Räntor = kort företagsobligation, båda i SEK) med
årsvis ombalansering – se src/policy.py. De speglar det enda avsiktliga
strategivalet (aktier/räntor-nivån); geografi-, EM- och tematiska val hamnar i
alfa. PA:s referens visar om PA själv slår passivt index – kontext till EGEN:s
primärmål att slå PA.

Regressionen är OLS på dagliga avkastningar över rapportens gemensamma fönster:

    r_REAL(t) = alfa + beta · r_POLICY(t) + e(t)

- **Beta** = samvariationen med referensen (kvot av kovarians/varians).
- **Alfa** redovisas annualiserad: (1 + alfa_dag)^252 − 1.
- **R²** = förklaringsgrad. Beta/Alfa visas endast när R² > 0,70 – under det
  förklarar referensen för lite av variationen för att måtten ska bära.
- **Preliminärt**: alfa/beta blir meningsfulla först vid ~3 års historik.
  Gränsen är datumstyrd (inception + 3 år), aldrig hårdkodad text.

Nivåbias att känna till: proxyfonderna är net-of-fee (ACWI-UCITS ~0,2 %/år,
räntefonden ~0,4 %/år), vilket gör referensen något lättare att slå – en liten,
konstant och dokumenterad effekt i alfa-nivån.

Mätteknik: aktiebucketen använder Europanoterade IUSQ.DE (Xetra, 17:30 CET) i
stället för US-noterade ACWI (22:00 CET) för att synka dagsavkastningarna med
portföljens svenska fond-NAV:er. Kvarvarande NAV-lagg (fonder med USA/Asien-
exponering NAV-sätts med en dags eftersläpning) trycker ändå ned daglig R²
strukturellt – R²-spärren är tänkt att fånga exakt detta.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.config import TRADING_DAYS_PER_YEAR

from .data import BIData
from .metrics import WindowSlice

# Portfölj -> policyreferensens Series_ID.
POLICY_SERIES = {"EGEN": "POLICY_EGEN", "PA": "POLICY_PA"}

# Beta/Alfa visas endast när referensen förklarar merparten av variationen.
R2_THRESHOLD = 0.70

# Alfa/beta betraktas som preliminära tills fönstret rymmer så här många års historik.
PRELIMINARY_YEARS = 3


@dataclass(frozen=True)
class PolicyRegression:
    """OLS-resultat för en portföljs REAL-serie mot dess policyreferens."""

    portfolio: str
    policy_series_id: str
    start: pd.Timestamp
    end: pd.Timestamp
    n_obs: int
    beta: float
    alpha_daily: float
    alpha_annual: float
    r2: float
    preliminary_until: pd.Timestamp  # inception + 3 år (datumstyrt)

    @property
    def show_beta_alpha(self) -> bool:
        """R²-spärren: Beta/Alfa undertrycks när referensen förklarar för lite."""
        return bool(self.r2 > R2_THRESHOLD)

    @property
    def preliminary(self) -> bool:
        return bool(self.end < self.preliminary_until)


def regress_returns(y: pd.Series, x: pd.Series) -> tuple[float, float, float, int]:
    """(beta, alfa_dag, R², n) för OLS y = alfa + beta·x på datum-alignade serier."""
    joined = pd.concat([y, x], axis=1, join="inner", keys=["y", "x"]).dropna()
    n = len(joined)
    if n < 3:
        raise ValueError(f"För få gemensamma observationer för regression: {n}")
    yv = joined["y"].to_numpy(dtype=float)
    xv = joined["x"].to_numpy(dtype=float)
    var_x = float(np.var(xv, ddof=1))
    if var_x == 0.0:
        raise ValueError("Referensserien har noll varians – beta odefinierat")
    beta = float(np.cov(yv, xv, ddof=1)[0, 1]) / var_x
    alpha = float(np.mean(yv) - beta * np.mean(xv))
    residuals = yv - (alpha + beta * xv)
    ss_tot = float(np.sum((yv - np.mean(yv)) ** 2))
    r2 = 1.0 - float(np.sum(residuals**2)) / ss_tot if ss_tot > 0 else np.nan
    return beta, alpha, r2, n


def annualize_alpha(alpha_daily: float) -> float:
    """Geometrisk annualisering av daglig alfa: (1 + alfa)^252 − 1."""
    return float((1.0 + alpha_daily) ** TRADING_DAYS_PER_YEAR - 1.0)


def _window_returns(
    data: BIData, series_id: str, start: pd.Timestamp, end: pd.Timestamp
) -> pd.Series:
    sl = WindowSlice(data, series_id, start, end)
    if not sl.valid:
        raise ValueError(f"{series_id} saknar data i fönstret {start.date()} – {end.date()}.")
    return pd.Series(sl.returns.to_numpy(dtype=float), index=pd.DatetimeIndex(sl.dates))


def compute_policy_regressions(
    data: BIData, inception: pd.Timestamp, as_of: pd.Timestamp
) -> dict[str, PolicyRegression] | None:
    """Regressionerna per portfölj över [inception, as_of].

    Returnerar None om policyserierna saknas i BI-filen (äldre fil) så att
    rapporten kan degradera med en notis i stället för att stoppa bygget.
    """
    available = set(data.fact_daily["Series_ID"].unique())
    if not all(sid in available for sid in POLICY_SERIES.values()):
        return None

    preliminary_until = inception + pd.DateOffset(years=PRELIMINARY_YEARS)
    out: dict[str, PolicyRegression] = {}
    for portfolio, policy_id in POLICY_SERIES.items():
        real = _window_returns(data, f"PORT_{portfolio}_REAL", inception, as_of)
        policy = _window_returns(data, policy_id, inception, as_of)
        beta, alpha_daily, r2, n = regress_returns(real, policy)
        out[portfolio] = PolicyRegression(
            portfolio=portfolio,
            policy_series_id=policy_id,
            start=inception,
            end=as_of,
            n_obs=n,
            beta=beta,
            alpha_daily=alpha_daily,
            alpha_annual=annualize_alpha(alpha_daily),
            r2=r2,
            preliminary_until=preliminary_until,
        )
    return out
