"""Självverifiering av fönster-KPI:er, rebasering och REAL-ankare.

Tre oberoende kontroller redovisas i rapporten:

1. **Rebaseringsankare** – varje rapportserie ska stå på exakt bas 100 vid det
   gemensamma startdatumet (inceptionen) efter rebasering.
2. **KPI-korskontroll** – de KPI:er rapporten visar (``metrics``-modulen, räknade
   ur IDX/RET via ``asof``-baser) jämförs mot en oberoende omräkning här, som
   samplar nivåer och avkastningar på ett annat sätt. Håller de inte ihop är
   antingen fönsterlogiken eller KPI-beräkningen fel.
3. **REAL-ankare** – REAL-seriernas slutnivåer i *hela* källserien jämförs mot
   kända värden. Detta guardar att rätt produktionsfil lästs och är oberoende av
   as-of (det kontrollerar filen, inte fönstret).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.config import RF_RATE_ANNUAL, TRADING_DAYS_PER_YEAR

from .data import BIData
from .metrics import KPI_COLUMNS
from .window import BASE_INDEX, Horizon, ONE_YEAR_DAYS, rebase_series

ABS_TOLERANCE = 1e-9
REL_TOLERANCE = 1e-6

# Kända slutnivåer, avlästa ur produktionsbygget som en filintegritetsguard (hela
# källserien, ej as-of-skuren). Uppdateras när priser drivit ankaret utanför
# toleransen och rörelsen är bekräftat legitim marknadsrörelse (inte fel fil/glitch).
# - EGEN 121,4: per 2026-07-06, bygget 2026-07-07 (sena fond-NAV-revideringar
#   flyttade EGEN 121,3→121,4 relativt bygget 2026-07-04).
# - PA 126,0: uppdaterad 2026-07-13 från 126,6 (per 2026-07-06). Bekräftad drift –
#   PA_REAL 126,60→125,99 över 2026-07-06→07-10 (−0,48 %), identisk med PA_TGT
#   (−0,47 %) och PA_CUR, gradvis utan dagsspik; divergensen mot POLICY_PA är
#   EM/tematik-släpet mot ACWI (samma mönster i EGEN_REAL). Toleransen oförändrad.
# - EGEN 120,0 / PA 125,4: uppdaterade 2026-07-19 (bygget för 2026-07-17, [AU]-
#   TER-seedfil-arbetet) från 121,4/126,0 (per 2026-07-13). Bekräftad drift –
#   EGEN_REAL −0,82 %, EGEN_TGT −0,79 %, EGEN_CUR −0,79 %; PA_REAL −0,30 %,
#   PA_TGT −0,28 %, PA_CUR −0,30 % över 2026-07-13→07-17, gradvis utan
#   dagsspik och identisk mellan REAL/TGT/CUR inom varje portfölj – legitim
#   marknadsrörelse, inte fel fil/glitch. TER-seedändringen rör bara
#   Dim_Instrument och påverkar inte prisserierna. Toleransen oförändrad.
REAL_ANCHORS = {"PORT_PA_REAL": 125.4, "PORT_EGEN_REAL": 120.0}
ANCHOR_TOLERANCE = 0.5
REBASE_TOLERANCE = 1e-9


@dataclass(frozen=True)
class VerificationResult:
    """Utfall av självverifieringen, för redovisning i rapporten."""

    kpi_comparison: pd.DataFrame  # en rad per serie/period/KPI med diff
    max_abs_diff: float
    n_compared: int
    n_deviations: int
    anchor_rows: pd.DataFrame  # REAL-serier: förväntat, observerat, ok (hela serien)
    rebase_rows: pd.DataFrame  # serie, nivå vid inception efter rebasering, ok
    max_rebase_diff: float


def _independent_kpis(
    data: BIData, series_id: str, start: pd.Timestamp, end: pd.Timestamp
) -> dict[str, float]:
    """Oberoende KPI-omräkning: annan sampling än metrics-modulen.

    Basen tas via ``asof``, totalavkastningen ur nivåkvoten (inte ur avkastnings-
    produkten), och fönsteravkastningarna ur IDX-differenser i stället för RET-
    kolumnen. Två skilda vägar till samma tal – avviker de fångas felet.
    """
    sub = data.fact_daily[data.fact_daily["Series_ID"] == series_id].sort_values("Date")
    idx = sub.set_index("Date")["IDX"]
    base = float(idx.asof(start))
    end_level = float(idx.asof(end))
    total_return = end_level / base - 1.0

    days = int((end - start).days)
    years = days / ONE_YEAR_DAYS
    cagr = float((1.0 + total_return) ** (1.0 / years) - 1.0) if years > 0 else np.nan

    window_levels = idx[(idx.index > start) & (idx.index <= end)]
    path = np.concatenate([[base], window_levels.to_numpy(dtype=float)])
    rets = pd.Series(path).pct_change().dropna()

    vol = float(rets.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)) if len(rets) > 1 else np.nan
    sharpe = float((cagr - RF_RATE_ANNUAL) / vol) if vol and vol != 0 else np.nan
    downside = rets.clip(upper=0.0)
    dd_dev = (
        float(np.sqrt(np.mean(np.square(downside))) * np.sqrt(TRADING_DAYS_PER_YEAR))
        if len(rets)
        else np.nan
    )
    sortino = float((cagr - RF_RATE_ANNUAL) / dd_dev) if dd_dev and dd_dev != 0 else np.nan

    running_max = np.maximum.accumulate(path)
    max_dd = float((path / running_max - 1.0).min())
    calmar = float(cagr / abs(max_dd)) if max_dd != 0 else np.nan

    return {
        "Return_Total": total_return,
        "CAGR": cagr,
        "Vol": vol,
        "Sharpe": sharpe,
        "Sortino": sortino,
        "Max_DD": max_dd,
        "Calmar": calmar,
    }


def verify_kpis(
    data: BIData,
    inception: pd.Timestamp,
    as_of: pd.Timestamp,
    horizons: list[Horizon],
    kpi_frame: pd.DataFrame,
    series_ids: list[str],
) -> VerificationResult:
    """Korskontrollera fönster-KPI:erna och rebaseringen; ankra REAL-nivåerna."""
    shown = kpi_frame.set_index(["Series_ID", "Period"])
    horizon_by_key = {h.key: h for h in horizons}

    rows: list[dict] = []
    for (series_id, period), shown_row in shown.iterrows():
        horizon = horizon_by_key[period]
        recomputed = _independent_kpis(data, series_id, horizon.start, horizon.end)
        for column in KPI_COLUMNS:
            expected = float(shown_row[column])
            actual = recomputed[column]
            if np.isnan(expected) and np.isnan(actual):
                diff, within = 0.0, True
            else:
                diff = abs(actual - expected)
                within = diff <= max(ABS_TOLERANCE, REL_TOLERANCE * abs(expected))
            rows.append(
                {
                    "Series_ID": series_id,
                    "Period": period,
                    "KPI": column,
                    "Visat": expected,
                    "Omräknat": actual,
                    "Diff": diff,
                    "OK": within,
                }
            )
    comparison = pd.DataFrame(rows)

    rebase_rows, max_rebase_diff = _check_rebase(data, inception, as_of, series_ids)

    return VerificationResult(
        kpi_comparison=comparison,
        max_abs_diff=float(comparison["Diff"].max()) if not comparison.empty else 0.0,
        n_compared=len(comparison),
        n_deviations=int((~comparison["OK"]).sum()) if not comparison.empty else 0,
        anchor_rows=_check_anchors(data),
        rebase_rows=rebase_rows,
        max_rebase_diff=max_rebase_diff,
    )


def _check_rebase(
    data: BIData, inception: pd.Timestamp, as_of: pd.Timestamp, series_ids: list[str]
) -> tuple[pd.DataFrame, float]:
    """Varje rebaserad serie ska stå på exakt bas 100 vid inceptionen."""
    rows = []
    worst = 0.0
    for series_id in series_ids:
        sub = data.fact_daily[data.fact_daily["Series_ID"] == series_id]
        if sub.empty:
            continue
        idx = sub.set_index("Date")["IDX"]
        rebased = rebase_series(idx, inception, as_of)
        first_level = float(rebased.iloc[0])
        diff = abs(first_level - BASE_INDEX)
        worst = max(worst, diff)
        rows.append(
            {
                "Series_ID": series_id,
                "Nivå_vid_start": first_level,
                "OK": diff <= REBASE_TOLERANCE,
            }
        )
    return pd.DataFrame(rows), worst


def _check_anchors(data: BIData) -> pd.DataFrame:
    """Jämför slutindex för REAL-serierna (hela serien) mot kända nivåer."""
    rows = []
    for series_id, expected in REAL_ANCHORS.items():
        sub = data.fact_daily[data.fact_daily["Series_ID"] == series_id]
        observed = float(sub.sort_values("Date")["IDX"].iloc[-1])
        rows.append(
            {
                "Series_ID": series_id,
                "Förväntat": expected,
                "Observerat": observed,
                "OK": abs(observed - expected) <= ANCHOR_TOLERANCE,
            }
        )
    return pd.DataFrame(rows)
