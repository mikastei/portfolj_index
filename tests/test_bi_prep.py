import pandas as pd
import pytest

from src.bi_prep import (
    _apply_ter_seed,
    _build_analysis_metadata,
    _build_dim_instrument,
    _build_dim_portfolio,
    _clean_text,
    _combine_optional_columns,
    _nullable_text,
    _warn_on_unclassified_active_holdings,
)


def test_clean_text_strips_and_normalizes_na_markers():
    series = pd.Series([" AAA ", None, "nan", "NaT", "<NA>", "BBB"])
    out = _clean_text(series)
    assert out.tolist() == ["AAA", "", "", "", "", "BBB"]


def test_nullable_text_masks_empty_strings_as_na():
    series = pd.Series(["  ", "AAA", None])
    out = _nullable_text(series)
    assert out.isna().tolist() == [True, False, True]
    assert out.dropna().tolist() == ["AAA"]


def test_combine_optional_columns_prefers_map_then_series():
    df = pd.DataFrame(
        {
            "Category_map": ["Aktier", pd.NA, pd.NA],
            "Category_series": [pd.NA, "Rantor", pd.NA],
        }
    )
    out = _combine_optional_columns(df, "Category")
    assert out.iloc[0] == "Aktier"
    assert out.iloc[1] == "Rantor"
    assert pd.isna(out.iloc[2])


def test_combine_optional_columns_returns_direct_column_when_no_suffixes():
    df = pd.DataFrame({"Category": ["Aktier", "Rantor"]})
    out = _combine_optional_columns(df, "Category")
    assert out.tolist() == ["Aktier", "Rantor"]


def _series_definition_row(series_id, series_type, portfolio_name=pd.NA, category=pd.NA):
    return {
        "Series_ID": series_id,
        "Series_Type": series_type,
        "Portfolio_Name": portfolio_name,
        "Variant": pd.NA,
        "Benchmark_ID": pd.NA,
        "Yahoo_Ticker": pd.NA,
        "ISIN": pd.NA,
        "Display_Name": series_id,
        "Price_Currency": pd.NA,
        "Instrument_Type": pd.NA,
        "Category": category,
        "Geography": pd.NA,
        "Index_Start_Date": pd.Timestamp("2026-01-01"),
        "Initial_Index_Value": 100.0,
        "Include_From_Date": pd.NaT,
    }


def test_build_analysis_metadata_flags_main_and_benchmark_series():
    series_definition = pd.DataFrame(
        [
            _series_definition_row("PORT_EGEN_REAL", "PORT", portfolio_name="EGEN"),
            _series_definition_row("BM_GLOBAL", "BM"),
        ]
    )
    master_long = pd.DataFrame({"Series_ID": ["PORT_EGEN_REAL", "PORT_EGEN_REAL", "BM_GLOBAL"]})

    metadata = _build_analysis_metadata(series_definition, master_long)

    port_row = metadata.loc[metadata["Series_ID"] == "PORT_EGEN_REAL"].iloc[0]
    bm_row = metadata.loc[metadata["Series_ID"] == "BM_GLOBAL"].iloc[0]
    assert bool(port_row["Is_Main_Portfolio_Series"]) is True
    assert bool(bm_row["Is_Benchmark"]) is True
    assert bool(bm_row["Is_Overview_Eligible"]) is True


def test_build_analysis_metadata_raises_when_missing_metadata():
    series_definition = pd.DataFrame([_series_definition_row("BM_GLOBAL", "BM")])
    master_long = pd.DataFrame({"Series_ID": ["PORT_EGEN_REAL", "BM_GLOBAL"]})

    with pytest.raises(ValueError, match="missing BI metadata"):
        _build_analysis_metadata(series_definition, master_long)


def test_build_dim_portfolio_dedupes_by_portfolio_name():
    analysis_metadata = pd.DataFrame(
        {
            "Portfolio_Name": ["EGEN", "EGEN", pd.NA],
            "Index_Start_Date": [pd.Timestamp("2026-01-01")] * 3,
            "Initial_Index_Value": [100.0, 100.0, 100.0],
        }
    )
    out = _build_dim_portfolio(analysis_metadata)
    assert out["Portfolio_Name"].tolist() == ["EGEN"]
    assert out["Portfolio_Key"].tolist() == ["EGEN"]


