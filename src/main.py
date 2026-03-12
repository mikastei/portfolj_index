"""Portfolio Index Engine entrypoint."""

from __future__ import annotations

import logging

import pandas as pd

from .bootstrap import init_ssl


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def run() -> None:
    init_ssl()

    from . import config
    from .io_excel import load_inputs
    from .outputs import build_master_timeseries_long, build_run_config, write_output_excel
    from .portfolio import (
        EngineInputs,
        build_portfolio_series_map,
        build_portfolios_and_benchmarks,
        build_series_definition,
        discover_fx_tickers,
        required_tickers,
    )
    from .prices import download_adj_close

    _configure_logging()
    logging.info("Loading Excel inputs")
    tables = load_inputs(config.PATH_TRANSAKTIONER, config.PATH_FONDER)

    tickers = required_tickers(
        tables["transactions"],
        tables["mapping"],
        tables["benchmarks"],
        tables["fondertabell"],
        base_currency=config.BASE_CURRENCY,
    )
    fx_tickers = discover_fx_tickers(
        tables["mapping"],
        tables["benchmarks"],
        base_currency=config.BASE_CURRENCY,
    )
    download_tickers = sorted(set(tickers["all"]) | set(fx_tickers))
    logging.info(
        "Discovered %s total tickers (%s real, %s model, %s benchmarks)",
        len(download_tickers),
        len(tickers["real"]),
        len(tickers["model"]),
        len(tickers["benchmarks"]),
    )
    if fx_tickers:
        logging.info("FX tickers added for conversion: %s", fx_tickers)

    start_date = pd.to_datetime(tables["portfolio_metadata"]["Index_Start_Date"], errors="coerce").min()
    prices = download_adj_close(
        tickers=download_tickers,
        start_date=start_date,
        end_date=None,
        forward_fill=config.FORWARD_FILL,
        fx_tickers=fx_tickers,
    )

    inputs = EngineInputs(
        transactions=tables["transactions"],
        mapping=tables["mapping"],
        portfolio_metadata=tables["portfolio_metadata"],
        benchmarks=tables["benchmarks"],
        fondertabell=tables["fondertabell"],
        prices=prices,
        base_currency=config.BASE_CURRENCY,
    )

    series_map = build_portfolios_and_benchmarks(inputs)
    series_definition = build_series_definition(
        tables["portfolio_metadata"],
        tables["benchmarks"],
        tables["mapping"],
        tables["transactions"],
        tickers["real"],
        tickers["model"],
    )
    portfolio_series_map = build_portfolio_series_map(
        tables["portfolio_metadata"],
        tables["fondertabell"],
    )
    master_long = build_master_timeseries_long(series_map)
    run_config = build_run_config(
        path_transaktioner=config.PATH_TRANSAKTIONER,
        path_fonder=config.PATH_FONDER,
        output_path=config.OUTPUT_PATH,
        rf_rate_annual=config.RF_RATE_ANNUAL,
        base_currency=config.BASE_CURRENCY,
        trading_days_per_year=config.TRADING_DAYS_PER_YEAR,
        forward_fill=config.FORWARD_FILL,
    )

    write_output_excel(
        output_path=config.OUTPUT_PATH,
        series_definition=series_definition,
        portfolio_series_map=portfolio_series_map,
        master_long=master_long,
        run_config=run_config,
    )

    bm_count = sum(1 for sid in series_map if sid.startswith("BM_"))
    port_count = tables["portfolio_metadata"]["Portfolio_Name"].astype(str).nunique()
    min_date = master_long["Date"].min() if not master_long.empty else None
    max_date = master_long["Date"].max() if not master_long.empty else None

    print(f"Number of portfolios: {port_count}")
    print(f"Number of benchmarks: {bm_count}")
    print(f"Date range: {min_date} -> {max_date}")
    print(f"Output path: {config.OUTPUT_PATH}")


if __name__ == "__main__":
    run()
