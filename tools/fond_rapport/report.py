"""HTML-bygge för fond-rapporten.

Rapporten ställer EGEN (den verkliga portföljen) mot PA – referensportföljen som
EGEN ska slå – plus externa benchmarks, allt över ett gemensamt analysfönster som
startar vid EGEN:s inception. Alla serier rebaseras till bas 100 vid startdatumet
och skärs till [inception, as_of]; alla horisonter och KPI:er räknas relativt
as-of. Inga tal är hårdkodade i prosan – sifferunderlaget injiceras ur de beräknade
fönster-KPI:erna.
"""

from __future__ import annotations

import html

import pandas as pd

from . import charts
from .attribution import TOP_N_FUNDS, PortfolioAttribution
from .costs import CostsResult
from .data import BIData, series_index
from .metrics import KPI_COLUMNS as METRIC_KPIS
from .verify import VerificationResult
from .window import Horizon, rebase_series

PORTFOLIOS = ["PA", "EGEN"]

HEADLINE_SERIES = "PORT_EGEN_REAL"
REFERENCE_SERIES = "PORT_PA_REAL"

SERIES_LABELS = {
    "PORT_PA_REAL": "PA – Verklig portfölj (REAL)",
    "PORT_PA_CUR": "PA – Nuvarande fondlista, konstantviktad (CUR)",
    "PORT_PA_TGT": "PA – Målvikter, konstantviktad (TGT)",
    "PORT_EGEN_REAL": "EGEN – Verklig portfölj (REAL)",
    "PORT_EGEN_CUR": "EGEN – Nuvarande fondlista, konstantviktad (CUR)",
    "PORT_EGEN_TGT": "EGEN – Målvikter, konstantviktad (TGT)",
    "BM_BM_NORDNET_BALANSERAD": "Nordnet Balanserad",
    "BM_BM_NORDNET_OFFENSIV": "Nordnet Offensiv",
    "BM_BM_OMX_STOCKHOLM_GI": "OMX Stockholm GI",
    "BM_BM_GLOBAL_LARGE": "Global Large Cap (ACWI)",
    "BM_BM_EMERGING_MARKETS": "Tillväxtmarknader (EEM)",
    "BM_BM_INTERMEDIATE_CORE_BOND": "Obligationer USA (AGG)",
}

KPI_TABLE_SERIES = [
    "PORT_PA_REAL",
    "PORT_PA_CUR",
    "PORT_PA_TGT",
    "PORT_EGEN_REAL",
    "PORT_EGEN_CUR",
    "PORT_EGEN_TGT",
    "BM_BM_NORDNET_BALANSERAD",
    "BM_BM_NORDNET_OFFENSIV",
    "BM_BM_OMX_STOCKHOLM_GI",
    "BM_BM_GLOBAL_LARGE",
    "BM_BM_EMERGING_MARKETS",
    "BM_BM_INTERMEDIATE_CORE_BOND",
]

KPI_COLUMNS = [
    ("Return_Total", "Totalavkastning", "pct"),
    ("CAGR", "CAGR", "pct"),
    ("Vol", "Volatilitet", "pct"),
    ("Sharpe", "Sharpe", "num"),
    ("Sortino", "Sortino", "num"),
    ("Max_DD", "Max drawdown", "pct"),
    ("Calmar", "Calmar", "num"),
]


# --- formattering (svensk decimalstil) ---------------------------------------


def fmt_pct(value: float, decimals: int = 1) -> str:
    if pd.isna(value):
        return "–"
    return f"{value * 100.0:.{decimals}f}".replace(".", ",") + " %"


def fmt_num(value: float, decimals: int = 2) -> str:
    if pd.isna(value):
        return "–"
    return f"{value:.{decimals}f}".replace(".", ",")


