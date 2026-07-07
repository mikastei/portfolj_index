"""Tester för policyreferensindexen (src/policy.py).

Täcker kraven: viktsumma 1,0 varje dag, reset-logik vid årsskifte (analytiskt
facit), fri drift inom året samt FX-konvertering i bucketpriserna.
"""

import numpy as np
import pandas as pd
import pytest

from src.policy import (
    AKTIER_BUCKET_SERIES_ID,
    build_policy_series,
    build_policy_series_definition,
    policy_return_path,
)


def _bucket_returns(dates: list[str], aktier: list[float], rantor: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"Aktier": aktier, "Rantor": rantor}, index=pd.DatetimeIndex(pd.to_datetime(dates))
    )


class TestPolicyReturnPath:
    def test_viktsumma_ar_1_varje_dag(self):
        rng = np.random.default_rng(42)
        dates = pd.bdate_range("2024-01-02", periods=400)
        rets = pd.DataFrame(
            {
                "Aktier": rng.normal(0.0005, 0.01, len(dates)),
                "Rantor": rng.normal(0.0001, 0.001, len(dates)),
            },
            index=dates,
        )
        _, weight_path = policy_return_path(rets, {"Aktier": 0.9, "Rantor": 0.1})
        sums = weight_path.sum(axis=1)
        assert np.allclose(sums.to_numpy(), 1.0, atol=1e-12)

    def test_reset_vid_arsskifte_analytiskt_facit(self):
        # Aktier +10 %/dag, Räntor 0 %/dag kring årsskiftet 2024/2025.
        rets = _bucket_returns(
            ["2024-12-30", "2024-12-31", "2025-01-02", "2025-01-03"],
            aktier=[0.0, 0.10, 0.10, 0.10],
            rantor=[0.0, 0.0, 0.0, 0.0],
        )
        port_ret, weight_path = policy_return_path(rets, {"Aktier": 0.9, "Rantor": 0.1})

        # 2024-12-31: strategivikterna gäller fortfarande (drift från nolldag).
        assert port_ret.iloc[1] == pytest.approx(0.9 * 0.10)
        # 2025-01-02: reset till 90/10 – INTE de driftade vikterna 0.99/1.09.
        assert weight_path.iloc[2]["Aktier"] == pytest.approx(0.9)
        assert port_ret.iloc[2] == pytest.approx(0.9 * 0.10)
        # 2025-01-03: fri drift inom det nya året.
        drifted = 0.9 * 1.10 / (0.9 * 1.10 + 0.1)
        assert weight_path.iloc[3]["Aktier"] == pytest.approx(drifted)
        assert port_ret.iloc[3] == pytest.approx(drifted * 0.10)

    def test_drift_inom_ar_sluten_form(self):
        # Konstanta dagsavkastningar inom ett år: vikten följer den slutna formen
        # w(n) = w0(1+ra)^n / (w0(1+ra)^n + (1-w0)(1+rr)^n).
        n_days = 60
        ra, rr, w0 = 0.005, 0.0002, 0.85
        dates = pd.bdate_range("2025-02-03", periods=n_days)  # inget årsskifte
        rets = pd.DataFrame({"Aktier": ra, "Rantor": rr}, index=dates)
        port_ret, weight_path = policy_return_path(rets, {"Aktier": w0, "Rantor": 1 - w0})

        for n in (1, 10, n_days - 1):
            expected = (
                w0 * (1 + ra) ** n / (w0 * (1 + ra) ** n + (1 - w0) * (1 + rr) ** n)
            )
            assert weight_path.iloc[n]["Aktier"] == pytest.approx(expected, rel=1e-12)

        # Buy-and-hold-identiteten inom året: produkten av policyavkastningarna
        # är strategiviktade produkten av bucketavkastningarna.
        total = float((1 + port_ret).prod())
        expected_total = w0 * (1 + ra) ** n_days + (1 - w0) * (1 + rr) ** n_days
        assert total == pytest.approx(expected_total, rel=1e-12)

    def test_viktsumma_krav_pa_strategivikter(self):
        rets = _bucket_returns(["2025-01-02"], [0.0], [0.0])
        with pytest.raises(ValueError, match="summera till 1.0"):
            policy_return_path(rets, {"Aktier": 0.9, "Rantor": 0.2})

    def test_saknad_bucketvikt_ger_fel(self):
        rets = _bucket_returns(["2025-01-02"], [0.0], [0.0])
        with pytest.raises(ValueError, match="Strategivikt saknas"):
            policy_return_path(rets, {"Aktier": 1.0})


