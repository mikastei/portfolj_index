"""Output table assembly and Excel export."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


def build_master_timeseries_long(series_map: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for series_id, df in series_map.items():
        if not (series_id.startswith("PORT_") or series_id.startswith("BM_")):
            continue
        part = df.copy()
        part = part.reset_index()
        part["Series_ID"] = series_id
        rows.append(part[["Date", "Series_ID", "RET", "IDX", "DD"]])
    if not rows:
        return pd.DataFrame(columns=["Date", "Series_ID", "RET", "IDX", "DD"])
    out = pd.concat(rows, ignore_index=True)
    out["Date"] = pd.to_datetime(out["Date"])
    return out.sort_values(["Series_ID", "Date"]).reset_index(drop=True)


def build_run_config(
    path_transaktioner: str,
    path_fonder: str,
    output_path: str,
    rf_rate_annual: float,
    base_currency: str,
    trading_days_per_year: int,
    forward_fill: bool,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Timestamp": datetime.now(),
                "PATH_TRANSAKTIONER": path_transaktioner,
                "PATH_FONDER": path_fonder,
                "OUTPUT_PATH": output_path,
                "RF_RATE_ANNUAL": rf_rate_annual,
                "BASE_CURRENCY": base_currency,
                "TRADING_DAYS_PER_YEAR": trading_days_per_year,
                "FORWARD_FILL": bool(forward_fill),
                "NO_REBALANCING": True,
            }
        ]
    )


def write_output_excel(
    output_path: str,
    series_definition: pd.DataFrame,
    portfolio_series_map: pd.DataFrame,
    master_long: pd.DataFrame,
    run_config: pd.DataFrame,
) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        series_definition.to_excel(writer, sheet_name="Series_Definition", index=False)
        portfolio_series_map.to_excel(writer, sheet_name="Portfolio_Series_Map", index=False)
        master_long.to_excel(writer, sheet_name="Master_TimeSeries_Long", index=False)
        run_config.to_excel(writer, sheet_name="Run_Config", index=False)