def fmt_idx(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def fmt_pp(value: float, decimals: int = 1) -> str:
    """Skillnad i procentenheter, med tecken."""
    if pd.isna(value):
        return "–"
    return f"{value * 100.0:+.{decimals}f}".replace(".", ",") + " p.e."


def _fore_efter(diff: float) -> str:
    return "före" if diff > 0 else "efter"


# --- fönsterserier ------------------------------------------------------------


def _windowed(data: BIData, series_id: str, inception: pd.Timestamp, as_of: pd.Timestamp) -> pd.Series:
    """Rebaserad (bas 100 vid inception) och as-of-skuren IDX-serie."""
    return rebase_series(series_index(data, series_id), inception, as_of)


# --- tabellhjälp --------------------------------------------------------------


def _kpi_table(kpi: pd.DataFrame, period: str) -> str:
    sub = kpi[kpi["Period"] == period].set_index("Series_ID")
    header = "".join(f"<th>{label}</th>" for _, label, _ in KPI_COLUMNS)
    rows = []
    for series_id in KPI_TABLE_SERIES:
        if series_id not in sub.index:
            continue
        row = sub.loc[series_id]
        cells = []
        for column, _, kind in KPI_COLUMNS:
            value = float(row[column])
            cells.append(f"<td>{fmt_pct(value) if kind == 'pct' else fmt_num(value)}</td>")
        css = ' class="real-row"' if series_id.endswith("_REAL") else ""
        rows.append(f"<tr{css}><td>{SERIES_LABELS[series_id]}</td>{''.join(cells)}</tr>")
    return (
        f"<table><thead><tr><th>Serie</th>{header}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _horizon_table(kpi: pd.DataFrame, horizons: list[Horizon]) -> str:
    """Avkastning per horisont: kumulativ (<1 år) eller CAGR (≥1 år), per serie."""
    shown = kpi.set_index(["Series_ID", "Period"])
    available = [h for h in horizons if h.available]
    header_cells = "".join(
        "<th>{}<br><span class=\"sub\">{}<br>{}</span></th>".format(
            h.label,
            "kumulativ" if h.measure == "cumulative" else "CAGR",
            h.date_range(),
        )
        for h in available
    )
    rows = []
    for series_id in KPI_TABLE_SERIES:
        cells = []
        for h in available:
            key = (series_id, h.key)
            if key in shown.index:
                column = "Return_Total" if h.measure == "cumulative" else "CAGR"
                cells.append(f"<td>{fmt_pct(float(shown.loc[key, column]))}</td>")
            else:
                cells.append("<td>–</td>")
        css = ' class="real-row"' if series_id.endswith("_REAL") else ""
        rows.append(f"<tr{css}><td>{SERIES_LABELS[series_id]}</td>{''.join(cells)}</tr>")
    table = (
        f"<table><thead><tr><th>Serie</th>{header_cells}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    omitted = [h for h in horizons if not h.available]
    caption = ""
    if omitted:
        items = "".join(f"<li><strong>{h.label}:</strong> {html.escape(h.note)}</li>" for h in omitted)
        caption = f'<div class="warn"><p>Utelämnade horisonter:</p><ul>{items}</ul></div>'
    return table + caption


def _category_series(data: BIData, portfolio: str) -> list[tuple[str, str]]:
    """[(Series_ID, kategorinamn)] för portföljens REAL_CAT-serier."""
    dim = data.dim_series
    mask = (
        (dim["Portfolio_Key"] == portfolio)
        & (dim["Is_Category_Series"] == True)  # noqa: E712 – kolumnen är bool
    )
    return [(row["Series_ID"], row["Category"]) for _, row in dim[mask].iterrows()]


def _category_table(data: BIData, portfolio: str, kpi: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    shown = kpi.set_index(["Series_ID", "Period"])
    has_1y = "1Y" in set(kpi["Period"])
    rows = []
    for series_id, category in _category_series(data, portfolio):
        if (series_id, "Since_Start") not in shown.index:
            continue
        since = shown.loc[(series_id, "Since_Start")]
        ret_1y = (
            float(shown.loc[(series_id, "1Y"), "Return_Total"])
            if has_1y and (series_id, "1Y") in shown.index
            else float("nan")
        )
        rows.append(
            {
                "Kategori": category,
                "Ret_Since": float(since["Return_Total"]),
                "Ret_1Y": ret_1y,
                "Sharpe_Since": float(since["Sharpe"]),
                "MaxDD_Since": float(since["Max_DD"]),
            }
        )
    frame = pd.DataFrame(rows).sort_values("Ret_Since", ascending=False)
    body = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(row["Kategori"]),
            fmt_pct(row["Ret_Since"]),
            fmt_pct(row["Ret_1Y"]),
            fmt_num(row["Sharpe_Since"]),
            fmt_pct(row["MaxDD_Since"]),
        )
        for _, row in frame.iterrows()
    )
    table = (
        "<table><thead><tr><th>Kategori</th><th>Avkastning sedan start</th>"
        "<th>Avkastning 1 år</th><th>Sharpe (sedan start)</th>"
        "<th>Max drawdown (sedan start)</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )
    return table, frame


def _allocation_table(data: BIData, portfolio: str) -> str:
    alloc = data.fact_alloc[data.fact_alloc["Portfolio_Key"] == portfolio]
    pivot = alloc.pivot_table(
        index="Display_Name", columns="Series_ID", values="Weight", aggfunc="sum"
    )
    variant_order = [f"PORT_{portfolio}_{v}" for v in ("REAL", "CUR", "TGT")]
    pivot = pivot.reindex(columns=[c for c in variant_order if c in pivot.columns])
    pivot = pivot.sort_values(pivot.columns[0], ascending=False)
    header = "".join(f"<th>{c.rsplit('_', 1)[-1]}</th>" for c in pivot.columns)
    body = []
    for name, row in pivot.iterrows():
        cells = "".join(
            f"<td>{fmt_pct(v) if pd.notna(v) else '–'}</td>" for v in row.values
        )
        body.append(f"<tr><td>{html.escape(str(name))}</td>{cells}</tr>")
    return (
        f"<table><thead><tr><th>Instrument</th>{header}</tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


# --- sektionsbyggare ----------------------------------------------------------


def _relative_series(
    data: BIData, portfolio: str, inception: pd.Timestamp, as_of: pd.Timestamp
) -> list[tuple[str, pd.Series, str]]:
    real = _windowed(data, f"PORT_{portfolio}_REAL", inception, as_of)
    out = []
    for other_id, label, style in (
        (f"PORT_{portfolio}_CUR", "REAL / CUR", "CUR"),
        (f"PORT_{portfolio}_TGT", "REAL / TGT", "TGT"),
        ("BM_BM_NORDNET_BALANSERAD", "REAL / Nordnet Balanserad", "BM1"),
    ):
        other = _windowed(data, other_id, inception, as_of)
        joined = pd.concat([real, other], axis=1, join="inner", keys=["real", "other"])
        out.append((label, joined["real"] / joined["other"] * 100.0, style))
    return out


def _headline_section(
    data: BIData, inception: pd.Timestamp, as_of: pd.Timestamp
) -> str:
    series = [
        ("EGEN – verklig (REAL)", _windowed(data, "PORT_EGEN_REAL", inception, as_of), "EGEN"),
        ("PA – referens att slå (REAL)", _windowed(data, "PORT_PA_REAL", inception, as_of), "PA"),
        ("Nordnet Balanserad", _windowed(data, "BM_BM_NORDNET_BALANSERAD", inception, as_of), "BM1"),
        ("Nordnet Offensiv", _windowed(data, "BM_BM_NORDNET_OFFENSIV", inception, as_of), "BM2"),
    ]
    png = charts.line_chart(
        series,
        f"EGEN mot PA och externa benchmarks (bas 100 vid {inception.date()})",
        "Index (bas 100)",
        baseline=100.0,
    )
    return f'<img src="data:image/png;base64,{png}" alt="EGEN mot PA och benchmarks">'


def _facts(
    data: BIData, portfolio: str, kpi: pd.DataFrame, inception: pd.Timestamp, as_of: pd.Timestamp
) -> dict:
    """Beräknade nyckelvärden som tolkningssektionen bygger på (över fönstret)."""
    shown = kpi.set_index(["Series_ID", "Period"])
    has_1y = "1Y" in set(kpi["Period"])

    def since(series_id: str, column: str) -> float:
        return float(shown.loc[(series_id, "Since_Start"), column])

    def one_year(series_id: str, column: str) -> float:
        if not has_1y or (series_id, "1Y") not in shown.index:
            return float("nan")
        return float(shown.loc[(series_id, "1Y"), column])

    real, cur, tgt = (f"PORT_{portfolio}_{v}" for v in ("REAL", "CUR", "TGT"))
    bal, off = "BM_BM_NORDNET_BALANSERAD", "BM_BM_NORDNET_OFFENSIV"

    _, cat_frame = _category_table(data, portfolio, kpi)
    return {
        "idx_real": float(_windowed(data, real, inception, as_of).iloc[-1]),
        "idx_cur": float(_windowed(data, cur, inception, as_of).iloc[-1]),
        "idx_tgt": float(_windowed(data, tgt, inception, as_of).iloc[-1]),
        "ret_real": since(real, "Return_Total"),
        "ret_cur": since(cur, "Return_Total"),
        "ret_tgt": since(tgt, "Return_Total"),
        "cagr_real": since(real, "CAGR"),
        "sharpe_real": since(real, "Sharpe"),
        "sharpe_cur": since(cur, "Sharpe"),
        "vol_real": since(real, "Vol"),
        "vol_cur": since(cur, "Vol"),
        "maxdd_real": since(real, "Max_DD"),
        "ret_bal": since(bal, "Return_Total"),
        "ret_off": since(off, "Return_Total"),
        "sharpe_bal": since(bal, "Sharpe"),
        "ret_real_1y": one_year(real, "Return_Total"),
        "ret_bal_1y": one_year(bal, "Return_Total"),
        "has_1y": has_1y,
        "categories": cat_frame,
    }


def _portfolio_index_section(
    data: BIData, portfolio: str, inception: pd.Timestamp, as_of: pd.Timestamp
) -> str:
    main = [
        (SERIES_LABELS[f"PORT_{portfolio}_REAL"], _windowed(data, f"PORT_{portfolio}_REAL", inception, as_of), "REAL"),
        (SERIES_LABELS[f"PORT_{portfolio}_CUR"], _windowed(data, f"PORT_{portfolio}_CUR", inception, as_of), "CUR"),
        (SERIES_LABELS[f"PORT_{portfolio}_TGT"], _windowed(data, f"PORT_{portfolio}_TGT", inception, as_of), "TGT"),
        ("Nordnet Balanserad", _windowed(data, "BM_BM_NORDNET_BALANSERAD", inception, as_of), "BM1"),
        ("Nordnet Offensiv", _windowed(data, "BM_BM_NORDNET_OFFENSIV", inception, as_of), "BM2"),
    ]
    idx_png = charts.line_chart(main, f"{portfolio}: indexutveckling (bas 100 vid {inception.date()})", "Index", baseline=100.0)
    rel_png = charts.line_chart(
        _relative_series(data, portfolio, inception, as_of),
        f"{portfolio}: relativ utveckling – REAL mot referenser (100 = lika)",
        "Kvot × 100",
        baseline=100.0,
    )
    return (
        f"<h3>{portfolio}</h3>"
        f'<img src="data:image/png;base64,{idx_png}" alt="Index {portfolio}">'
        f'<img src="data:image/png;base64,{rel_png}" alt="Relativ utveckling {portfolio}">'
    )


def _category_section(
    data: BIData, portfolio: str, inception: pd.Timestamp, as_of: pd.Timestamp, kpi: pd.DataFrame
) -> str:
    cat_series = [
        (category, _windowed(data, series_id, inception, as_of))
        for series_id, category in _category_series(data, portfolio)
    ]
    png = charts.category_chart(cat_series, f"{portfolio}: kategoriserier (REAL, bas 100 vid {inception.date()})")
    table, frame = _category_table(data, portfolio, kpi)
    best = frame.iloc[0]
    worst = frame.iloc[-1]
    summary = (
        f"<p>Starkast sedan start: <strong>{html.escape(best['Kategori'])}</strong> "
        f"({fmt_pct(best['Ret_Since'])}). Svagast: "
        f"<strong>{html.escape(worst['Kategori'])}</strong> ({fmt_pct(worst['Ret_Since'])}).</p>"
    )
    return (
        f"<h3>{portfolio}</h3>"
        f'<img src="data:image/png;base64,{png}" alt="Kategorier {portfolio}">'
        f"{summary}{table}"
    )


def _allocation_section(data: BIData, portfolio: str) -> str:
    alloc = data.fact_alloc[
        (data.fact_alloc["Portfolio_Key"] == portfolio)
        & (data.fact_alloc["Series_ID"] == f"PORT_{portfolio}_REAL")
    ]
    weights = alloc.set_index("Display_Name")["Weight"]
    snapshot_date = pd.to_datetime(alloc["Snapshot_Date"].iloc[0]).date()
    png = charts.allocation_chart(
        weights, f"{portfolio}: verkliga vikter (REAL) per {snapshot_date}"
    )
    return (
        f"<h3>{portfolio}</h3>"
        f'<img src="data:image/png;base64,{png}" alt="Allokering {portfolio}">'
        f"<p>Vikter per variant (snapshot {snapshot_date}):</p>"
        f"{_allocation_table(data, portfolio)}"
    )


def _costs_section(costs: CostsResult, kpi: pd.DataFrame) -> str:
    """Sektion 6: löpande avgift (TER), avgiftsdekomponering och courtage."""
    shown = kpi.set_index(["Series_ID", "Period"])

    def since(series_id: str) -> float:
        return float(shown.loc[(series_id, "Since_Start"), "Return_Total"])

    egen, pa = costs.ter["EGEN"], costs.ter["PA"]

    # --- 6.1: tidsviktad TER och dagens listor ---------------------------------
    ter_chart = charts.line_chart(
        [
            ("EGEN – viktad TER på täckt vikt", egen.monthly["TER_Renorm"] * 100.0, "EGEN"),
            ("PA – viktad TER på täckt vikt", pa.monthly["TER_Renorm"] * 100.0, "PA"),
        ],
        "Viktad TER per periodslut (renormaliserad på täckt vikt)",
        "TER (%/år)",
    )
    tw_rows = "".join(
        f"<tr><td>{p.portfolio}</td><td>{fmt_pct(p.ter_tw_renorm, 2)}</td>"
        f"<td>{fmt_pct(p.ter_tw_lower, 2)}</td><td>{fmt_pct(p.coverage_tw)}</td>"
        f"<td>{p.uncovered_periods}</td></tr>"
        for p in (egen, pa)
    )
    tw_table = (
        "<table><thead><tr><th>Portfölj</th><th>Tidsviktad TER (täckt vikt)</th>"
        "<th>Undre gräns (otäckt := 0)</th><th>Dagviktad täckning</th>"
        "<th>Periodslut utan täckning</th></tr></thead>"
        f"<tbody>{tw_rows}</tbody></table>"
    )
    snap_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            p.portfolio,
            fmt_pct(p.snapshot_ter.get("REAL", float("nan")), 2),
            fmt_pct(p.snapshot_ter.get("CUR", float("nan")), 2),
            fmt_pct(p.snapshot_ter.get("TGT", float("nan")), 2),
        )
        for p in (egen, pa)
    )
    snap_table = (
        "<table><thead><tr><th>Portfölj</th><th>REAL i dag</th><th>CUR</th><th>TGT</th>"
        f"</tr></thead><tbody>{snap_rows}</tbody></table>"
    )

    monthly = pd.concat(
        [egen.monthly.add_prefix("EGEN_"), pa.monthly.add_prefix("PA_")], axis=1
    )
    monthly_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            pd.Timestamp(pe).date(),
            fmt_pct(row["EGEN_Coverage"]),
            fmt_pct(row["EGEN_TER_Renorm"], 2),
            fmt_pct(row["PA_Coverage"]),
            fmt_pct(row["PA_TER_Renorm"], 2),
        )
        for pe, row in monthly.iterrows()
    )
    monthly_table = (
        "<table><thead><tr><th>Periodslut</th><th>EGEN täckning</th><th>EGEN TER</th>"
        "<th>PA täckning</th><th>PA TER</th></tr></thead>"
        f"<tbody>{monthly_rows}</tbody></table>"
    )

    missing_frames = []
    for p in (egen, pa):
        if not p.missing.empty:
            frame = p.missing.copy()
            frame.insert(0, "Portfölj", p.portfolio)
            missing_frames.append(frame)
    if missing_frames:
        all_missing = pd.concat(missing_frames, ignore_index=True)
        missing_rows = "".join(
            "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                row["Portfölj"],
                html.escape(str(row["Display_Name"])),
                html.escape(str(row["ISIN"])),
                int(row["Perioder"]),
                fmt_pct(row["Maxvikt"]),
            )
            for _, row in all_missing.iterrows()
        )
        missing_block = (
            f'<div class="warn"><p><strong>Innehav utan TER ({len(all_missing)} '
            "poster):</strong> förkravet att alla EGEN/PA-innehav har TER håller "
            "<em>inte</em> – följande innehav i fönstret saknar TER (till stor del "
            "fonder som lämnat portföljen; deras metadata finns inte längre hos "
            "källan). Alla viktade TER-tal i avsnittet gäller den täckta vikten.</p>"
            "<table><thead><tr><th>Portfölj</th><th>Instrument</th><th>ISIN</th>"
            "<th>Periodslut</th><th>Maxvikt</th></tr></thead>"
            f"<tbody>{missing_rows}</tbody></table></div>"
        )
    else:
        missing_block = (
            "<p>Samtliga innehav i fönstret har TER – full täckning i alla perioder.</p>"
        )

    # --- 6.2: motvind och dekomponering ----------------------------------------
    gap_egen_tgt = since("PORT_EGEN_REAL") - since("PORT_EGEN_TGT")
    gap_egen_pa = since("PORT_EGEN_REAL") - since("PORT_PA_REAL")
    # Avgiftens mekaniska bidrag till nettogapet: negativ TER-differens (EGEN
    # billigare) ger positivt bidrag till EGEN:s relativa nettoavkastning.
    fee_contrib_tgt = -costs.fee_gap_egen_tgt_cum
    fee_contrib_pa = -costs.fee_gap_egen_pa_cum
    mgmt_tgt = gap_egen_tgt - fee_contrib_tgt
    mgmt_pa = gap_egen_pa - fee_contrib_pa

    cheapest_clause = ""
    if costs.cheapest_broad_global is not None:
        name, cheap_ter = costs.cheapest_broad_global
        cheapest_clause = (
            f"<p><strong>Mot ett billigt indexalternativ:</strong> det billigaste breda "
            f"globala instrumentet i universumet är {html.escape(name)} "
            f"(TER {fmt_pct(cheap_ter, 2)}). Relativt det bär EGEN en strukturell "
            f"avgiftsmotvind på {fmt_pct(egen.ter_tw_renorm - cheap_ter, 2)}/år "
            f"(tidsviktat, täckt vikt) och PA {fmt_pct(pa.ter_tw_renorm - cheap_ter, 2)}/år. "
            f"Det är ett stiliserat räkneexempel på vad avgiftsnivån kostar mot det "
            f"billigaste bytbara alternativet – ingen utsaga om förväntad avkastning. "
            f"Nordnet-referensernas egna avgifter saknas i datan och ingår inte.</p>"
        )

    decomposition = f"""
<p><strong>Principen först:</strong> alla serier är netto (NAV) – TER ligger redan i
avkastningen och läggs inte tillbaka. TER-differenser används i stället för att säga
hur stor del av ett observerat <em>netto</em>-gap som är avgift (kontrollerbar – kan
bytas till billigare) respektive bruttoförvaltning (fondernas utfall före avgift plus
de egna besluten).</p>
<p><strong>EGEN mot sin egen lista (TGT):</strong> tidsviktad TER för EGEN:s faktiska
resa är {fmt_pct(egen.ter_tw_renorm, 2)}/år (täckt vikt) mot {fmt_pct(egen.snapshot_ter.get("TGT", float("nan")), 2)}
för dagens målviktslista – en differens på {fmt_pct(costs.fee_gap_egen_tgt, 2)}/år,
vars mekaniska bidrag till nettogapet över fönstret är {fmt_pp(fee_contrib_tgt, 2)}
(linjärt: differens × {costs.window_years:.2f} år). Av gapet REAL−TGT på
{fmt_pp(gap_egen_tgt, 2)} är alltså {fmt_pp(fee_contrib_tgt, 2)} avgift och
{fmt_pp(mgmt_tgt, 2)} bruttoförvaltning. <strong>Gapet mot den egna listan är i allt
väsentligt förvaltning, inte avgift</strong> – med förbehållen att referensen bär
survivorship-/look-ahead-bias (avsnitt 7.2) och att EGEN:s historiska TER-täckning är
{fmt_pct(egen.coverage_tw)} av vikten.</p>
<p><strong>EGEN mot PA (kärnfrågan):</strong> EGEN:s tidsviktade TER
({fmt_pct(egen.ter_tw_renorm, 2)}) är <em>{"lägre" if costs.fee_gap_egen_pa < 0 else "högre"}</em>
än PA:s ({fmt_pct(pa.ter_tw_renorm, 2)}) – differens {fmt_pct(costs.fee_gap_egen_pa, 2)}/år,
dvs. en strukturell avgifts{"medvind" if fee_contrib_pa > 0 else "motvind"} för EGEN
på {fmt_pp(fee_contrib_pa, 2)} över fönstret. Nettogapet EGEN−PA är
{fmt_pp(gap_egen_pa, 2)} – EGEN ligger {_fore_efter(gap_egen_pa)} PA i det gemensamma
fönstret (avsnitt 7.1). Rensat för avgiftsdifferensen är bruttoförvaltningsgapet
{fmt_pp(mgmt_pa, 2)} – <strong>avgiftsskillnaden förklarar {fmt_pp(fee_contrib_pa, 2)}
av gapet mot PA; resten är förvaltning</strong>, med samma täckningsförbehåll som
ovan.</p>
{cheapest_clause}
"""

    # --- 6.3: courtage -----------------------------------------------------------
    ct = costs.courtage
    ct_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(row["Display_Name"])),
            html.escape(str(row["Category"])),
            fmt_num(row["Courtage_SEK"], 0) + " kr",
            int(row["Txn"]),
        )
        for _, row in ct.by_instrument.iterrows()
    )
    ct_table = (
        "<table><thead><tr><th>Instrument</th><th>Kategori</th>"
        "<th>Courtage (SEK)</th><th>Transaktioner</th></tr></thead>"
        f"<tbody>{ct_rows}</tbody></table>"
    )
    bucket_range = (
        f"{ct.first_bucket.strftime('%Y-%m')} – {ct.last_bucket.strftime('%Y-%m')}"
        if ct.first_bucket is not None
        else "–"
    )
    courtage_text = f"""
<p>Realiserat courtage för EGEN i fönstret: <strong>{fmt_num(ct.total_sek, 0)} kr</strong>
({ct.n_rows} månadsposter, {ct.n_txn} transaktioner, bucketar {bucket_range}). Mot den
dagviktade genomsnittliga portföljvolymen ({fmt_num(ct.avg_mv_sek / 1000, 0)} tkr) över
fönstrets {ct.window_years:.2f} år motsvarar det <strong>{fmt_pct(ct.pct_per_year, 3)}/år</strong>
– försumbart bredvid TER-nivåerna ovan. Courtaget är <em>redan indraget</em> i
REAL-serien (transaktionsbeloppen inkluderar courtage); det synliggörs här och dras
inte av igen. PA har inga courtageposter i fönstret ({costs.pa_courtage_rows} rader) –
fondhandel sker utan courtage, och EGEN:s courtage uppstår först när ETF-handeln
inleds ({ct.first_bucket.strftime("%Y-%m") if ct.first_bucket is not None else "–"}).
Bucketarna är kalendermånader; den sista omfattar transaktioner till och med as-of.</p>
{ct_table}
"""

    flags_html = "".join(f"<li>{html.escape(flag)}</li>" for flag in costs.flags)
    return f"""
<p>Avsnittet kvantifierar den strukturella avgiftsmotvinden (Steg 2b): tidsviktad
löpande avgift (TER) ur <code>Dim_Instrument</code> × månadsvikterna i
<code>Fact_Portfolio_Alloc_Monthly</code>, plus realiserat courtage ur
<code>Fact_Portfolio_Courtage</code>. Vikterna vid varje periodslut representerar den
gångna perioden och vägs med kalenderdagar; fönster och as-of är rapportens gemensamma
({costs.inception.date()} – {costs.as_of.date()}).</p>
{missing_block}
<h3>6.1 Löpande avgift (TER)</h3>
<img src="data:image/png;base64,{ter_chart}" alt="Viktad TER per periodslut">
{tw_table}
<p>Dagens listor (snapshot, full TER-täckning i samtliga):</p>
{snap_table}
<p>Underlaget per periodslut – täckningen är svag i fönstrets början (fonder som
lämnat portföljen saknar TER-uppgift) och fullständig mot slutet:</p>
{monthly_table}
<h3>6.2 Avgiftsmotvind och dekomponering av gapen</h3>
{decomposition}
<h3>6.3 Courtage – omsättningens direkta kostnad</h3>
{courtage_text}
<h3>6.4 Poster som inte fångas</h3>
<div class="warn"><ul>{flags_html}</ul></div>
"""


