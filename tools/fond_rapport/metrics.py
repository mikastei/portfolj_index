"""KPI- och horisontberäkning över ett godtyckligt [start, as_of]-fönster.

Alla mått räknas ur ``Fact_Series_Daily`` och är oberoende av rebasering – de
bygger på avkastningar och nivåkvoter, inte på absoluta indexnivåer. Definitionerna
följer pipelinen (rf 3&nbsp;% årligen, 252 handelsdagar, CAGR på
kalenderdagar/365,25).

Fönstrets bas är nivån vid *senast kända stängning på eller före* startdatumet
(``asof``). Det ger den vedertagna YTD-/1Y-definitionen även när startdatumet
(t.ex. 1 januari) inte är en handelsdag: basen blir föregående års sista stängning
och första dagsavkastningen i fönstret räknas mot den. Drawdown mäts inom fönstret,
med basen som första möjliga topp.

Returtabellen exponeras i samma form som BI-filens ``Fact_Series_KPI`` (kolumner
Series_ID, Period + de sju KPI:erna) men beräknad över det gemensamma fönstret,
så att rapporten kan konsumera den precis som den tidigare läste filens KPI:er.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import RF_RATE_ANNUAL, TRADING_DAYS_PER_YEAR

from .data import BIData
from .window import ONE_YEAR_DAYS, Horizon

KPI_COLUMNS = ["Return_Total", "CAGR", "Vol", "Sharpe", "Sortino", "Max_DD", "Calmar"]


class WindowSlice:
    """Fönsterlokala nivåer och dagsavkastningar för en serie över [start, as_of]."""

    def __init__(self, data: BIData, series_id: str, start: pd.Timestamp, end: pd.Timestamp):
        sub = data.fact_daily[data.fact_daily["Series_ID"] == series_id]
        if sub.empty:
            raise KeyError(f"Serien saknas i Fact_Series_Daily: {series_id}")
        sub = sub.sort_values("Date")
        self.series_id = series_id
        self.start = start
        self.end = end
        idx = sub.set_index("Date")["IDX"]
        self.base_level = idx.asof(start)
        self.end_level = idx.asof(end)
        window = sub[(sub["Date"] > start) & (sub["Date"] <= end)]
        self.dates = window["Date"].reset_index(drop=True)
        # Dagsavkastningar ur RET (varje refererar föregående handelsdag; första
        # i fönstret mot basstängningen). Produkten återger exakt end/base − 1.
        self.returns = window["RET"].reset_index(drop=True)
        # Nivåbana med basen som första punkt (för drawdown).
        self.levels = np.concatenate([[float(self.base_level)], window["IDX"].to_numpy(dtype=float)])

    @property
    def valid(self) -> bool:
        return (
            not pd.isna(self.base_level)
            and not pd.isna(self.end_level)
            and self.base_level != 0
            and len(self.returns) >= 1
        )

    @property
    def span_days(self) -> int:
        return int((self.end - self.start).days)


def _cagr(total_return: float, days: int) -> float:
    years = days / ONE_YEAR_DAYS
    if years <= 0:
        return np.nan
    return float((1.0 + total_return) ** (1.0 / years) - 1.0)


def horizon_return(sl: WindowSlice, measure: str) -> float:
    """Kumulativ avkastning eller CAGR över fönstret enligt horisontens mått."""
    total = float(sl.end_level / sl.base_level - 1.0)
    if measure == "cumulative":
        return total
    return _cagr(total, sl.span_days)


def compute_kpis(sl: WindowSlice) -> dict[str, float]:
    """De sju KPI:erna över ett fönster. Avkastningar och drawdown är fönsterlokala."""
    rets = sl.returns.astype(float)
    total_return = float(sl.end_level / sl.base_level - 1.0)
    cagr = _cagr(total_return, sl.span_days)

    vol = float(rets.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR)) if len(rets) > 1 else np.nan
    sharpe = float((cagr - RF_RATE_ANNUAL) / vol) if vol and vol != 0 else np.nan

    downside = rets.clip(upper=0.0)
    downside_dev = (
        float(np.sqrt(np.mean(np.square(downside))) * np.sqrt(TRADING_DAYS_PER_YEAR))
        if len(rets)
        else np.nan
    )
    sortino = (
        float((cagr - RF_RATE_ANNUAL) / downside_dev) if downside_dev and downside_dev != 0 else np.nan
    )

    running_max = np.maximum.accumulate(sl.levels)
    drawdown = sl.levels / running_max - 1.0
    max_dd = float(drawdown.min())
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


def window_kpi_table(
    data: BIData, series_ids: list[str], horizons: list[Horizon]
) -> pd.DataFrame:
    """KPI-tabell (Series_ID × Period) över de tillgängliga horisonterna.

    Endast tillgängliga horisonter ger rader; utelämnade horisonter (t.ex. 3Y utan
    tre års data) saknas helt, så uppslag på dem måste gate:as av anroparen.
    """
    rows: list[dict] = []
    for horizon in horizons:
        if not horizon.available:
            continue
        for series_id in series_ids:
            sl = WindowSlice(data, series_id, horizon.start, horizon.end)
            if not sl.valid:
                continue
            rows.append({"Series_ID": series_id, "Period": horizon.key, **compute_kpis(sl)})
    return pd.DataFrame(rows, columns=["Series_ID", "Period", *KPI_COLUMNS])
