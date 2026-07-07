"""Policyreferens-blocket: Beta/Alfa/R² för REAL mot passiv policyreferens.

Referensindexen (POLICY_EGEN 90/10, POLICY_PA 85/15) är passiva tvåbucketsindex
(Aktier = MSCI ACWI inkl. EM, Räntor = kort företagsobligation, båda i SEK) med
årsvis ombalansering – se src/policy.py. De speglar det enda avsiktliga
strategivalet (aktier/räntor-nivån); geografi-, EM- och tematiska val hamnar i
alfa. PA:s referens visar om PA själv slår passivt index – kontext till EGEN:s
primärmål att slå PA.

Regressionen är OLS på VECKOavkastningar (fre–fre) över rapportens gemensamma
fönster:

    r_REAL(v) = alfa + beta · r_POLICY(v) + e(v)

- **Veckobas, inte dagsbas**: portföljens fonder NAV-sätts med eftersläpning
  (fonder med USA/Asien-exponering får kursen en dag senare), vilket gör
  dagsavkastningarna felalignade mot referensen. Daglig R² trycks då ned
  strukturellt (mätartefakt, bevisad via lag-korrelationer) och beta biasas mot
  noll. Veckoaggregeringen neutraliserar laggens andel av variationen; därför
  är veckodata rapporteringsbasen (beslut 2026-07-07). Dagsserierna behålls
  oförändrade för grafer och övriga KPI:er.
- **Fre–fre**: dagsavkastningarna kapitaliseras per vecka som slutar fredag;
  infaller helgdag används närmast föregående handelsdag som veckoslut.
  Serierna alignas dagligen (inner join) före aggregeringen så att båda
  veckoserier bygger på exakt samma handelsdagar. Kantveckor (fönstrets första/
  sista vecka) kan rymma färre dagar men är konsistenta observationer av samma
  samband.
- **Beta** = samvariationen med referensen (kvot av kovarians/varians).
- **Alfa** redovisas annualiserad: (1 + alfa_vecka)^52 − 1.
- **R²** = förklaringsgrad. Beta/Alfa visas endast när R² > 0,70 – under det
  förklarar referensen för lite av variationen för att måtten ska bära.
- **Preliminärt**: alfa/beta blir meningsfulla först vid ~3 års historik.
  Gränsen är datumstyrd (inception + 3 år), aldrig hårdkodad text. Veckobasen
  ger dessutom få observationer (~52/år); konfidensintervallen kring beta/alfa
  är breda tills historiken växer.

Nivåbias att känna till: proxyfonderna är net-of-fee (ACWI-UCITS ~0,2 %/år,
räntefonden ~0,4 %/år), vilket gör referensen något lättare att slå – en liten,
konstant och dokumenterad effekt i alfa-nivån.

Mätteknik: aktiebucketen använder Europanoterade IUSQ.DE (Xetra, 17:30 CET) i
stället för US-noterade ACWI (22:00 CET) för att synka dagsavkastningarna med
portföljens svenska fond-NAV:er – det minskar laggen men tar inte bort den,
därav veckobasen ovan.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import BIData
from .metrics import WindowSlice

# Portfölj -> policyreferensens Series_ID.
POLICY_SERIES = {"EGEN": "POLICY_EGEN", "PA": "POLICY_PA"}

# Veckoregressionens annualiseringsbas.
WEEKS_PER_YEAR = 52

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
    n_obs: int  # antal veckoobservationer
    beta: float
    alpha_weekly: float
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
    """(beta, alfa, R², n) för OLS y = alfa + beta·x på datum-alignade serier.

    Periodicitetsagnostisk: alfa kommer i samma periodlängd som inserierna
    (veckobas i rapporten – annualisera med ``annualize_alpha``).
    """
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


def annualize_alpha(alpha_weekly: float) -> float:
    """Geometrisk annualisering av veckoalfa: (1 + alfa)^52 − 1."""
    return float((1.0 + alpha_weekly) ** WEEKS_PER_YEAR - 1.0)


def weekly_returns(daily):
    """Veckoavkastningar (fre–fre) ur dagsavkastningar med datumindex.

    Dagsavkastningarna kapitaliseras per vecka som slutar fredag
    (``W-FRI``-buckets); är fredagen helgdag slutar veckan automatiskt på
    närmast föregående handelsdag, eftersom bucketen då bara rymmer dagar fram
    till den dagen. Observationen etiketteras med veckans sista faktiska
    handelsdag. Veckor helt utan handelsdagar utelämnas.

    Fungerar för både Series och DataFrame (kolumnvis) – ett DataFrame med
    redan datum-alignade serier ger veckoserier på exakt samma buckets.
    """
    grouper = pd.Grouper(freq="W-FRI")
    compounded = (1.0 + daily).groupby(grouper).prod() - 1.0
    counts = daily.groupby(grouper).size()
    last_trading_day = daily.index.to_series().groupby(grouper).max()
    weekly = compounded[counts > 0]
    weekly.index = pd.DatetimeIndex(last_trading_day[counts > 0])
    return weekly


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
        # Aligna dagligen först så att båda veckoserier bygger på samma dagar.
        joined = pd.concat([real, policy], axis=1, join="inner", keys=["real", "policy"]).dropna()
        weekly = weekly_returns(joined)
        beta, alpha_weekly, r2, n = regress_returns(weekly["real"], weekly["policy"])
        out[portfolio] = PolicyRegression(
            portfolio=portfolio,
            policy_series_id=policy_id,
            start=inception,
            end=as_of,
            n_obs=n,
            beta=beta,
            alpha_weekly=alpha_weekly,
            alpha_annual=annualize_alpha(alpha_weekly),
            r2=r2,
            preliminary_until=preliminary_until,
        )
    return out