def _costs_verification_section(costs_verification: pd.DataFrame) -> str:
    rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{:.2e}</td><td>{}</td></tr>".format(
            html.escape(str(row["Kontroll"])),
            fmt_num(row["Visat"], 6),
            fmt_num(row["Omräknat"], 6),
            row["Diff"],
            "OK" if row["OK"] else "AVVIKER",
        )
        for _, row in costs_verification.iterrows()
    )
    return f"""
<h4>Avgiftsavsnittets kontrollvärden</h4>
<p>Den tidsviktade TER:n räknas om via en oberoende väg (viktmatris × TER-vektor,
vektoriserat) och jämförs mot rapportens gruppvisa beräkning; courtagesumman
korssummeras mot facten och instrumenttabellen; snapshot-täckningen ska vara exakt
1,0 för samtliga listor.</p>
<table><thead><tr><th>Kontroll</th><th>Visat</th><th>Omräknat</th><th>|Diff|</th>
<th>Status</th></tr></thead><tbody>{rows}</tbody></table>
"""


def _interpretation_section(
    data: BIData,
    kpi: pd.DataFrame,
    inception: pd.Timestamp,
    as_of: pd.Timestamp,
    costs: CostsResult,
) -> str:
    pa = _facts(data, "PA", kpi, inception, as_of)
    egen = _facts(data, "EGEN", kpi, inception, as_of)

    def gap_text(f: dict, portfolio: str) -> str:
        gap_cur = f["ret_real"] - f["ret_cur"]
        gap_bal = f["ret_real"] - f["ret_bal"]
        one_year_clause = ""
        if f["has_1y"]:
            gap_bal_1y = f["ret_real_1y"] - f["ret_bal_1y"]
            one_year_clause = f" senaste året är avståndet {fmt_pp(gap_bal_1y)}."
        return (
            f"<p><strong>{portfolio}:</strong> REAL står i {fmt_idx(f['idx_real'])} "
            f"({fmt_pct(f['ret_real'])} sedan start, CAGR {fmt_pct(f['cagr_real'])}), "
            f"mot CUR {fmt_idx(f['idx_cur'])} och TGT {fmt_idx(f['idx_tgt'])}. "
            f"Gapet REAL−CUR är {fmt_pp(gap_cur)} i totalavkastning. "
            f"Mot Nordnet Balanserad ({fmt_pct(f['ret_bal'])}) ligger REAL "
            f"{fmt_pp(gap_bal)}, dvs. {_fore_efter(gap_bal)} referensen sedan start;"
            f"{one_year_clause} "
            f"Riskjusterat: Sharpe {fmt_num(f['sharpe_real'])} för REAL mot "
            f"{fmt_num(f['sharpe_bal'])} för Nordnet Balanserad.</p>"
        )

    gap_egen_pa = egen["ret_real"] - pa["ret_real"]
    egen_vs_pa = (
        f"<p><strong>EGEN mot PA (kärnfrågan):</strong> över det gemensamma fönstret "
        f"({inception.date()} – {as_of.date()}) avkastade EGEN {fmt_pct(egen['ret_real'])} "
        f"mot PA:s {fmt_pct(pa['ret_real'])} – EGEN ligger {fmt_pp(gap_egen_pa)} "
        f"{_fore_efter(gap_egen_pa)} referensportföljen. Riskjusterat är Sharpe "
        f"{fmt_num(egen['sharpe_real'])} (EGEN) mot {fmt_num(pa['sharpe_real'])} (PA). "
        f"PA är den portfölj EGEN ska slå; båda mäts från EGEN:s inception så att "
        f"jämförelsen sker över EGEN:s livslängd, inte PA:s längre historik.</p>"
    )

    egen_worst = egen["categories"].iloc[-1]
    egen_best = egen["categories"].iloc[0]
    pa_best = pa["categories"].iloc[0]

    egen_costs = costs.ter["EGEN"]
    fee_contrib_pa = -costs.fee_gap_egen_pa_cum
    return f"""
<h3>7.1 Vad siffrorna visar</h3>
{egen_vs_pa}
{gap_text(pa, "PA")}
{gap_text(egen, "EGEN")}
<p>Kategorimässigt (deskriptivt): i EGEN drog
<strong>{html.escape(egen_best['Kategori'])}</strong> ({fmt_pct(egen_best['Ret_Since'])}) upp
medan <strong>{html.escape(egen_worst['Kategori'])}</strong>
({fmt_pct(egen_worst['Ret_Since'])}, max drawdown {fmt_pct(egen_worst['MaxDD_Since'])}) drog ned.
I PA var <strong>{html.escape(pa_best['Kategori'])}</strong> ({fmt_pct(pa_best['Ret_Since'])})
starkast.</p>

<h3>7.2 Hur REAL-vs-CUR/TGT-gapet får – och inte får – tolkas</h3>
<p>CUR och TGT är <em>konstantviktade (dagligen rebalanserade) portföljer av den
nuvarande fondlistan, bakåtprojicerade</em> över hela perioden. Listan är vald med facit i hand: fonder som
åkt ut ur portföljen under resan ingår inte, och fonder som köpts in sent får i
CUR/TGT tillgodoräkna sig hela periodens uppgång. Det ger survivorship- och
look-ahead-bias i referensens favör. <strong>Gapet REAL−CUR/TGT är därför inte ett
skicklighetsmått</strong> – det är en partisk jämförelse där referensen har systematisk
medvind. Det gäller särskilt EGEN, där gapet ({fmt_pp(egen['ret_real'] - egen['ret_cur'])})
till stor del kan bero på att dagens lista innehåller periodens vinnare, inte på att
de löpande besluten kostat motsvarande belopp.</p>
<p><strong>Vad datan stödjer i dag:</strong> (1) Den externa jämförelsen REAL mot
Nordnet-referenserna är rättvis i tiden – samma fönster, samma bas, daglig TWR, priser
valutakonverterade till SEK uppströms. Där ligger båda portföljerna efter Nordnet
Balanserad sedan start, både absolut och riskjusterat. (2) För PA är REAL-vs-CUR-gapet
litet ({fmt_pp(pa['ret_real'] - pa['ret_cur'])}) med likvärdig Sharpe
({fmt_num(pa['sharpe_real'])} mot {fmt_num(pa['sharpe_cur'])}) och lägre volatilitet
({fmt_pct(pa['vol_real'])} mot {fmt_pct(pa['vol_cur'])}) – den faktiska förvaltningen har
inte uppenbart förstört värde relativt sin egen nuvarande lista, med reservationen att
även den jämförelsen bär samma bias. (3) För EGEN är den realiserade resan kraftigt
svagare än backprojektionen av sin egen lista – ett tydligt <em>underlag för vidare
analys</em>, inte en dom.</p>
<p><strong>Vad som nu besvaras respektive återstår:</strong> Brinson-attributionen,
rebalansering-mot-slump-testet och koncentrationsanalysen finns i avsnitt 5 (Steg 2a),
och avgiftsmotvinden kvantifieras i avsnitt 6 (Steg 2b). Avgiftsspåret skärper
selektionsläsningen: EGEN:s tidsviktade TER ({fmt_pct(egen_costs.ter_tw_renorm, 2)},
på täckt vikt) är {"lägre" if costs.fee_gap_egen_pa < 0 else "högre"} än PA:s – en
strukturell avgifts{"medvind" if fee_contrib_pa > 0 else "motvind"} på
{fmt_pp(fee_contrib_pa, 2)} mot PA över fönstret. Gapet mot PA är alltså inte
avgiftsdrivet; det som återstår efter avgiftsjustering är förvaltning/selektion, och
survivorship-förbehållet ovan kvarstår. Det som
återstår är TER för de innehav som lämnat portföljen (täckningsluckan i avsnitt 6)
samt spread/FX-växling, som inte fångas av datan.</p>

<h3>7.3 Pilotens metafråga och rekommendation</h3>
<p>Ger den här rapporten beslutsvärde utöver Power BI? Bedömning: <strong>ja, men på
tolknings- och verifieringslagret snarare än på siffrorna</strong>. Kurvorna och
KPI-tabellerna finns redan i Power BI. Det rapporten tillför är (1) ett gemensamt
analysfönster ankrat vid EGEN:s inception så att EGEN mäts rättvist mot PA, (2) en
oberoende omräkning av samtliga KPI:er över fönstret med redovisad tolerans, (3) explicit
bias-hantering – Power BI visar gapet men förklarar inte varför det inte får läsas som
skicklighet, och (4) ett reproducerbart, versionerat underlag som kan byggas om vid
varje datauppdatering och as-of-datum.</p>
<p><strong>Rekommendation: fortsätt, med justerat scope.</strong> Med Steg 2a-vikterna
på plats attribuerar avsnitt 5 gapet mekaniskt (allokering/selektion/koncentration),
och med TER + courtage (Steg 2b) skiljer avsnitt 6 avgift från förvaltning. Den
kvarvarande dataluckan med störst beslutsvärde är TER för utgångna innehav –
täckningen bakåt i tiden är {fmt_pct(egen_costs.coverage_tw)} av EGEN:s vikt, så den
historiska avgiftsbilden vilar på den täckta delen. Behåll Power BI för löpande
överblick; låt det här spåret äga fördjupning, attribution och verifiering.</p>
"""


