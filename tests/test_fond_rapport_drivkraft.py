"""Tester för fond-rapportens motorexponering: Drivkraft-aggregeringen ([BD]).

Ren aggregering ovanpå redan testade byggstenar (diversifieringsmåtten i [AZ],
dagviktningen i risk.py) – här verifieras enbart att grupperingen per motor
summerar rätt och hanterar oklassade innehav utan att gissa.
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from tools.fond_rapport.data import BIData
from tools.fond_rapport.diversification import ContributionRow, DiversificationWindow
from tools.fond_rapport.drivkraft import (
    UNCLASSIFIED_LABEL,
    _weights_by_driver,
    compute_driver_exposure,
    compute_driver_risk_share,
    has_driver_data,
    renormalized_over_classified,
)

EMPTY = pd.DataFrame()


# --- _weights_by_driver / renormalized_over_classified --------------------------


def test_weights_by_driver_groups_and_isolates_unclassified():
    weights = pd.Series({"AAA": 0.5, "BBB": 0.3, "CCC": 0.2})
    driver_by_key = pd.Series({"AAA": "Bred marknadsbeta", "BBB": "Bred marknadsbeta", "CCC": pd.NA})

    grouped = _weights_by_driver(weights, driver_by_key)

    assert grouped.sum() == pytest.approx(1.0, rel=1e-12)
    assert grouped["Bred marknadsbeta"] == pytest.approx(0.8, rel=1e-12)
    assert grouped[UNCLASSIFIED_LABEL] == pytest.approx(0.2, rel=1e-12)


def test_weights_by_driver_missing_from_lookup_counts_as_unclassified():
    """Instrument som inte alls finns i Fondertabell (t.ex. benchmark) - ingen gissning."""
    weights = pd.Series({"AAA": 0.7, "BM_X": 0.3})
    driver_by_key = pd.Series({"AAA": "Bred marknadsbeta"})

    grouped = _weights_by_driver(weights, driver_by_key)

    assert grouped[UNCLASSIFIED_LABEL] == pytest.approx(0.3, rel=1e-12)


def test_renormalized_over_classified_sums_to_one_excluding_unclassified():
    weights_by_driver = pd.Series(
        {"Bred marknadsbeta": 0.4, "Stabilitet & skydd": 0.4, UNCLASSIFIED_LABEL: 0.2}
    )

    out = renormalized_over_classified(weights_by_driver)

    assert UNCLASSIFIED_LABEL not in out.index
    assert out.sum() == pytest.approx(1.0, rel=1e-12)
    assert out["Bred marknadsbeta"] == pytest.approx(0.5, rel=1e-12)


def test_renormalized_over_classified_all_unclassified_returns_empty():
    weights_by_driver = pd.Series({UNCLASSIFIED_LABEL: 1.0})
    out = renormalized_over_classified(weights_by_driver)
    assert out.empty


# --- compute_driver_exposure ------------------------------------------------------


def _exposure_bidata() -> BIData:
    dim_instrument = pd.DataFrame(
        [
            {"Instrument_Key": "AAA", "Driver": "Bred marknadsbeta"},
            {"Instrument_Key": "BBB", "Driver": "Stabilitet & skydd"},
            {"Instrument_Key": "CCC", "Driver": pd.NA},
        ]
    )
    fact_alloc = pd.DataFrame(
        [
            {"Portfolio_Key": "EGEN", "Series_ID": "PORT_EGEN_REAL", "Instrument_Key": "AAA", "Weight": 0.5},
            {"Portfolio_Key": "EGEN", "Series_ID": "PORT_EGEN_REAL", "Instrument_Key": "BBB", "Weight": 0.3},
            {"Portfolio_Key": "EGEN", "Series_ID": "PORT_EGEN_REAL", "Instrument_Key": "CCC", "Weight": 0.2},
            # CUR-serien ska inte påverka REAL-Nuläget.
            {"Portfolio_Key": "EGEN", "Series_ID": "PORT_EGEN_CUR", "Instrument_Key": "AAA", "Weight": 1.0},
        ]
    )
    fact_alloc_monthly = pd.DataFrame(
        [
            {
                "Portfolio_Key": "EGEN",
                "Instrument_Key": "AAA",
                "Period_End_Date": pd.Timestamp("2024-06-30"),
                "Weight": 0.5,
            },
            {
                "Portfolio_Key": "EGEN",
                "Instrument_Key": "BBB",
                "Period_End_Date": pd.Timestamp("2024-06-30"),
                "Weight": 0.3,
            },
            {
                "Portfolio_Key": "EGEN",
                "Instrument_Key": "CCC",
                "Period_End_Date": pd.Timestamp("2024-06-30"),
                "Weight": 0.2,
            },
        ]
    )
    return BIData(
        dim_date=EMPTY,
        dim_portfolio=EMPTY,
        dim_series=EMPTY,
        dim_instrument=dim_instrument,
        fact_daily=EMPTY,
        fact_kpi=EMPTY,
        fact_alloc=fact_alloc,
        fact_alloc_monthly=fact_alloc_monthly,
    )


def test_compute_driver_exposure_snapshot_and_since_start():
    data = _exposure_bidata()
    inception = pd.Timestamp("2024-01-01")
    as_of = pd.Timestamp("2024-06-30")

    result = compute_driver_exposure(data, ["EGEN"], inception, as_of)

    assert result is not None
    window = result["EGEN"]
    assert window.snapshot_weights.sum() == pytest.approx(1.0, rel=1e-9)
    assert window.snapshot_weights["Bred marknadsbeta"] == pytest.approx(0.5, rel=1e-9)
    assert window.snapshot_weights["Stabilitet & skydd"] == pytest.approx(0.3, rel=1e-9)
    assert window.snapshot_weights[UNCLASSIFIED_LABEL] == pytest.approx(0.2, rel=1e-9)

    assert window.since_start_weights.sum() == pytest.approx(1.0, rel=1e-9)
    # Motorvikterna summerar till 100 % över klassade innehav.
    classified = renormalized_over_classified(window.snapshot_weights)
    assert classified.sum() == pytest.approx(1.0, rel=1e-9)


def test_compute_driver_exposure_none_when_driver_column_missing():
    data = _exposure_bidata()
    data = dataclasses.replace(data, dim_instrument=data.dim_instrument.drop(columns=["Driver"]))

    result = compute_driver_exposure(data, ["EGEN"], pd.Timestamp("2024-01-01"), pd.Timestamp("2024-06-30"))
    assert result is None
    assert not has_driver_data(data)


def test_compute_driver_exposure_none_when_no_fund_classified():
    data = _exposure_bidata()
    unclassified_dim = data.dim_instrument.copy()
    unclassified_dim["Driver"] = pd.NA
    data = dataclasses.replace(data, dim_instrument=unclassified_dim)

    result = compute_driver_exposure(data, ["EGEN"], pd.Timestamp("2024-01-01"), pd.Timestamp("2024-06-30"))
    assert result is None


# --- compute_driver_risk_share -----------------------------------------------------


def _diversification_window(portfolio: str) -> DiversificationWindow:
    contributions = [
        ContributionRow("AAA", "Fond AAA", weight=0.5, risk_contribution=0.6, ratio=1.2),
        ContributionRow("BBB", "Fond BBB", weight=0.3, risk_contribution=0.1, ratio=0.1 / 0.3),
        ContributionRow("CCC", "Fond CCC", weight=0.2, risk_contribution=0.3, ratio=1.5),
    ]
    return DiversificationWindow(
        portfolio=portfolio, period="Since_Start", dr=1.5, enb=2.0, n=3, contributions=contributions
    )


def test_compute_driver_risk_share_sums_to_mctr_total_and_computes_ratio():
    data = _exposure_bidata()
    diversification = {"EGEN": [_diversification_window("EGEN")]}

    result = compute_driver_risk_share(data, diversification)

    assert result is not None
    share = result["EGEN"]
    total_contrib = sum(r.risk_contribution for r in diversification["EGEN"][0].contributions)
    assert share.risk_share.sum() == pytest.approx(total_contrib, rel=1e-9)
    assert share.risk_share.sum() == pytest.approx(1.0, rel=1e-9)

    # AAA är ensam i "Bred marknadsbeta": kvoten ska matcha dess egen ratio exakt.
    assert share.ratio["Bred marknadsbeta"] == pytest.approx(1.2, rel=1e-9)
    # CCC (oklassad, ratio 1.5) driver kvoten > 1 för Oklassad-bucketen.
    assert share.ratio[UNCLASSIFIED_LABEL] == pytest.approx(1.5, rel=1e-9)


def test_compute_driver_risk_share_none_when_diversification_missing():
    data = _exposure_bidata()
    assert compute_driver_risk_share(data, None) is None
    assert compute_driver_risk_share(data, {}) is None


def test_compute_driver_risk_share_none_when_no_fund_classified():
    data = _exposure_bidata()
    unclassified_dim = data.dim_instrument.copy()
    unclassified_dim["Driver"] = pd.NA
    data = dataclasses.replace(data, dim_instrument=unclassified_dim)
    diversification = {"EGEN": [_diversification_window("EGEN")]}

    assert compute_driver_risk_share(data, diversification) is None
