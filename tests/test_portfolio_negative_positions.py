import pandas as pd
import pytest

from src.portfolio import (
    COL_AFFARSDAG,
    COL_PORTFOLJ,
    EngineInputs,
    build_portfolios_and_benchmarks,
)

BUY = "KÖPT"
SELL = "SÅLT"


def test_sell_without_prior_buy_stops_the_run():
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
    prices = pd.DataFrame(
        {"AAA": [100.0, 110.0, 120.0]},
        index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
    )
    # Försäljning utan föregående köp – ackumulerat innehav går till -5.
    transactions = pd.DataFrame(
        [
            {
                "Portfolio_Name": "EGEN",
                COL_AFFARSDAG: pd.Timestamp("2024-01-02"),
                "ISIN": "SE0001",
                "Antal": 5.0,
                "Transaktionstyp": SELL,
                "Belopp": 550.0,
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

    with pytest.raises(ValueError, match=r"Negative accumulated position.*SE0001"):
        build_portfolios_and_benchmarks(inputs)