def _attribution_portfolio_section(attr: PortfolioAttribution) -> str:
    """Sektion 5 för en portfölj: dekomponering, slumptest, koncentration."""
    effects = attr.effects_by_category.copy()
    effects["Summa"] = effects.sum(axis=1)
    body = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(category)),
            fmt_pp(row["Allokering"], 2),
            fmt_pp(row["Selektion"], 2),
            fmt_pp(row["Interaktion"], 2),
            fmt_pp(row["Summa"], 2),
        )
        for category, row in effects.iterrows()
    )
    totals_row = (
        f"<tr class=\"real-row\"><td>Summa</td><td>{fmt_pp(attr.allocation_total, 2)}</td>"
        f"<td>{fmt_pp(attr.selection_total, 2)}</td>"
        f"<td>{fmt_pp(attr.interaction_total, 2)}</td>"
        f"<td>{fmt_pp(attr.allocation_total + attr.selection_total + attr.interaction_total, 2)}</td></tr>"
    )
    effects_table = (
        "<table><thead><tr><th>Kategori</th><th>Allokering/timing</th><th>Selektion</th>"
        f"<th>Interaktion</th><th>Summa</th></tr></thead><tbody>{body}{totals_row}</tbody></table>"
    )

    reconciliation = (
        f"<p>Aktiv avkastning REAL−TGT i attributionsfönstret "
        f"({attr.window_start.date()} – {attr.window_end.date()}, {attr.n_months} månader): "
        f"<strong>{fmt_pp(attr.active_window, 2)}</strong> "
        f"(REAL {fmt_pct(attr.r_real_window)} mot TGT {fmt_pct(attr.r_ref_window)}). "
        f"Komponenter: allokering/timing {fmt_pp(attr.allocation_total, 2)}, "
        f"selektion {fmt_pp(attr.selection_total, 2)}, "
        f"interaktion {fmt_pp(attr.interaction_total, 2)}, "
        f"residual REAL (intra-månadsflöden) {fmt_pp(attr.residual_real, 2)}, "
        f"residual TGT (daglig rebalansering) {fmt_pp(attr.residual_ref, 2)}. "
        f"Kontrollsumma mot aktiv avkastning: residual {attr.decomposition_residual:.2e}. "
        f"Sedan seriestart är den aktiva avkastningen {fmt_pp(attr.active_since_start, 2)}; "
        f"skillnaden mot fönstret, {fmt_pp(attr.pre_window_effect, 2)}, uppstod "
        f"<em>före</em> första månadsvikten (perioden innan portföljen var fullt "
        f"investerad, då bakåtprojicerade TGT redan var det).</p>"
    )

    perm_conclusion = (
        "statistiskt skiljbar från slump"
        if attr.perm_p_two_sided < 0.05
        else "inte statistiskt skiljbar från slump"
    )
    perm = (
        f"<p><strong>Rebalansering mot slump:</strong> den aritmetiska allokerings-/"
        f"timingeffekten är {fmt_pp(attr.perm_statistic, 2)}. Under nollhypotesen att "
        f"viktbanans <em>tidsordning</em> är slumpmässig (permutation av månadsvikternas "
        f"ordning, N&nbsp;=&nbsp;{attr.perm_n}, fast seed) blir effekten i medel "
        f"{fmt_pp(attr.perm_null_mean, 2)} med standardavvikelse "
        f"{fmt_pp(attr.perm_null_std, 2)}. Den faktiska banan ligger på percentil "
        f"{fmt_num(attr.perm_percentile * 100.0, 1)} och tvåsidigt p-värde "
        f"{fmt_num(attr.perm_p_two_sided, 3)} – <strong>{perm_conclusion}</strong>. "
        f"Testet isolerar timingen: nivån på snedvridningarna hålls konstant, bara "
        f"ordningen slumpas.</p>"
    )

    top = attr.fund_contributions.head(TOP_N_FUNDS)
    other = attr.fund_contributions.iloc[TOP_N_FUNDS:]
    fund_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(row["Fond"])),
            html.escape(str(row["Kategori"])),
            fmt_pp(row["C_real"], 2),
            fmt_pp(row["C_ref"], 2),
            fmt_pp(row["Gap"], 2),
        )
        for _, row in top.iterrows()
    )
    if not other.empty:
        fund_rows += (
            f"<tr><td>Övriga {len(other)} fonder</td><td>–</td>"
            f"<td>{fmt_pp(other['C_real'].sum(), 2)}</td>"
            f"<td>{fmt_pp(other['C_ref'].sum(), 2)}</td>"
            f"<td>{fmt_pp(other['Gap'].sum(), 2)}</td></tr>"
        )
    fund_rows += (
        f"<tr><td>Residualer (flöden/rebalansering)</td><td>–</td>"
        f"<td>{fmt_pp(attr.fund_residual_real, 2)}</td>"
        f"<td>{fmt_pp(attr.fund_residual_ref, 2)}</td>"
        f"<td>{fmt_pp(attr.fund_residual_real - attr.fund_residual_ref, 2)}</td></tr>"
    )
    fund_table = (
        "<table><thead><tr><th>Fond</th><th>Kategori</th><th>Bidrag REAL</th>"
        "<th>Bidrag TGT</th><th>Gapbidrag</th></tr></thead>"
        f"<tbody>{fund_rows}</tbody></table>"
    )
    concentration = (
        f"<p><strong>Koncentration:</strong> de tre största gapbidragen (absolutbelopp) "
        f"står för {fmt_pct(attr.gap_top3_share)} av summan av alla gapbidrags "
        f"absolutbelopp. Bidragen är Carino-länkade så att de summerar till respektive "
        f"series totalavkastning i fönstret; REAL-bidragen bygger på månadsvikter × "
        f"fondavkastning och intra-månadsflöden hamnar i residualraden.</p>"
    )

    effects_png = charts.attribution_chart(
        attr.effects_by_category,
        f"{attr.portfolio}: Brinson-Fachler mot TGT, länkade effekter per kategori",
    )
    gap_png = charts.signed_barh_chart(
        top.set_index("Fond")["Gap"],
        f"{attr.portfolio}: största fondbidrag till gapet REAL−TGT",
        "Gapbidrag (procentenheter)",
    )

    components = {
        "allokering/timing": attr.allocation_total,
        "selektion (inom kategori, mot dagens lista)": attr.selection_total,
        "interaktion": attr.interaction_total,
    }
    dominant_name = max(components, key=lambda name: abs(components[name]))
    concentration_verdict = (
        "buret av ett fåtal positioner"
        if attr.gap_top3_share >= 0.5
        else "brett fördelat över listan, inte buret av enstaka positioner"
    )
    survivorship_note = (
        " Observera att selektionstermen är den komponent där survivorship-biasen "
        "slår hårdast: referensens inom-kategori-mix är dagens behållna fonder."
        if dominant_name.startswith("selektion")
        else ""
    )
    reading = (
        f"<p><strong>Läsning:</strong> största komponent i fönstret är "
        f"<strong>{dominant_name}</strong> ({fmt_pp(components[dominant_name], 2)}). "
        f"Viktbanans tidsordning är {perm_conclusion} (p = "
        f"{fmt_num(attr.perm_p_two_sided, 3)}); nollfördelningens medelvärde "
        f"({fmt_pp(attr.perm_null_mean, 2)}) visar vad snedvridningarnas <em>struktur</em> "
        f"kostar oavsett ordning, och avståndet till den faktiska effekten "
        f"({fmt_pp(attr.perm_statistic - attr.perm_null_mean, 2)}) är timingens bidrag "
        f"utöver strukturen. Gapet är {concentration_verdict} "
        f"(topp-3-andel {fmt_pct(attr.gap_top3_share)}).{survivorship_note}</p>"
    )

    flags_html = "".join(f"<li>{html.escape(flag)}</li>" for flag in attr.flags)
    return (
        f"<h3>{attr.portfolio}</h3>"
        f"{reconciliation}"
        f'<img src="data:image/png;base64,{effects_png}" alt="Attribution {attr.portfolio}">'
        f"{effects_table}"
        f"{perm}"
        f"{concentration}"
        f"{reading}"
        f'<img src="data:image/png;base64,{gap_png}" alt="Gapbidrag {attr.portfolio}">'
        f"{fund_table}"
        f'<div class="warn"><ul>{flags_html}</ul></div>'
    )


