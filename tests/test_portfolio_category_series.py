import pandas as pd
import pytest

from src.outputs import build_master_timeseries_long
from src.portfolio import (
    COL_AFFARSDAG,
    COL_PORTFOLJ,
    EngineInputs,
    build_portfolio_series_map,
    build_portfolios_and_benchmarks,
    build_series_definition,
    slug,
)


BUY = "K\u00d6PT"
SELL = "S\u00c5LT"
RATE_CATEGORY = "R\u00e4ntor & L\u00e5grisk"


@pytest.fixture
def base_frames():
    portfolio_metadata = pd.DataFrame(
        [
            {
                "Portfolio_Name": "EGEN",
                "Index_Start_Date": pd.Timestamp("2024-01-01"),
                "Initial_Index_Value": 100.0,
            }
        ]
    )
    benchmarks = pd.DataFrame(columns=["Benchmark_ID", "Yahoo_Ticker", "Include_From_Date"])
    fondertabell = pd.DataFrame(
        [
            {COL_PORTFOLJ: "EGEN", "Yahoo": "AAA", "Andel": 1.0, "AndelP": 1.0},
        ]
    )
    prices = pd.DataFrame(
        {"AAA": [100.0, 110.0, 110.0, 120.0, 120.0]},
        index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
    )
    return portfolio_metadata, benchmarks, fondertabell, prices


def test_series_definition_adds_slugged_real_category_series(base_frames):
    portfolio_metadata, benchmarks, _fondertabell, _prices = base_frames
    mapping = pd.DataFrame(
        [
            {
                "ISIN": "SE0001",
                "Name": "Sverige Indexfond",
                "Yahoo_Ticker": "AAA",
                "Instrument_Type": "Fund",
                "Price_Currency": "SEK",
                "Category": "Sverige&Norden / Mix",
            }
        ]
    )
    transactions = pd.DataFrame(
        [
            {
                "Portfolio_Name": "EGEN",
                COL_AFFARSDAG: pd.Timestamp("2024-01-02"),
                "ISIN": "SE0001",
                "Antal": 1.0,
                "Transaktionstyp": BUY,
                "Belopp": -110.0,
                "Valuta": "SEK",
            }
        ]
    )

    series_definition = build_series_definition(
        portfolio_metadata,
        benchmarks,
        mapping,
        transactions,
        real_tickers=["AAA"],
        model_tickers=["AAA"],
    )

    series_id = "PORT_EGEN_REAL_CAT_SVERIGE_NORDEN_MIX"
    row = series_definition.loc[series_definition["Series_ID"] == series_id].iloc[0]

    assert row["Series_Type"] == "PORT"
    assert row["Variant"] == "REAL"
    assert row["Category"] == "Sverige&Norden / Mix"
    assert "&" not in series_id
    assert "/" not in series_id
    assert " " not in series_id


def test_real_category_series_is_flat_without_holdings_and_written_to_outputs(base_frames):
    portfolio_metadata, benchmarks, fondertabell, prices = base_frames
    mapping = pd.DataFrame(
        [
            {
                "ISIN": "SE0001",
                "Name": "Sverige Indexfond",
                "Yahoo_Ticker": "AAA",
                "Instrument_Type": "Fund",
                "Price_Currency": "SEK",
                "Category": "Sverige&Norden",
            }
        ]
    )
    transactions = pd.DataFrame(
        [
            {
                "Portfolio_Name": "EGEN",
                COL_AFFARSDAG: pd.Timestamp("2024-01-02"),
                "ISIN": "SE0001",
                "Antal": 1.0,
                "Transaktionstyp": BUY,
                "Belopp": -110.0,
                "Valuta": "SEK",
            },
            {
                "Portfolio_Name": "EGEN",
                COL_AFFARSDAG: pd.Timestamp("2024-01-04"),
                "ISIN": "SE0001",
                "Antal": 1.0,
                "Transaktionstyp": SELL,
                "Belopp": 120.0,
                "Valuta": "SEK",
            },
        ]
    )
    inputs = EngineInputs(
        transactions=transactions,
        mapping=mapping,
        portfolio_metadata=portfolio_metadata,
        benchmarks=benchmarks,
        fondertabell=fondertabell,
        prices=prices,
        base_currency="SEK",
    )

    series_map = build_portfolios_and_benchmarks(inputs)
    series_id = "PORT_EGEN_REAL_CAT_SVERIGE_NORDEN"

    assert series_id in series_map
    category_series = series_map[series_id]
    assert category_series.index.min() == pd.Timestamp("2024-01-01")
    assert category_series.loc[pd.Timestamp("2024-01-01"), "RET"] == 0.0
    assert category_series.loc[pd.Timestamp("2024-01-01"), "IDX"] == 100.0
    assert category_series.loc[pd.Timestamp("2024-01-05"), "RET"] == 0.0
    assert category_series.loc[pd.Timestamp("2024-01-05"), "IDX"] == category_series.loc[pd.Timestamp("2024-01-04"), "IDX"]

    master_long = build_master_timeseries_long(series_map)
    master_series_ids = set(master_long["Series_ID"].unique())
    assert series_id in master_series_ids


