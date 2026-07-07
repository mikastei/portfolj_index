"""Tester för fond-rapportens policyregression (tools/fond_rapport/policy.py).

Täcker kraven: veckoaggregeringen (analytiskt facit), fre–fre-logiken kring
helgdag, regression med känt beta/alfa på veckobas, R²-spärren samt den
datumstyrda preliminär-markeringen.
"""

import numpy as np
import pandas as pd
import pytest

from tools.fond_rapport.policy import (
    PRELIMINARY_YEARS,
    R2_THRESHOLD,
    WEEKS_PER_YEAR,
    PolicyRegression,
    annualize_alpha,
    regress_returns,
    weekly_returns,
)


def _regression(r2: float, end: str, preliminary_until: str) -> PolicyRegression:
    return PolicyRegression(
        portfolio="EGEN",
        policy_series_id="POLICY_EGEN",
        start=pd.Timestamp("2024-08-21"),
        end=pd.Timestamp(end),
        n_obs=100,
        beta=0.8,
        alpha_weekly=0.0005,
        alpha_annual=annualize_alpha(0.0005),
        r2=r2,
        preliminary_until=pd.Timestamp(preliminary_until),
    )


class TestWeeklyReturns:
    def test_analytiskt_facit_tva_hela_veckor(self):
        # Mån 2025-01-13 – fre 2025-01-24: två hela handelsveckor utan helgdag.
        dates = pd.bdate_range("2025-01-13", "2025-01-24")
        rets = pd.Series([0.01, -0.02, 0.03, 0.0, 0.01, 0.02, 0.02, -0.01, 0.0, 0.01], index=dates)

        weekly = weekly_returns(rets)

        assert list(weekly.index) == [pd.Timestamp("2025-01-17"), pd.Timestamp("2025-01-24")]
        v1 = 1.01 * 0.98 * 1.03 * 1.00 * 1.01 - 1.0
        v2 = 1.02 * 1.02 * 0.99 * 1.00 * 1.01 - 1.0
        assert weekly.iloc[0] == pytest.approx(v1, rel=1e-12)
        assert weekly.iloc[1] == pytest.approx(v2, rel=1e-12)

    def test_helgdag_pa_fredag_ger_torsdag_som_veckoslut(self):
        # Långfredag 2025-04-18: veckan slutar torsdag 2025-04-17; annandag påsk
        # 2025-04-21 gör att nästa vecka startar tisdag – båda utanför buckets.
        dates = pd.bdate_range("2025-04-14", "2025-04-25")
        dates = dates[~dates.isin([pd.Timestamp("2025-04-18"), pd.Timestamp("2025-04-21")])]
        rets = pd.Series(0.01, index=dates)

        weekly = weekly_returns(rets)

        assert list(weekly.index) == [pd.Timestamp("2025-04-17"), pd.Timestamp("2025-04-25")]
        assert weekly.iloc[0] == pytest.approx(1.01**4 - 1.0, rel=1e-12)  # mån–tor
        assert weekly.iloc[1] == pytest.approx(1.01**4 - 1.0, rel=1e-12)  # tis–fre

    def test_kantvecka_kapitaliseras_over_sina_dagar(self):
        # Serie som startar onsdag: första veckobucketen rymmer ons–fre.
        dates = pd.bdate_range("2025-01-15", "2025-01-24")  # ons – fre veckan därpå
        rets = pd.Series(0.01, index=dates)
        weekly = weekly_returns(rets)
        assert weekly.index[0] == pd.Timestamp("2025-01-17")
        assert weekly.iloc[0] == pytest.approx(1.01**3 - 1.0, rel=1e-12)

    def test_tom_vecka_utelamnas(self):
        # Hela mellanveckan saknar handelsdagar – den ska inte ge någon observation.
        dates = pd.DatetimeIndex(["2025-01-13", "2025-01-17", "2025-01-27", "2025-01-31"])
        rets = pd.Series(0.01, index=dates)
        weekly = weekly_returns(rets)
        assert list(weekly.index) == [pd.Timestamp("2025-01-17"), pd.Timestamp("2025-01-31")]

    def test_dataframe_aggregeras_kolumnvis_pa_samma_buckets(self):
        dates = pd.bdate_range("2025-01-13", "2025-01-24")
        frame = pd.DataFrame({"real": 0.01, "policy": 0.02}, index=dates)
        weekly = weekly_returns(frame)
        assert list(weekly.columns) == ["real", "policy"]
        assert len(weekly) == 2
        assert weekly["real"].iloc[0] == pytest.approx(1.01**5 - 1.0, rel=1e-12)
        assert weekly["policy"].iloc[0] == pytest.approx(1.02**5 - 1.0, rel=1e-12)


class TestRegressReturns:
    def test_kant_beta_alfa_pa_veckobas(self):
        # Veckoserier via weekly_returns: känt samband ska återvinnas exakt.
        rng = np.random.default_rng(7)
        dates = pd.bdate_range("2024-08-21", periods=500)
        daily_x = pd.Series(rng.normal(0.0004, 0.01, len(dates)), index=dates)
        x = weekly_returns(daily_x)
        true_beta, true_alpha = 0.85, 0.0008
        y = true_alpha + true_beta * x

        beta, alpha, r2, n = regress_returns(y, x)
        assert beta == pytest.approx(true_beta, rel=1e-12)
        assert alpha == pytest.approx(true_alpha, rel=1e-9)
        assert r2 == pytest.approx(1.0)
        assert n == len(x)
        assert 90 <= n <= 110  # ~100 veckor av ~500 handelsdagar

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

    def test_annualiserad_alfa_pa_veckobas(self):
        assert WEEKS_PER_YEAR == 52
        assert annualize_alpha(0.0) == pytest.approx(0.0)
        assert annualize_alpha(0.0005) == pytest.approx(1.0005**52 - 1.0)