def _attribution_section(attributions: dict[str, PortfolioAttribution] | None) -> str:
    if not attributions:
        return (
            '<div class="warn"><p>Attributionen kunde inte beräknas: prismatrisen '
            "(data/cache_prices.parquet) saknas. Kör upstream-pipelinen så att cachen "
            "skapas, och bygg om rapporten.</p></div>"
        )
    method = """
<p><strong>Metod och referensval.</strong> Referensportfölj är <strong>TGT</strong>
(målvikterna, kolumn AndelP): det är den uttalade policyn och därmed den korrekta
Brinson-referensen – aktiv avkastning mäter då avvikelser från den egna planen. CUR
är dagens faktiska mix bakåtprojicerad (en driftad ögonblicksbild, ingen policy) och
används inte som referens. Dekomponeringen är Brinson-Fachler per kalendermånad på
kategorinivå: <em>allokering/timing</em> = (REAL-vikt − TGT-vikt) × (TGT-kategoriavkastning
− TGT-total), <em>selektion</em> = TGT-vikt × (REAL-kategoriavkastning −
TGT-kategoriavkastning), <em>interaktion</em> = viktavvikelse × avkastningsavvikelse.
Månadseffekterna länkas med Carino-metoden så att komponenterna summerar exakt till
fönstrets aktiva avkastning; kontrollsumman redovisas per portfölj.</p>
<p><strong>Datakällor.</strong> REAL-vikterna kommer ur
<code>Fact_Portfolio_Alloc_Monthly</code> (Steg 2a) och REAL-kategoriavkastningarna är
ankrade i REAL_CAT-seriernas indexnivåer – inga nya REAL-beräkningar görs. TGT:s
kategoriavkastningar finns inte i BI-filen; de replikeras ur samma prismatris som
pipelinen använder (<code>data/cache_prices.parquet</code>, forward-fylld, SEK-konverterad
med samma FX-logik). Replikeringen verifieras mot TGT-seriens IDX i BI-filen innan den
används – maximal avvikelse redovisas i bilagan.</p>
<p><strong>Vad selektionstermen är – och inte är.</strong> Selektion mäts här
<em>inom samma fonduniversum</em>: REAL:s faktiska inom-kategori-utfall mot TGT:s
konstantviktade mix av dagens lista. Selektion mot <em>externa marknadsindex</em> per
kategori kräver en entydig indexmappning per kategori; BI-filen har kategoriindex för
tre av kategorierna (ACWI, EEM, AGG – och två kandidater för Breda fonder) men saknar
index för Småbolag &amp; Faktorfonder och Tematiska &amp; Sektorfonder. Den analysen
räknas därför inte alls här, i stället för att räknas orent.</p>
"""
    sections = "".join(
        _attribution_portfolio_section(attributions[p])
        for p in PORTFOLIOS
        if p in attributions
    )
    return method + sections