def _dim_instrument_row(isin, ter=pd.NA, ter_status=pd.NA, ter_source=pd.NA):
    return {
        "Instrument_Key": f"KEY_{isin}",
        "Yahoo_Ticker": f"TICK_{isin}",
        "ISIN": isin,
        "Display_Name": f"Fond {isin}",
        "TER": ter,
        "TER_Status": ter_status,
        "TER_Source": ter_source,
    }


def _write_ter_seed(tmp_path, rows, filename="ter_seed.csv"):
    path = tmp_path / filename
    lines = ["ISIN;Namn;TER;Kalla;Datum;Kommentar"]
    lines += [f"{isin};Fond {isin};{ter};nordnet-web;2026-07-19;" for isin, ter in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_apply_ter_seed_fills_only_no_data_rows(tmp_path):
    dim_instrument = pd.DataFrame(
        [
            _dim_instrument_row("SE0000000001", ter=pd.NA, ter_status="no_data"),
            _dim_instrument_row("SE0000000002", ter=0.20, ter_status="ok", ter_source="nordnet"),
        ]
    )
    seed_path = _write_ter_seed(tmp_path, [("SE0000000001", 0.54), ("SE0000000002", 9.99)])

    out = _apply_ter_seed(dim_instrument, seed_path)

    seeded = out.loc[out["ISIN"] == "SE0000000001"].iloc[0]
    assert seeded["TER"] == pytest.approx(0.54)
    assert seeded["TER_Status"] == "ok"
    assert seeded["TER_Source"] == "seed"


def test_apply_ter_seed_never_overwrites_scraped_value(tmp_path):
    dim_instrument = pd.DataFrame(
        [_dim_instrument_row("SE0000000002", ter=0.20, ter_status="ok", ter_source="nordnet")]
    )
    seed_path = _write_ter_seed(tmp_path, [("SE0000000002", 9.99)])

    out = _apply_ter_seed(dim_instrument, seed_path)

    row = out.iloc[0]
    assert row["TER"] == pytest.approx(0.20)
    assert row["TER_Status"] == "ok"
    assert row["TER_Source"] == "nordnet"


def test_apply_ter_seed_sets_source_seed_for_missing_status_too(tmp_path):
    # TER_Status kan vara helt saknad (NA) om instrumentet inte fanns i
    # Instrument_Cost-universumet alls – ska behandlas som "saknat TER".
    dim_instrument = pd.DataFrame([_dim_instrument_row("SE0000000003", ter=pd.NA, ter_status=pd.NA)])
    seed_path = _write_ter_seed(tmp_path, [("SE0000000003", 1.05)])

    out = _apply_ter_seed(dim_instrument, seed_path)

    row = out.iloc[0]
    assert row["TER"] == pytest.approx(1.05)
    assert row["TER_Status"] == "ok"
    assert row["TER_Source"] == "seed"


def test_apply_ter_seed_missing_file_warns_and_leaves_unchanged(tmp_path, caplog):
    dim_instrument = pd.DataFrame([_dim_instrument_row("SE0000000001", ter=pd.NA, ter_status="no_data")])
    missing_path = tmp_path / "does_not_exist.csv"

    with caplog.at_level("WARNING"):
        out = _apply_ter_seed(dim_instrument, missing_path)

    assert pd.isna(out.iloc[0]["TER"])
    assert out.iloc[0]["TER_Status"] == "no_data"
    assert "seedfil saknas" in caplog.text.lower()


def test_apply_ter_seed_unknown_isin_warns_and_continues(tmp_path, caplog):
    dim_instrument = pd.DataFrame(
        [_dim_instrument_row("SE0000000001", ter=pd.NA, ter_status="no_data")]
    )
    seed_path = _write_ter_seed(
        tmp_path, [("SE0000000001", 0.54), ("SE0009999999", 1.00)]
    )

    with caplog.at_level("WARNING"):
        out = _apply_ter_seed(dim_instrument, seed_path)

    assert out.loc[out["ISIN"] == "SE0000000001"].iloc[0]["TER"] == pytest.approx(0.54)
    assert "SE0009999999" in caplog.text
    assert "finns inte i instrumentuniversumet" in caplog.text


# --- Drivkraft / Driver ([BD]) ---------------------------------------------------


def _map_row(ticker):
    return {
        "Yahoo_Ticker": ticker,
        "ISIN": f"ISIN_{ticker}",
        "Display_Name": f"Fond {ticker}",
        "Price_Currency": "SEK",
    }


def test_build_dim_instrument_includes_driver_column():
    portfolio_series_map = pd.DataFrame([_map_row("AAA"), _map_row("BBB")])
    series_definition = pd.DataFrame(
        [
            _series_definition_row("AST_AAA", "AST") | {"Yahoo_Ticker": "AAA", "Driver": "Bred marknadsbeta"},
            _series_definition_row("AST_BBB", "AST") | {"Yahoo_Ticker": "BBB", "Driver": pd.NA},
        ]
    )

    dim_instrument = _build_dim_instrument(series_definition, portfolio_series_map)

    assert "Driver" in dim_instrument.columns
    row_a = dim_instrument.loc[dim_instrument["Instrument_Key"] == "AAA"].iloc[0]
    row_b = dim_instrument.loc[dim_instrument["Instrument_Key"] == "BBB"].iloc[0]
    assert row_a["Driver"] == "Bred marknadsbeta"
    assert pd.isna(row_b["Driver"])


def test_build_dim_instrument_missing_driver_column_warns_and_defaults_empty(caplog):
    """Uppström-workbook byggd före [BD] saknar Driver-kolumnen helt - graceful,
    ingen krasch, samma mönster som andra optionella kolumner i denna funktion."""
    portfolio_series_map = pd.DataFrame([_map_row("AAA")])
    series_definition = pd.DataFrame([_series_definition_row("AST_AAA", "AST") | {"Yahoo_Ticker": "AAA"}])
    assert "Driver" not in series_definition.columns

    with caplog.at_level("WARNING"):
        dim_instrument = _build_dim_instrument(series_definition, portfolio_series_map)

    assert "Driver" in dim_instrument.columns
    assert dim_instrument["Driver"].isna().all()
    assert any("Driver" in record.message for record in caplog.records)


def test_warn_on_unclassified_active_holdings_logs_warning(caplog):
    dim_instrument = pd.DataFrame(
        [
            {"Instrument_Key": "AAA", "Driver": "Bred marknadsbeta"},
            {"Instrument_Key": "BBB", "Driver": pd.NA},
        ]
    )
    snapshot = pd.DataFrame(
        [
            {"Instrument_Key": "AAA", "Weight": 0.6},
            {"Instrument_Key": "BBB", "Weight": 0.4},
        ]
    )

    with caplog.at_level("WARNING"):
        _warn_on_unclassified_active_holdings(dim_instrument, snapshot)

    assert "BBB" in caplog.text
    assert "AAA" not in caplog.text


def test_warn_on_unclassified_active_holdings_silent_when_all_classified(caplog):
    dim_instrument = pd.DataFrame([{"Instrument_Key": "AAA", "Driver": "Bred marknadsbeta"}])
    snapshot = pd.DataFrame([{"Instrument_Key": "AAA", "Weight": 1.0}])

    with caplog.at_level("WARNING"):
        _warn_on_unclassified_active_holdings(dim_instrument, snapshot)

    assert caplog.text == ""


def test_warn_on_unclassified_active_holdings_ignores_zero_weight_rows(caplog):
    """Endast innehav med vikt > 0 i snapshotet räknas som aktiva - en oklassad
    fond med 0 % vikt (t.ex. utträdd) ska inte trigga kanariefågeln."""
    dim_instrument = pd.DataFrame([{"Instrument_Key": "AAA", "Driver": pd.NA}])
    snapshot = pd.DataFrame([{"Instrument_Key": "AAA", "Weight": 0.0}])

    with caplog.at_level("WARNING"):
        _warn_on_unclassified_active_holdings(dim_instrument, snapshot)

    assert caplog.text == ""
