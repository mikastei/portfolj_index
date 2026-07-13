"""Output table assembly and Excel export."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


def build_master_timeseries_long(series_map: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for series_id, df in series_map.items():
        if not series_id.startswith(("PORT_", "BM_", "POLICY_")):
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


INSTRUMENT_COST_COLUMNS = ["ISIN", "Instrument_Type", "TER", "TER_Status", "TER_Source"]


def build_instrument_cost(mapping: pd.DataFrame, fund_costs: pd.DataFrame) -> pd.DataFrame:
    """Löpande avgift (TER) per instrument, nyckel ISIN, för hela mapping-universumet.

    TER hämtas från Fondanalys usa_exposure-skrapning (``fund_costs``). Instrument
    som saknas i skrapningen eller där Nordnet inte visade avgiften får TER=NA och
    en talande status (``no_data``/``missing``/``parse_error``/``url_error``) så att
    täckningen kan rapporteras. Inget värde hittas på. TER lagras som Nordnets råa
    procentvärde (t.ex. 1.55 = 1,55 %).
    """
    map_df = mapping.copy()
    map_df["ISIN"] = map_df["ISIN"].astype(str).str.strip()
    instrument_type = (
        map_df["Instrument_Type"].fillna("").astype(str).str.strip()
        if "Instrument_Type" in map_df.columns
        else ""
    )
    map_df = map_df.assign(Instrument_Type=instrument_type)
    universe = (
        map_df[map_df["ISIN"] != ""]
        .drop_duplicates(subset=["ISIN"], keep="first")[["ISIN", "Instrument_Type"]]
        .sort_values("ISIN")
        .reset_index(drop=True)
    )
    if universe.empty:
        return pd.DataFrame(columns=INSTRUMENT_COST_COLUMNS)

    costs = fund_costs.copy() if fund_costs is not None else pd.DataFrame()
    if costs.empty or "ISIN" not in costs.columns:
        costs = pd.DataFrame(columns=["ISIN", "TER", "TER_Status"])
    costs["ISIN"] = costs["ISIN"].astype(str).str.strip()

    merged = universe.merge(costs[["ISIN", "TER", "TER_Status"]], on="ISIN", how="left")
    merged["TER"] = pd.to_numeric(merged["TER"], errors="coerce")
    # ISIN som helt saknar rad i skrapningen → no_data (skiljs från 'ok'/'missing' m.fl.).
    merged["TER_Status"] = merged["TER_Status"].where(merged["TER_Status"].notna(), "no_data")
    merged["TER_Status"] = merged["TER_Status"].astype(str).str.strip().replace("", "no_data")
    merged["TER_Source"] = merged["TER"].notna().map({True: "nordnet", False: pd.NA})
    merged["Instrument_Type"] = merged["Instrument_Type"].replace("", pd.NA)
    return merged[INSTRUMENT_COST_COLUMNS]


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
                # CUR/TGT beräknas som fasta vikter mot dagliga tillgångsavkastningar
                # (_portfolio_returns_from_weights), vilket matematiskt motsvarar daglig
                # ombalansering till målvikterna – inte avsaknad av ombalansering.
                "DAILY_REBALANCING": True,
            }
        ]
    )


def write_output_excel(
    output_path: str,
    series_definition: pd.DataFrame,
    portfolio_series_map: pd.DataFrame,
    master_long: pd.DataFrame,
    run_config: pd.DataFrame,
    portfolio_alloc_monthly: pd.DataFrame | None = None,
    instrument_cost: pd.DataFrame | None = None,
    portfolio_courtage: pd.DataFrame | None = None,
) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        series_definition.to_excel(writer, sheet_name="Series_Definition", index=False)
        portfolio_series_map.to_excel(writer, sheet_name="Portfolio_Series_Map", index=False)
        if portfolio_alloc_monthly is not None:
            portfolio_alloc_monthly.to_excel(
                writer, sheet_name="Portfolio_Alloc_Monthly", index=False
            )
        if instrument_cost is not None:
            instrument_cost.to_excel(writer, sheet_name="Instrument_Cost", index=False)
        if portfolio_courtage is not None:
            portfolio_courtage.to_excel(writer, sheet_name="Portfolio_Courtage", index=False)
        master_long.to_excel(writer, sheet_name="Master_TimeSeries_Long", index=False)
        run_config.to_excel(writer, sheet_name="Run_Config", index=False)