def _attribution_verification_section(
    attributions: dict[str, PortfolioAttribution] | None,
) -> str:
    if not attributions:
        return ""
    rows = "".join(
        f"<tr><td>{attr.portfolio}</td>"
        f"<td>{attr.replication_max_diff:.2e}</td>"
        f"<td>{attr.decomposition_residual:.2e}</td>"
        f"<td>{fmt_pp(attr.max_abs_e_real, 2)}</td>"
        f"<td>{fmt_pp(attr.max_abs_e_ref, 2)}</td>"
        f"<td>{attr.zero_weight_cells}</td></tr>"
        for attr in attributions.values()
    )
    return f"""
<h4>Attributionens kontrollvärden</h4>
<p>Replikering: TGT-serien återskapas ur priscachen och jämförs mot BI-seriens IDX
(maskinexakt förväntas). Kontrollsumman är komponenternas summa minus aktiv avkastning
efter Carino-länkning (ska vara maskineps). Identitetsresidualerna e är största
månatliga avvikelse mellan seriens totalavkastning och viktade kategoriavkastningar –
för REAL fångar den intra-månadsflöden, för TGT den dagliga rebalanseringen; båda ingår
som redovisade komponenter i dekomponeringen, inte som fel.</p>
<table><thead><tr><th>Portfölj</th><th>Replikering max|ΔIDX|</th>
<th>Kontrollsumma</th><th>max |e_REAL|/mån</th><th>max |e_TGT|/mån</th>
<th>Kategorimånader utan REAL-innehav</th></tr></thead>
<tbody>{rows}</tbody></table>
"""


