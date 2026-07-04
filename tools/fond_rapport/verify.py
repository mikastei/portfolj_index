"""Självverifiering: räknar om KPI:erna ur Fact_Series_Daily och ankrar REAL-nivåer.

Omräkningen är en oberoende implementation av samma KPI-definitioner som
src.bi_metrics använder (rf och handelsdagar hämtas från src.config så att
parametrarna garanterat matchar pipelinen). Om filens Fact_Series_KPI inte
kan reproduceras ur Fact_Series_Daily är antingen filen eller rapportmotorn
fel – båda fallen ska synas i rapporten.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.config import RF_RATE_ANNUAL, TRADING_DAYS_PER_YEAR

from .data import BIData

KPI_COLUMNS = ["Return_Total", "CAGR", "Vol", "Sharpe", "Sortino", "Max_DD", "Calmar"]
ABS_TOLERANCE = 1e-9
REL_TOLERANCE = 1e-6

# Kända nivåer per 2026-07-03, avlästa ur BI-filen byggd 2026-07-04 (sena
# fond-NAV:er reviderade EGEN från 120,5 till 121,3 mellan byggena 3 och 4 juli).
# Avviker slutindex mer än toleransen ska rapporten inte byggas alls.
REAL_ANCHORS = {"PORT_PA_REAL": 125.9, "PORT_EGEN_REAL": 121.3}
ANCHOR_TOLERANCE = 0.5


@dataclass(frozen=True)
class VerificationResult:
    """Utfall av självverifieringen, för redovisning i rapporten."""

    kpi_comparison: pd.DataFrame  # en rad per serie/period/KPI med diff
    max_abs_diff: float
    n_compared: int
    n_deviations: int
    anchor_rows: pd.DataFrame  # serie, förväntat, observerat, ok


def _period_window(frame: pd.DataFrame, period: str) -> pd.DataFrame:
    """Samma periodfönster som src.bi_metrics: senaste datum per serie styr."""
    latest = frame["Date"].max()
    if period == "Since_Start":
        return frame
    if period == "YTD":
        start = pd.Timestamp(year=latest.year, month=1, day=1)
    elif period == "30D":
        start = latest - pd.Timedelta(days=30)
    elif period == "1Y":
        start = latest - pd.DateOffset(years=1)
    else:
        raise ValueError(f"Okänd period: {period}")
    return frame[frame["Date"] >= start]


def _recompute_row(window: pd.DataFrame) -> dict[str, float]:
    """Oberoende omräkning av KPI:erna för ett periodfönster."""
    idx = window["IDX"]
    ret = window["RET"]
    dd = window["DD"]

    total_return = float(idx.iloc[-1] / idx.iloc[0] - 1.0)

    days = (window["Date"].max() - window["Date"].min()).days
    years = days / 365.25
    cagr = float((1.0 + total_return) ** (1.0 / years) - 1.0) if years > 0 else np.nan

    vol = float(ret.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
    sharpe = float((cagr - RF_RATE_ANNUAL) / vol) if vol != 0 else np.nan

    downside = ret.clip(upper=0.0)
    downside_dev = float(np.sqrt(np.mean(np.square(downside))) * np.sqrt(TRADING_DAYS_PER_YEAR))
    sortino = float((cagr - RF_RATE_ANNUAL) / downside_dev) if downside_dev != 0 else np.nan

    max_dd = float(dd.min())
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


def verify_kpis(data: BIData) -> VerificationResult:
    """Räkna om samtliga KPI-rader och jämför mot Fact_Series_KPI."""
    rows: list[dict] = []
    for _, kpi_row in data.fact_kpi.iterrows():
        series_frame = data.fact_daily[data.fact_daily["Series_ID"] == kpi_row["Series_ID"]]
        window = _period_window(series_frame, kpi_row["Period"])
        recomputed = _recompute_row(window)
        for column in KPI_COLUMNS:
            expected = float(kpi_row[column])
            actual = recomputed[column]
            diff = abs(actual - expected)
            within = diff <= max(ABS_TOLERANCE, REL_TOLERANCE * abs(expected))
            rows.append(
                {
                    "Series_ID": kpi_row["Series_ID"],
                    "Period": kpi_row["Period"],
                    "KPI": column,
                    "Fil": expected,
                    "Omräknat": actual,
                    "Diff": diff,
                    "OK": within,
                }
            )

    comparison = pd.DataFrame(rows)
    return VerificationResult(
        kpi_comparison=comparison,
        max_abs_diff=float(comparison["Diff"].max()),
        n_compared=len(comparison),
        n_deviations=int((~comparison["OK"]).sum()),
        anchor_rows=_check_anchors(data),
    )


def _check_anchors(data: BIData) -> pd.DataFrame:
    """Jämför slutindex för REAL-serierna mot kända nivåer."""
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
