"""Tester för fond-rapportens policyregression (tools/fond_rapport/policy.py).

Täcker kraven: regression mot syntetisk serie med känt beta/alfa, R²-spärren
samt den datumstyrda preliminär-markeringen.
"""

import numpy as np
import pandas as pd
import pytest

from tools.fond_rapport.policy import (
    PRELIMINARY_YEARS,
    R2_THRESHOLD,
    PolicyRegression,
    annualize_alpha,
    regress_returns,
)


def _regression(r2: float, end: str, preliminary_until: str) -> PolicyRegression:
    return PolicyRegression(
        portfolio="EGEN",
        policy_series_id="POLICY_EGEN",
        start=pd.Timestamp("2024-08-21"),
        end=pd.Timestamp(end),
        n_obs=500,
        beta=0.8,
        alpha_daily=0.0001,
        alpha_annual=annualize_alpha(0.0001),
        r2=r2,
        preliminary_until=pd.Timestamp(preliminary_until),
    )


class TestRegressReturns:
    def test_kant_beta_alfa_utan_brus(self):
        rng = np.random.default_rng(7)
        dates = pd.bdate_range("2024-08-21", periods=500)
        x = pd.Series(rng.normal(0.0004, 0.01, len(dates)), index=dates)
        true_beta, true_alpha = 0.85, 0.0002
        y = true_alpha + true_beta * x

        beta, alpha, r2, n = regress_returns(y, x)
        assert beta == pytest.approx(true_beta, rel=1e-12)
        assert alpha == pytest.approx(true_alpha, rel=1e-9)
        assert r2 == pytest.approx(1.0)
        assert n == len(dates)

    def test_brus_ger_lag_r2(self):
        rng = np.random.default_rng(11)
        dates = pd.bdate_range("2024-08-21", periods=500)
        x = pd.Series(rng.normal(0.0004, 0.01, len(dates)), index=dates)
        noise = pd.Series(rng.normal(0.0, 0.05, len(dates)), index=dates)
        y = 0.0002 + 0.85 * x + noise

        _, _, r2, _ = regress_returns(y, x)
        assert r2 < R2_THRESHOLD

    def test_datum_alignas_via_inner_join(self):
        dates_x = pd.bdate_range("2025-01-02", periods=10)
        dates_y = dates_x[2:]  # y saknar de två första dagarna
        x = pd.Series(np.linspace(0.001, 0.01, len(dates_x)), index=dates_x)
        y = 2.0 * x.reindex(dates_y)
        beta, _, _, n = regress_returns(y, x)
        assert n == len(dates_y)
        assert beta == pytest.approx(2.0, rel=1e-12)

    def test_for_fa_observationer_ger_fel(self):
        dates = pd.bdate_range("2025-01-02", periods=2)
        s = pd.Series([0.01, 0.02], index=dates)
        with pytest.raises(ValueError, match="För få"):
            regress_returns(s, s)


class TestGrindarOchMarkering:
    def test_r2_sparren(self):
        assert _regression(0.71, "2026-07-06", "2027-08-21").show_beta_alpha
        assert not _regression(0.70, "2026-07-06", "2027-08-21").show_beta_alpha
        assert not _regression(0.30, "2026-07-06", "2027-08-21").show_beta_alpha

    def test_preliminar_ar_datumstyrd(self):
        # Före treårsgränsen: preliminärt. På/efter gränsen: inte preliminärt.
        assert _regression(0.9, "2026-07-06", "2027-08-21").preliminary
        assert not _regression(0.9, "2027-08-21", "2027-08-21").preliminary
        assert not _regression(0.9, "2027-09-01", "2027-08-21").preliminary

    def test_preliminar_grans_ar_tre_ar(self):
        assert PRELIMINARY_YEARS == 3

    def test_annualiserad_alfa(self):
        assert annualize_alpha(0.0) == pytest.approx(0.0)
        assert annualize_alpha(0.0001) == pytest.approx(1.0001**252 - 1.0)