class TestBuildPolicySeries:
    @staticmethod
    def _fixtures():
        benchmarks = pd.DataFrame(
            {
                "Benchmark_ID": ["BM_ACWI_UCITS", "BM_Short_Corp_Bond"],
                "Yahoo_Ticker": ["IUSQ.DE", "0P00000KJ0.ST"],
                "Price_Currency": ["EUR", "SEK"],
                "Include_From_Date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
            }
        )
        metadata = pd.DataFrame(
            {
                "Portfolio_Name": ["EGEN", "PA"],
                "Index_Start_Date": pd.to_datetime(["2024-01-01", "2024-01-01"]),
                "Initial_Index_Value": [100.0, 100.0],
            }
        )
        dates = pd.bdate_range("2024-01-02", periods=10)
        prices = pd.DataFrame(
            {
                "IUSQ.DE": np.linspace(70.0, 73.0, len(dates)),
                "0P00000KJ0.ST": np.linspace(500.0, 501.0, len(dates)),
                "EURSEK=X": np.linspace(11.0, 11.2, len(dates)),
            },
            index=dates,
        )
        buckets = {"Aktier": "BM_ACWI_UCITS", "Rantor": "BM_Short_Corp_Bond"}
        weights = {"EGEN": {"Aktier": 0.9, "Rantor": 0.1}, "PA": {"Aktier": 0.85, "Rantor": 0.15}}
        return benchmarks, metadata, prices, buckets, weights

    def test_serier_byggs_med_fx_konvertering(self):
        benchmarks, metadata, prices, buckets, weights = self._fixtures()
        series = build_policy_series(benchmarks, metadata, prices, "SEK", buckets, weights)
        assert set(series) == {"POLICY_EGEN", "POLICY_PA", AKTIER_BUCKET_SERIES_ID}

        # Aktiebucketen är EUR-priset konverterat till SEK.
        aktier_sek = prices["IUSQ.DE"] * prices["EURSEK=X"]
        expected_idx = 100.0 * aktier_sek / aktier_sek.iloc[0]
        bucket = series[AKTIER_BUCKET_SERIES_ID]
        assert np.allclose(bucket["IDX"].to_numpy(), expected_idx.to_numpy(), rtol=1e-12)
        # IDX startar på basindexvärdet.
        for frame in series.values():
            assert frame["IDX"].iloc[0] == pytest.approx(100.0)

    def test_saknad_fx_serie_ger_fel(self):
        benchmarks, metadata, prices, buckets, weights = self._fixtures()
        with pytest.raises(ValueError, match="FX-serie"):
            build_policy_series(
                benchmarks, metadata, prices.drop(columns=["EURSEK=X"]), "SEK", buckets, weights
            )

    def test_tom_konfiguration_ger_tomt(self):
        benchmarks, metadata, prices, _, _ = self._fixtures()
        assert build_policy_series(benchmarks, metadata, prices, "SEK", {}, {}) == {}
        assert build_policy_series_definition(benchmarks, metadata, {}, {}).empty

    def test_series_definition_rader(self):
        benchmarks, metadata, _, buckets, weights = self._fixtures()
        definition = build_policy_series_definition(benchmarks, metadata, buckets, weights)
        assert list(definition["Series_ID"]) == [
            "POLICY_EGEN",
            "POLICY_PA",
            AKTIER_BUCKET_SERIES_ID,
        ]
        assert (definition["Series_Type"] == "POLICY").all()
        egen = definition[definition["Series_ID"] == "POLICY_EGEN"].iloc[0]
        assert egen["Portfolio_Name"] == "EGEN"
        assert "90/10" in egen["Display_Name"]