def _verification_section(result: VerificationResult, contract_failures: list[str]) -> str:
    anchor_rows = "".join(
        f"<tr><td>{row['Series_ID']}</td><td>{fmt_idx(row['Förväntat'])}</td>"
        f"<td>{fmt_idx(row['Observerat'])}</td><td>{'OK' if row['OK'] else 'AVVIKER'}</td></tr>"
        for _, row in result.anchor_rows.iterrows()
    )
    rebase_all_ok = bool(result.rebase_rows["OK"].all()) if not result.rebase_rows.empty else True
    rebase_status = (
        f"samtliga {len(result.rebase_rows)} serier står på exakt bas 100 vid startdatumet"
        if rebase_all_ok
        else f"<strong>{int((~result.rebase_rows['OK']).sum())} serier avviker från bas 100</strong>"
    )
    worst = result.kpi_comparison.nlargest(5, "Diff") if not result.kpi_comparison.empty else result.kpi_comparison
    worst_rows = "".join(
        f"<tr><td>{row['Series_ID']}</td><td>{row['Period']}</td><td>{row['KPI']}</td>"
        f"<td>{row['Diff']:.2e}</td></tr>"
        for _, row in worst.iterrows()
    )
    contract = (
        "<p>Datakontrakt: inga NaN i faktatabellerna, samtliga viktsnapshot summerar till 1,0.</p>"
        if not contract_failures
        else "<p><strong>Datakontraktsavvikelser:</strong></p><ul>"
        + "".join(f"<li>{html.escape(f)}</li>" for f in contract_failures)
        + "</ul>"
    )
    status = (
        "samtliga inom tolerans"
        if result.n_deviations == 0
        else f"<strong>{result.n_deviations} avvikelser utanför tolerans</strong>"
    )
    return f"""
<p>KPI:erna räknades om oberoende över det gemensamma fönstret ur
<code>Fact_Series_Daily</code> (samma definitioner som pipelinen: rf 3&nbsp;% årligen,
252 handelsdagar, CAGR på kalenderdagar/365,25) och jämfördes mot de tal rapporten
visar: {result.n_compared} värden jämförda, {status}. Största absoluta avvikelse:
{result.max_abs_diff:.2e}.</p>
<p>Rebaseringskontroll: {rebase_status} (största avvikelse {result.max_rebase_diff:.2e}
indexpunkter).</p>
{contract}
<h4>Ankarkontroll REAL-nivåer (hela källserien)</h4>
<table><thead><tr><th>Serie</th><th>Förväntat</th><th>Observerat</th><th>Status</th></tr></thead>
<tbody>{anchor_rows}</tbody></table>
<h4>Största observerade differenser (topp 5)</h4>
<table><thead><tr><th>Serie</th><th>Period</th><th>KPI</th><th>|Diff|</th></tr></thead>
<tbody>{worst_rows}</tbody></table>
"""


