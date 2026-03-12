"""Separate step that prepares dashboard-ready tables from Portfolio_index output."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from . import config
from .dashboard_io import (
    build_analysis_master_long,
    build_analysis_metadata,
    extract_run_parameters,
    load_dashboard_source,
)
from .dashboard_tables import (
    build_allocation_snapshot,
    build_build_info,
    build_chart_wide,
    build_correlation_long,
    build_dashboard_config,
    build_kpi_summary,
    build_period_returns,
)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-path",
        default=None,
        help="Path to portfolio_output_timeseries.xlsx",
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Path to portfolio_dashboard_data.xlsx",
    )
    return parser.parse_args()


def run(
    source_output_path: str | Path | None = None,
    dashboard_output_path: str | Path | None = None,
) -> None:
    """Read Portfolio_index output and write dashboard-ready workbook."""
    _configure_logging()

    source_path = Path(source_output_path or config.DASHBOARD_SOURCE_OUTPUT_PATH)
    output_path = Path(dashboard_output_path or config.DASHBOARD_OUTPUT_PATH)

    logging.info("Loading dashboard source workbook: %s", source_path)
    source = load_dashboard_source(source_path)
    rf_rate_annual, trading_days_per_year = extract_run_parameters(source.run_config)
    analysis_metadata = build_analysis_metadata(source)
    analysis_master_long = build_analysis_master_long(source, analysis_metadata)

    date_min = analysis_master_long["Date"].min()
    date_max = analysis_master_long["Date"].max()
    portfolio_count = analysis_metadata.loc[analysis_metadata["Series_Type"] == "PORT", "Portfolio_Name"].nunique()
    benchmark_count = int((analysis_metadata["Series_Type"] == "BM").sum())

    logging.info(
        "Dashboard analysis universe: %s series (%s portfolios, %s benchmarks), %s -> %s",
        len(analysis_metadata),
        portfolio_count,
        benchmark_count,
        date_min.date().isoformat(),
        date_max.date().isoformat(),
    )

    kpi_summary = build_kpi_summary(
        analysis_master_long,
        analysis_metadata,
        rf_rate_annual,
        trading_days_per_year,
    )
    period_returns = build_period_returns(analysis_master_long, analysis_metadata)
    chart_idx_wide = build_chart_wide(analysis_master_long, analysis_metadata, "IDX")
    chart_dd_wide = build_chart_wide(analysis_master_long, analysis_metadata, "DD")
    correlation_long = build_correlation_long(analysis_master_long, analysis_metadata)
    allocation_snapshot = build_allocation_snapshot(
        source.portfolio_series_map,
        source.series_definition,
    )
    dashboard_config = build_dashboard_config()
    build_info = build_build_info(
        source_output_file=str(source.source_path),
        master_long=analysis_master_long,
        analysis_metadata=analysis_metadata,
        rf_rate_annual=rf_rate_annual,
        trading_days_per_year=trading_days_per_year,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        kpi_summary.to_excel(writer, sheet_name="KPI_Summary", index=False)
        period_returns.to_excel(writer, sheet_name="Period_Returns", index=False)
        chart_idx_wide.to_excel(writer, sheet_name="Chart_IDX_Wide", index=False)
        chart_dd_wide.to_excel(writer, sheet_name="Chart_DD_Wide", index=False)
        correlation_long.to_excel(writer, sheet_name="Correlation_Long", index=False)
        allocation_snapshot.to_excel(writer, sheet_name="Allocation_Snapshot", index=False)
        dashboard_config.to_excel(writer, sheet_name="Dashboard_Config", index=False)
        build_info.to_excel(writer, sheet_name="Build_Info", index=False)

    logging.info("Dashboard workbook written: %s", output_path)


if __name__ == "__main__":
    args = _parse_args()
    run(
        source_output_path=args.input_path,
        dashboard_output_path=args.output_path,
    )