def test_missing_category_for_real_holding_raises(base_frames):
    portfolio_metadata, benchmarks, fondertabell, prices = base_frames
    mapping = pd.DataFrame(
        [
            {
                "ISIN": "SE0001",
                "Name": "Sverige Indexfond",
                "Yahoo_Ticker": "AAA",
                "Instrument_Type": "Fund",
                "Price_Currency": "SEK",
                "Category": None,
            }
        ]
    )
    transactions = pd.DataFrame(
        [
            {
                "Portfolio_Name": "EGEN",
                COL_AFFARSDAG: pd.Timestamp("2024-01-02"),
                "ISIN": "SE0001",
                "Antal": 1.0,
                "Transaktionstyp": BUY,
                "Belopp": -110.0,
                "Valuta": "SEK",
            }
        ]
    )
    inputs = EngineInputs(
        transactions=transactions,
        mapping=mapping,
        portfolio_metadata=portfolio_metadata,
        benchmarks=benchmarks,
        fondertabell=fondertabell,
        prices=prices,
        base_currency="SEK",
    )

    with pytest.raises(ValueError, match="Missing Category for ISIN"):
        build_portfolios_and_benchmarks(inputs)


def test_category_real_uses_sleeve_returns_for_internal_reallocation():
    portfolio_metadata = pd.DataFrame(
        [
            {
                "Portfolio_Name": "PA",
                "Index_Start_Date": pd.Timestamp("2024-01-01"),
                "Initial_Index_Value": 100.0,
            }
        ]
    )
    benchmarks = pd.DataFrame(columns=["Benchmark_ID", "Yahoo_Ticker", "Include_From_Date"])
    fondertabell = pd.DataFrame(
        [
            {COL_PORTFOLJ: "PA", "Yahoo": "AAA", "Andel": 1.0, "AndelP": 1.0},
        ]
    )
    mapping = pd.DataFrame(
        [
            {"ISIN": "SE0001", "Yahoo_Ticker": "AAA", "Instrument_Type": "Fund", "Price_Currency": "SEK", "Category": RATE_CATEGORY},
            {"ISIN": "SE0002", "Yahoo_Ticker": "BBB", "Instrument_Type": "Fund", "Price_Currency": "SEK", "Category": "Aktier"},
        ]
    )
    prices = pd.DataFrame(
        {
            "AAA": [100.0, 100.0, 101.0, 101.0],
            "BBB": [100.0, 100.0, 100.0, 100.0],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]),
    )
    transactions = pd.DataFrame(
        [
            {"Portfolio_Name": "PA", COL_AFFARSDAG: pd.Timestamp("2024-01-01"), "ISIN": "SE0001", "Antal": 10.0, "Transaktionstyp": BUY, "Belopp": -1000.0, "Valuta": "SEK"},
            {"Portfolio_Name": "PA", COL_AFFARSDAG: pd.Timestamp("2024-01-01"), "ISIN": "SE0002", "Antal": 10.0, "Transaktionstyp": BUY, "Belopp": -1000.0, "Valuta": "SEK"},
            {"Portfolio_Name": "PA", COL_AFFARSDAG: pd.Timestamp("2024-01-02"), "ISIN": "SE0001", "Antal": 10.0, "Transaktionstyp": BUY, "Belopp": -1000.0, "Valuta": "SEK"},
            {"Portfolio_Name": "PA", COL_AFFARSDAG: pd.Timestamp("2024-01-02"), "ISIN": "SE0002", "Antal": 10.0, "Transaktionstyp": SELL, "Belopp": 1000.0, "Valuta": "SEK"},
        ]
    )
    inputs = EngineInputs(
        transactions=transactions,
        mapping=mapping,
        portfolio_metadata=portfolio_metadata,
        benchmarks=benchmarks,
        fondertabell=fondertabell,
        prices=prices,
        base_currency="SEK",
    )

    series_map = build_portfolios_and_benchmarks(inputs)

    total_series = series_map["PORT_PA_REAL"]
    category_series = series_map[f"PORT_PA_REAL_CAT_{slug(RATE_CATEGORY)}"]

    assert total_series.loc[pd.Timestamp("2024-01-02"), "RET"] == pytest.approx(0.0)
    assert category_series.loc[pd.Timestamp("2024-01-02"), "RET"] == pytest.approx(0.0)
    assert category_series.loc[pd.Timestamp("2024-01-03"), "RET"] == pytest.approx(0.01)
    assert category_series["RET"].abs().max() < 0.30