# --- huvudbyggare -------------------------------------------------------------

_CSS = """
body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
       max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
h1 { font-size: 1.6rem; border-bottom: 2px solid #1f4e9c; padding-bottom: .4rem; }
h2 { font-size: 1.25rem; margin-top: 2.2rem; color: #1f4e9c; }
h3 { font-size: 1.05rem; margin-top: 1.6rem; }
img { max-width: 100%; height: auto; display: block; margin: .8rem 0; }
table { border-collapse: collapse; width: 100%; font-size: .82rem; margin: .8rem 0; }
th, td { border: 1px solid #ccc; padding: .35rem .5rem; text-align: right; }
th:first-child, td:first-child { text-align: left; }
th .sub { font-weight: 400; font-size: .72rem; color: #555; }
thead { background: #eef2f8; }
tr.real-row { background: #e8eefb; font-weight: 600; }
.meta { background: #f6f6f6; border-left: 4px solid #1f4e9c; padding: .8rem 1rem;
        font-size: .85rem; }
.warn { background: #fdf3e7; border-left: 4px solid #e07b39; padding: .8rem 1rem;
        font-size: .9rem; }
"""


def build_html(
    data: BIData,
    verification: VerificationResult,
    contract_failures: list[str],
    inception: pd.Timestamp,
    as_of: pd.Timestamp,
    horizons: list[Horizon],
    kpi: pd.DataFrame,
    attributions: dict[str, PortfolioAttribution] | None = None,
    costs: CostsResult | None = None,
    costs_verification: pd.DataFrame | None = None,
) -> str:
    """Sätt ihop hela rapporten till en självbärande HTML-sträng."""
    if costs is None:
        raise ValueError("Kostnadsanalysen (costs) krävs för att bygga rapporten.")
    start_date = inception.date()
    end_date = as_of.date()
    window_years = (as_of - inception).days / 365.25

    headline = _headline_section(data, inception, as_of)
    index_sections = "".join(_portfolio_index_section(data, p, inception, as_of) for p in PORTFOLIOS)
    category_sections = "".join(_category_section(data, p, inception, as_of, kpi) for p in PORTFOLIOS)
    allocation_sections = "".join(_allocation_section(data, p) for p in PORTFOLIOS)

    return f"""<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="utf-8">
<title>Fond-rapport – {end_date}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Fond-rapport – slår EGEN referensportföljen PA?</h1>
<div class="meta">
<p><strong>Källa:</strong> portfolio_bi_data.xlsx (läst read-only) ·
<strong>Analysfönster:</strong> {start_date} – {end_date} ({window_years:.2f} år) ·
<strong>As-of:</strong> {end_date} ·
<strong>Byggd av:</strong> tools/fond_rapport (deterministisk beräkning i Python).</p>
<p><strong>Ram:</strong> EGEN är den verkliga portföljen; PA är referensportföljen
EGEN ska slå. Fönstret startar vid EGEN:s inception ({start_date} – EGEN:s första
värderade REAL-position), härledd ur datan. Alla serier – PA/EGEN REAL/CUR/TGT samt
externa benchmarks – rebaseras till bas 100 vid detta datum och skärs till fönstret,
så att jämförelserna sker över EGEN:s livslängd, inte PA:s längre historik.</p>
<p><strong>Metod:</strong> Alla serier är dagliga tidsviktade avkastningar (TWR),
index bas 100, priser valutakonverterade till SEK uppströms. KPI:er enligt
pipelinens definitioner (rf 3&nbsp;%, 252 handelsdagar), räknade över fönstret. Alla
tal i rapporten är beräknade ur källfilen – inget är uppskattat.</p>
</div>

<h2>1. Index: EGEN mot PA och referenser</h2>
<p>EGEN (blå) mäts mot PA (röd) – referensportföljen som ska slås – samt externa
blandfondsreferenser, allt rebaserat till 100 vid EGEN:s inception. CUR och TGT är
konstantviktade referenser, dagligen ombalanserade till fasta vikter (nuvarande
fondlista resp. målvikter), bakåtprojicerade – se förbehållen i avsnitt 7.2 innan
gapet tolkas.</p>
{headline}
{index_sections}

<h2>2. Nyckeltal per serie</h2>
<h3>Avkastning per horisont</h3>
<p>Kumulativ avkastning för horisonter under ett år, CAGR för ett år och längre;
datumintervallen står i kolumnrubrikerna. Alla horisonter räknas relativt as-of
({end_date}).</p>
{_horizon_table(kpi, horizons)}
<h3>Fullständiga nyckeltal – sedan start ({start_date} – {end_date})</h3>
{_kpi_table(kpi, "Since_Start")}
{_one_year_kpi_block(kpi, horizons)}

<h2>3. Kategorier – var fanns avkastningen?</h2>
<div class="warn"><p>Kategoriserierna är tidsviktade delportföljer (REAL_CAT). De visar
<em>var</em> avkastningen fanns, inte hur mycket varje kategori <em>bidrog</em> till
portföljens totala avkastning – bidragsanalys görs i attributionen (avsnitt 5). Läs
tabellerna deskriptivt.</p></div>
{category_sections}

<h2>4. Aktuell allokering (snapshot)</h2>
<p>Vikterna avser <em>ett</em> datum; den historiska viktbanan
(Fact_Portfolio_Alloc_Monthly, Steg 2a) används i attributionen i avsnitt 5.</p>
{allocation_sections}

<h2>5. Attribution – varifrån kommer gapet mot den egna listan?</h2>
{_attribution_section(attributions)}

<h2>6. Avgifter och kostnader – den strukturella motvinden (Steg 2b)</h2>
{_costs_section(costs, kpi)}

<h2>7. Tolkning och metodikbedömning</h2>
{_interpretation_section(data, kpi, inception, as_of, costs)}

<h2>Bilaga: Självverifiering</h2>
{_verification_section(verification, contract_failures)}
{_attribution_verification_section(attributions)}
{_costs_verification_section(costs_verification) if costs_verification is not None else ""}
</body>
</html>
"""


def _one_year_kpi_block(kpi: pd.DataFrame, horizons: list[Horizon]) -> str:
    """Fullständig KPI-tabell för 1Y om horisonten är tillgänglig, annars en not."""
    one_year = next((h for h in horizons if h.key == "1Y"), None)
    if one_year is None or not one_year.available:
        note = one_year.note if one_year else "1Y ej definierad."
        return f'<h3>Senaste året (1Y)</h3><div class="warn"><p>{html.escape(note)}</p></div>'
    return f"<h3>Senaste året (1Y: {one_year.date_range()})</h3>{_kpi_table(kpi, '1Y')}"
