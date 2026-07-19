"""Motorexponering per portfölj ([BD]): vikt- och riskandel per Drivkraft-motor.

Drivkraft (7 avkastningsmotorer) är Mickes klassning per fond, en primärmotor per
fond, beslutad i ``Portföljanalys/_output/260716_Mappningstabell_Drivkraft.md`` och
definierad i ``Styrning/01_Fondkategorier.md`` Del 3 (Fondanalys-repot). Kolumnen
läses ur Fondertabell (fonder.xlsx) uppströms och landar som ``Driver`` i
Dim_Instrument – se ``src/portfolio.py::_driver_by_ticker`` och
``src/bi_prep.py::_build_dim_instrument``.

Ren aggregering ovanpå redan beräknade byggstenar, ingen ny motor:

- **Exponering** (:func:`compute_driver_exposure`): Nuläge = dagens REAL-
  snapshotvikter (``Fact_Portfolio_Alloc_Snapshot``); Sedan start = samma
  dagviktade snitt av månadsvikterna som TER-/riskblocken
  (:func:`risk.day_weighted_avg_weights` över ``Fact_Portfolio_Alloc_Monthly``,
  fönstret EGEN:s inception → as-of). Instrument utan klassning (benchmarks,
  policyserier, oklassade fonder) samlas i en separat "Oklassad"-rest – ingen
  gissning. :func:`renormalized_over_classified` räknar om motorvikterna så att
  de summerar till 100 % över enbart de klassade innehaven.
- **Riskandel** (:func:`compute_driver_risk_share`): summan av MCTR-bidragen per
  motor ur en redan beräknad :class:`~.diversification.DiversificationWindow`
  (Since_Start) – ingen ny riskberäkning. Kvoten riskandel/vikt: > 1 riskdrivare,
  < 1 diversifierare, samma tolkningsspråk som MCTR-tabellen.

Strukturmått, inte kvalitetsmått: jämför över tid, inte mot en absolutskala.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .data import BIData
from .diversification import DiversificationWindow
from .risk import day_weighted_avg_weights

UNCLASSIFIED_LABEL = "Oklassad"


@dataclass(frozen=True)
class DriverExposureWindow:
    """Motorexponering för en portfölj: Nuläge och dagviktat Sedan start."""

    portfolio: str
    snapshot_weights: pd.Series  # Driver -> vikt (Nuläge, inkl. "Oklassad", summerar till 1,0)
    since_start_weights: pd.Series  # Driver -> vikt (Sedan start, dagviktat, summerar till 1,0)


@dataclass(frozen=True)
class DriverRiskShareWindow:
    """Riskandel per motor för en portfölj, ur MCTR-aggregeringen (Since_Start)."""

    portfolio: str
    weight: pd.Series  # Driver -> vikt (samma bas som MCTR-kontributionerna)
    risk_share: pd.Series  # Driver -> summerat riskbidrag (summerar till portföljrisken)
    ratio: pd.Series  # risk_share / weight per motor


def _driver_by_key(data: BIData) -> pd.Series:
    dim = data.dim_instrument
    if "Driver" not in dim.columns:
        return pd.Series(dtype=object)
    return dim.set_index("Instrument_Key")["Driver"]


def has_driver_data(data: BIData) -> bool:
    """Finns det över huvud taget någon Drivkraft-klassning att aggregera på."""
    driver_by_key = _driver_by_key(data)
    return bool(driver_by_key.notna().any())


def _weights_by_driver(weights: pd.Series, driver_by_key: pd.Series) -> pd.Series:
    """Grupperar en viktvektor (Instrument_Key -> vikt, summa 1,0) per motor.

    Instrument utan klassning samlas i :data:`UNCLASSIFIED_LABEL` – ingen gissning.
    """
    mapped = weights.index.to_series().map(driver_by_key)
    mapped = mapped.where(mapped.notna(), UNCLASSIFIED_LABEL)
    grouped = weights.groupby(mapped.to_numpy()).sum()
    return grouped.sort_values(ascending=False)


def renormalized_over_classified(weights_by_driver: pd.Series) -> pd.Series:
    """Motorvikterna omräknade så att de summerar till 100 % över klassade innehav.

    Den oklassade resten redovisas separat i rapporten – den är inte en åttonde
    motor och ingår inte i denna omräkning.
    """
    classified = weights_by_driver.drop(index=UNCLASSIFIED_LABEL, errors="ignore")
    total_classified = float(classified.sum())
    if total_classified <= 0:
        return classified
    return classified / total_classified


def _snapshot_weights_by_driver(
    data: BIData, portfolio: str, driver_by_key: pd.Series
) -> pd.Series:
    alloc = data.fact_alloc[
        (data.fact_alloc["Portfolio_Key"] == portfolio)
        & (data.fact_alloc["Series_ID"] == f"PORT_{portfolio}_REAL")
    ]
    if alloc.empty:
        raise ValueError(f"Fact_Portfolio_Alloc_Snapshot saknar REAL-snapshot för {portfolio}")
    weights = alloc.groupby("Instrument_Key")["Weight"].sum()
    return _weights_by_driver(weights, driver_by_key)


def _since_start_weights_by_driver(
    data: BIData,
    portfolio: str,
    inception: pd.Timestamp,
    as_of: pd.Timestamp,
    driver_by_key: pd.Series,
) -> pd.Series:
    alloc = data.fact_alloc_monthly[data.fact_alloc_monthly["Portfolio_Key"] == portfolio]
    if alloc.empty:
        raise ValueError(f"Fact_Portfolio_Alloc_Monthly saknar portfölj {portfolio}")
    weights = day_weighted_avg_weights(alloc, inception, as_of)
    return _weights_by_driver(weights, driver_by_key)


def compute_driver_exposure(
    data: BIData, portfolios: list[str], inception: pd.Timestamp, as_of: pd.Timestamp
) -> dict[str, DriverExposureWindow] | None:
    """Motorexponering (Nuläge + Sedan start) per portfölj.

    ``None`` om Dim_Instrument saknar Driver-kolumnen eller om ingen fond alls är
    klassad (t.ex. äldre BI-fil byggd före [BD]) – rapporten utelämnar då avsnittet
    i stället för att gissa.
    """
    driver_by_key = _driver_by_key(data)
    if driver_by_key.empty or driver_by_key.notna().sum() == 0:
        return None
    return {
        portfolio: DriverExposureWindow(
            portfolio=portfolio,
            snapshot_weights=_snapshot_weights_by_driver(data, portfolio, driver_by_key),
            since_start_weights=_since_start_weights_by_driver(
                data, portfolio, inception, as_of, driver_by_key
            ),
        )
        for portfolio in portfolios
    }


def _risk_share_from_contributions(
    d: DiversificationWindow, driver_by_key: pd.Series
) -> DriverRiskShareWindow:
    rows = d.contributions
    df = pd.DataFrame(
        {
            "driver": [driver_by_key.get(r.instrument) for r in rows],
            "weight": [r.weight for r in rows],
            "risk_contribution": [r.risk_contribution for r in rows],
        }
    )
    df["driver"] = df["driver"].where(df["driver"].notna(), UNCLASSIFIED_LABEL)
    grouped = df.groupby("driver")[["weight", "risk_contribution"]].sum()
    weight = grouped["weight"]
    risk_share = grouped["risk_contribution"]
    ratio = (risk_share / weight).where(weight != 0, float("nan"))
    order = risk_share.sort_values(ascending=False).index
    return DriverRiskShareWindow(
        portfolio=d.portfolio,
        weight=weight.reindex(order),
        risk_share=risk_share.reindex(order),
        ratio=ratio.reindex(order),
    )


def compute_driver_risk_share(
    data: BIData, diversification: dict[str, list[DiversificationWindow]] | None
) -> dict[str, DriverRiskShareWindow] | None:
    """Riskandel per motor (Since_Start), ren aggregering av redan beräknade MCTR-bidrag.

    ``None`` om diversifieringsmåtten inte kunde beräknas (prismatris saknades) eller
    om ingen fond är Drivkraft-klassad.
    """
    if not diversification:
        return None
    driver_by_key = _driver_by_key(data)
    if driver_by_key.empty or driver_by_key.notna().sum() == 0:
        return None
    result: dict[str, DriverRiskShareWindow] = {}
    for portfolio, rows in diversification.items():
        since_start = next((d for d in rows if d.period == "Since_Start"), None)
        if since_start is None:
            continue
        result[portfolio] = _risk_share_from_contributions(since_start, driver_by_key)
    return result or None