def test_build_portfolio_series_map_includes_real_snapshot_from_transactions(base_frames):
    portfolio_metadata, benchmarks, fondertabell, prices = base_frames
    mapping = pd.DataFrame(
        [
            {
                "ISIN": "SE0001",
                "Name": "Sverige Indexfond",
                "Yahoo_Ticker": "AAA",
                "Instrument_Type": "Fund",
                "Price_Currency": "SEK",
                "Category": "Sverige",
            }
        ]
    )
    transactions = pd.DataFrame(
        [
            {
                "Portfolio_Name": "EGEN",
                COL_AFFARSDAG: pd.Timestamp("2024-01-02"),
                "ISIN": "SE0001",
                "Antal": 1.0,
                "Transaktionstyp": BUY,
                "Belopp": -110.0,
                "Valuta": "SEK",
            }
        ]
    )

    portfolio_series_map = build_portfolio_series_map(
        portfolio_metadata,
        transactions,
        mapping,
        fondertabell,
        prices,
        base_currency="SEK",
    )

    real_rows = portfolio_series_map.loc[portfolio_series_map["Series_ID"] == "PORT_EGEN_REAL"].copy()

    assert not real_rows.empty
    assert real_rows["Display_Name"].tolist() == ["Sverige Indexfond"]
    assert real_rows["Yahoo_Ticker"].tolist() == ["AAA"]
    assert real_rows["Weight_Source"].tolist() == ["REAL"]
    assert real_rows["Weight"].iloc[0] == pytest.approx(1.0)


def test_real_total_aligns_weekend_trade_to_next_price_day_not_bokforingsdag():
    portfolio_metadata = pd.DataFrame(
        [
            {
                "Portfolio_Name": "PA",
                "Index_Start_Date": pd.Timestamp("2024-01-05"),
                "Initial_Index_Value": 100.0,
            }
        ]
    )
    benchmarks = pd.DataFrame(columns=["Benchmark_ID", "Yahoo_Ticker", "Include_From_Date"])
    fondertabell = pd.DataFrame(
        [
            {COL_PORTFOLJ: "PA", "Yahoo": "AAA", "Andel": 1.0, "AndelP": 1.0},
        ]
    )
    mapping = pd.DataFrame(
        [
            {"ISIN": "SE0001", "Yahoo_Ticker": "AAA", "Instrument_Type": "Fund", "Price_Currency": "SEK", "Category": RATE_CATEGORY},
            {"ISIN": "SE0002", "Yahoo_Ticker": "BBB", "Instrument_Type": "Fund", "Price_Currency": "SEK", "Category": RATE_CATEGORY},
        ]
    )
    prices = pd.DataFrame(
        {
            "AAA": [100.0, 100.0, 100.0, 100.0],
            "BBB": [100.0, 100.0, 100.0, 100.0],
        },
        index=pd.to_datetime(["2024-01-05", "2024-01-08", "2024-01-09", "2024-01-10"]),
    )
    transactions = pd.DataFrame(
        [
            {
                "Portfolio_Name": "PA",
                COL_AFFARSDAG: pd.Timestamp("2024-01-05"),
                "Bokföringsdag": pd.Timestamp("2024-01-08"),
                "ISIN": "SE0001",
                "Antal": 10.0,
                "Transaktionstyp": BUY,
                "Belopp": -1000.0,
                "Valuta": "SEK",
            },
            {
                "Portfolio_Name": "PA",
                COL_AFFARSDAG: pd.Timestamp("2024-01-06"),
                "Bokföringsdag": pd.Timestamp("2024-01-09"),
                "ISIN": "SE0001",
                "Antal": 10.0,
                "Transaktionstyp": SELL,
                "Belopp": 1000.0,
                "Valuta": "SEK",
            },
            {
                "Portfolio_Name": "PA",
                COL_AFFARSDAG: pd.Timestamp("2024-01-09"),
                "Bokföringsdag": pd.Timestamp("2024-01-10"),
                "ISIN": "SE0002",
                "Antal": 10.0,
                "Transaktionstyp": BUY,
                "Belopp": -1000.0,
                "Valuta": "SEK",
            },
        ]
    )
    inputs = EngineInputs(
        transactions=transactions,
        mapping=mapping,
        portfolio_metadata=portfolio_metadata,
        benchmarks=benchmarks,
        fondertabell=fondertabell,
        prices=prices,
        base_currency="SEK",
    )

    series_map = build_portfolios_and_benchmarks(inputs)
    total_series = series_map["PORT_PA_REAL"]

    assert total_series.loc[pd.Timestamp("2024-01-08"), "RET"] == pytest.approx(0.0)
    assert total_series.loc[pd.Timestamp("2024-01-09"), "RET"] == pytest.approx(0.0)
    assert total_series.loc[pd.Timestamp("2024-01-10"), "RET"] == pytest.approx(0.0)
