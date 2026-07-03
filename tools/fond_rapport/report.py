"""HTML-bygge för fond-rapporten (Steg 1-pilot).

All text med siffror i rapporten formateras ur beräknade värden – inga tal är
hårdkodade i prosan. Tolkningssektionen innehåller fasta resonemang (bias,
Steg 2-avgränsningar, rekommendation) vars sifferunderlag injiceras.
"""

from __future__ import annotations

import html

import pandas as pd

from . import charts
from .data import BIData, series_index
from .verify import VerificationResult

PORTFOLIOS = ["PA", "EGEN"]

SERIES_LABELS = {
    "PORT_PA_REAL": "PA – Verklig portfölj (REAL)",
    "PORT_PA_CUR": "PA – Nuvarande fondlista, buy &amp; hold (CUR)",
    "PORT_PA_TGT": "PA – Målvikter, buy &amp; hold (TGT)",
    "PORT_EGEN_REAL": "EGEN – Verklig portfölj (REAL)",
    "PORT_EGEN_CUR": "EGEN – Nuvarande fondlista, buy &amp; hold (CUR)",
    "PORT_EGEN_TGT": "EGEN – Målvikter, buy &amp; hold (TGT)",
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
    return f"{value * 100.0:.{decimals}f}".replace(".", ",") + " %"


def fmt_num(value: float, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def fmt_idx(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def fmt_pp(value: float, decimals: int = 1) -> str:
    """Skillnad i procentenheter, med tecken."""
    return f"{value * 100.0:+.{decimals}f}".replace(".", ",") + " p.e."


def _fore_efter(diff: float) -> str:
    return "före" if diff > 0 else "efter"


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


def _category_series(data: BIData, portfolio: str) -> list[tuple[str, str]]:
    """[(Series_ID, kategorinamn)] för portföljens REAL_CAT-serier."""
    dim = data.dim_series
    mask = (
        (dim["Portfolio_Key"] == portfolio)
        & (dim["Is_Category_Series"] == True)  # noqa: E712 – kolumnen är bool
    )
    return [(row["Series_ID"], row["Category"]) for _, row in dim[mask].iterrows()]


def _category_table(data: BIData, portfolio: str) -> tuple[str, pd.DataFrame]:
    kpi = data.fact_kpi.set_index(["Series_ID", "Period"])
    rows = []
    for series_id, category in _category_series(data, portfolio):
        since = kpi.loc[(series_id, "Since_Start")]
        one_year = kpi.loc[(series_id, "1Y")]
        rows.append(
            {
                "Kategori": category,
                "Ret_Since": float(since["Return_Total"]),
                "Ret_1Y": float(one_year["Return_Total"]),
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


def _relative_series(data: BIData, portfolio: str) -> list[tuple[str, pd.Series, str]]:
    real = series_index(data, f"PORT_{portfolio}_REAL")
    out = []
    for other_id, label, style in (
        (f"PORT_{portfolio}_CUR", "REAL / CUR", "CUR"),
        (f"PORT_{portfolio}_TGT", "REAL / TGT", "TGT"),
        ("BM_BM_NORDNET_BALANSERAD", "REAL / Nordnet Balanserad", "BM1"),
    ):
        other = series_index(data, other_id)
        joined = pd.concat([real, other], axis=1, join="inner", keys=["real", "other"])
        out.append((label, joined["real"] / joined["other"] * 100.0, style))
    return out


def _facts(data: BIData, portfolio: str) -> dict:
    """Beräknade nyckelvärden som tolkningssektionen bygger på."""
    kpi = data.fact_kpi.set_index(["Series_ID", "Period"])

    def since(series_id: str, column: str) -> float:
        return float(kpi.loc[(series_id, "Since_Start"), column])

    def one_year(series_id: str, column: str) -> float:
        return float(kpi.loc[(series_id, "1Y"), column])

    real, cur, tgt = (f"PORT_{portfolio}_{v}" for v in ("REAL", "CUR", "TGT"))
    bal, off = "BM_BM_NORDNET_BALANSERAD", "BM_BM_NORDNET_OFFENSIV"

    _, cat_frame = _category_table(data, portfolio)
    return {
        "idx_real": float(series_index(data, real).iloc[-1]),
        "idx_cur": float(series_index(data, cur).iloc[-1]),
        "idx_tgt": float(series_index(data, tgt).iloc[-1]),
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
        "categories": cat_frame,
    }


def _portfolio_index_section(data: BIData, portfolio: str) -> str:
    main = [
        (SERIES_LABELS[f"PORT_{portfolio}_REAL"], series_index(data, f"PORT_{portfolio}_REAL"), "REAL"),
        (SERIES_LABELS[f"PORT_{portfolio}_CUR"], series_index(data, f"PORT_{portfolio}_CUR"), "CUR"),
        (SERIES_LABELS[f"PORT_{portfolio}_TGT"], series_index(data, f"PORT_{portfolio}_TGT"), "TGT"),
        ("Nordnet Balanserad", series_index(data, "BM_BM_NORDNET_BALANSERAD"), "BM1"),
        ("Nordnet Offensiv", series_index(data, "BM_BM_NORDNET_OFFENSIV"), "BM2"),
    ]
    idx_png = charts.line_chart(main, f"{portfolio}: indexutveckling (bas 100)", "Index", baseline=100.0)
    rel_png = charts.line_chart(
        _relative_series(data, portfolio),
        f"{portfolio}: relativ utveckling – REAL mot referenser (100 = lika)",
        "Kvot × 100",
        baseline=100.0,
    )
    return (
        f"<h3>{portfolio}</h3>"
        f'<img src="data:image/png;base64,{idx_png}" alt="Index {portfolio}">'
        f'<img src="data:image/png;base64,{rel_png}" alt="Relativ utveckling {portfolio}">'
    )


def _category_section(data: BIData, portfolio: str) -> str:
    cat_series = [
        (category, series_index(data, series_id))
        for series_id, category in _category_series(data, portfolio)
    ]
    png = charts.category_chart(cat_series, f"{portfolio}: kategoriserier (REAL, bas 100)")
    table, frame = _category_table(data, portfolio)
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


def _interpretation_section(data: BIData) -> str:
    pa = _facts(data, "PA")
    egen = _facts(data, "EGEN")

    def gap_text(f: dict, portfolio: str) -> str:
        gap_cur = f["ret_real"] - f["ret_cur"]
        gap_bal = f["ret_real"] - f["ret_bal"]
        gap_bal_1y = f["ret_real_1y"] - f["ret_bal_1y"]
        return (
            f"<p><strong>{portfolio}:</strong> REAL står i {fmt_idx(f['idx_real'])} "
            f"({fmt_pct(f['ret_real'])} sedan start, CAGR {fmt_pct(f['cagr_real'])}), "
            f"mot CUR {fmt_idx(f['idx_cur'])} och TGT {fmt_idx(f['idx_tgt'])}. "
            f"Gapet REAL−CUR är {fmt_pp(gap_cur)} i totalavkastning. "
            f"Mot Nordnet Balanserad ({fmt_pct(f['ret_bal'])}) ligger REAL "
            f"{fmt_pp(gap_bal)}, dvs. {_fore_efter(gap_bal)} referensen sedan start; "
            f"senaste året är avståndet {fmt_pp(gap_bal_1y)}. "
            f"Riskjusterat: Sharpe {fmt_num(f['sharpe_real'])} för REAL mot "
            f"{fmt_num(f['sharpe_bal'])} för Nordnet Balanserad.</p>"
        )

    egen_worst = egen["categories"].iloc[-1]
    egen_best = egen["categories"].iloc[0]
    pa_best = pa["categories"].iloc[0]

    return f"""
<h3>5.1 Vad siffrorna visar</h3>
{gap_text(pa, "PA")}
{gap_text(egen, "EGEN")}
<p>Kategorimässigt (deskriptivt): i EGEN drog
<strong>{html.escape(egen_best['Kategori'])}</strong> ({fmt_pct(egen_best['Ret_Since'])}) upp
medan <strong>{html.escape(egen_worst['Kategori'])}</strong>
({fmt_pct(egen_worst['Ret_Since'])}, max drawdown {fmt_pct(egen_worst['MaxDD_Since'])}) drog ned.
I PA var <strong>{html.escape(pa_best['Kategori'])}</strong> ({fmt_pct(pa_best['Ret_Since'])})
starkast.</p>

<h3>5.2 Hur REAL-vs-CUR/TGT-gapet får – och inte får – tolkas</h3>
<p>CUR och TGT är <em>statiska buy-and-hold-portföljer av den nuvarande fondlistan,
bakåtprojicerade</em> över hela perioden. Listan är vald med facit i hand: fonder som
åkt ut ur portföljen under resan ingår inte, och fonder som köpts in sent får i
CUR/TGT tillgodoräkna sig hela periodens uppgång. Det ger survivorship- och
look-ahead-bias i referensens favör. <strong>Gapet REAL−CUR/TGT är därför inte ett
skicklighetsmått</strong> – det är en partisk jämförelse där referensen har systematisk
medvind. Det gäller särskilt EGEN, där gapet ({fmt_pp(egen['ret_real'] - egen['ret_cur'])})
till stor del kan bero på att dagens lista innehåller periodens vinnare, inte på att
de löpande besluten kostat motsvarande belopp.</p>
<p><strong>Vad datan stödjer i dag:</strong> (1) Den externa jämförelsen REAL mot
Nordnet-referenserna är rättvis i tiden – samma period, samma bas, daglig TWR, priser
valutakonverterade till SEK uppströms. Där ligger båda portföljerna efter Nordnet
Balanserad sedan start, både absolut och riskjusterat. (2) För PA är REAL-vs-CUR-gapet
litet ({fmt_pp(pa['ret_real'] - pa['ret_cur'])}) med likvärdig Sharpe
({fmt_num(pa['sharpe_real'])} mot {fmt_num(pa['sharpe_cur'])}) och lägre volatilitet
({fmt_pct(pa['vol_real'])} mot {fmt_pct(pa['vol_cur'])}) – den faktiska förvaltningen har
inte uppenbart förstört värde relativt sin egen nuvarande lista, med reservationen att
även den jämförelsen bär samma bias. (3) För EGEN är den realiserade resan kraftigt
svagare än backprojektionen av sin egen lista – ett tydligt <em>underlag för vidare
analys</em>, inte en dom.</p>
<p><strong>Vad som INTE kan besvaras med nuvarande fil (Steg 2 – kräver historiska
vikter över tid samt TER per fond):</strong></p>
<ul>
<li>Brinson-attribution: kommer gapet från allokering eller fondselektion?</li>
<li>Rebalansering mot slump: har omviktningarna tillfört eller kostat?</li>
<li>Strukturell avgiftsmotvind: hur mycket förklarar avgifterna?</li>
<li>Koncentrationsberoende: drivs eventuell över-/underavkastning av en enda position?</li>
</ul>

<h3>5.3 Pilotens metafråga och rekommendation</h3>
<p>Ger den här rapporten beslutsvärde utöver Power BI? Bedömning: <strong>ja, men på
tolknings- och verifieringslagret snarare än på siffrorna</strong>. Kurvorna och
KPI-tabellerna finns redan i Power BI. Det rapporten tillför är (1) en oberoende
omräkning av samtliga KPI:er ur dagsserierna med redovisad tolerans, (2) explicit
bias-hantering – Power BI visar gapet men förklarar inte varför det inte får läsas som
skicklighet, och (3) ett reproducerbart, versionerat underlag som kan byggas om vid
varje datauppdatering.</p>
<p><strong>Rekommendation: fortsätt, med justerat scope.</strong> Rapportens största
begränsning är inte motorn utan datat: utan historiska vikter och TER går det inte att
attribuera EGEN-gapet, och det är den frågan som har störst beslutsvärde för
metodiken. Prioritera därför Steg 2-datat (historiska vikter över tid + TER per fond)
före fler visualiseringar. Behåll Power BI för löpande överblick; låt det här spåret
äga fördjupning, attribution och verifiering.</p>
"""


def _verification_section(result: VerificationResult, contract_failures: list[str]) -> str:
    anchor_rows = "".join(
        f"<tr><td>{row['Series_ID']}</td><td>{fmt_idx(row['Förväntat'])}</td>"
        f"<td>{fmt_idx(row['Observerat'])}</td><td>{'OK' if row['OK'] else 'AVVIKER'}</td></tr>"
        for _, row in result.anchor_rows.iterrows()
    )
    worst = result.kpi_comparison.nlargest(5, "Diff")
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
<p>KPI:erna räknades om oberoende ur <code>Fact_Series_Daily</code> (samma definitioner
som pipelinen: rf 3&nbsp;% årligen, 252 handelsdagar, CAGR på kalenderdagar/365,25) och
jämfördes mot <code>Fact_Series_KPI</code>: {result.n_compared} värden jämförda,
{status}. Största absoluta avvikelse: {result.max_abs_diff:.2e}.</p>
{contract}
<h4>Ankarkontroll REAL-nivåer</h4>
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
thead { background: #eef2f8; }
tr.real-row { background: #e8eefb; font-weight: 600; }
.meta { background: #f6f6f6; border-left: 4px solid #1f4e9c; padding: .8rem 1rem;
        font-size: .85rem; }
.warn { background: #fdf3e7; border-left: 4px solid #e07b39; padding: .8rem 1rem;
        font-size: .9rem; }
"""


def build_html(data: BIData, verification: VerificationResult, contract_failures: list[str]) -> str:
    """Sätt ihop hela rapporten till en självbärande HTML-sträng."""
    daily = data.fact_daily
    start_date = daily["Date"].min().date()
    end_date = daily["Date"].max().date()

    index_sections = "".join(_portfolio_index_section(data, p) for p in PORTFOLIOS)
    category_sections = "".join(_category_section(data, p) for p in PORTFOLIOS)
    allocation_sections = "".join(_allocation_section(data, p) for p in PORTFOLIOS)

    return f"""<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="utf-8">
<title>Fond-rapport (pilot) – {end_date}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Fond-rapport – presterar den verkliga portföljen? (Steg 1-pilot)</h1>
<div class="meta">
<p><strong>Källa:</strong> portfolio_bi_data.xlsx (läst read-only) ·
<strong>Period:</strong> {start_date} – {end_date} ·
<strong>Byggd av:</strong> tools/fond_rapport (deterministisk beräkning i Python).</p>
<p><strong>Metod:</strong> Alla serier är dagliga tidsviktade avkastningar (TWR),
index bas 100, priser valutakonverterade till SEK uppströms. KPI:er enligt
pipelinens definitioner (rf 3&nbsp;%, 252 handelsdagar). Alla tal i rapporten är
beräknade ur källfilen – inget är uppskattat.</p>
</div>

<h2>1. Index: REAL mot referenser</h2>
<p>REAL är den faktiskt realiserade portföljen (transaktionsbaserad). CUR och TGT är
statiska buy-and-hold-referenser av den <em>nuvarande</em> fondlistan respektive
målvikterna, bakåtprojicerade – se förbehållen i avsnitt 5.2 innan gapet tolkas.
Nordnet Balanserad och Offensiv är externa blandfondsreferenser.</p>
{index_sections}

<h2>2. Nyckeltal per serie</h2>
<h3>Sedan start ({start_date} – {end_date})</h3>
{_kpi_table(data.fact_kpi, "Since_Start")}
<h3>Senaste året (1Y)</h3>
{_kpi_table(data.fact_kpi, "1Y")}

<h2>3. Kategorier – var fanns avkastningen?</h2>
<div class="warn"><p>Kategoriserierna är tidsviktade delportföljer (REAL_CAT). De visar
<em>var</em> avkastningen fanns, inte hur mycket varje kategori <em>bidrog</em> till
portföljens totala avkastning – bidragsanalys kräver historiska vikter (Steg 2,
Brinson). Läs tabellerna deskriptivt.</p></div>
{category_sections}

<h2>4. Aktuell allokering (snapshot)</h2>
<p>Vikterna avser <em>ett</em> datum. Historiska vikter över tid finns inte i
BI-filen och ingår i Steg 2.</p>
{allocation_sections}

<h2>5. Tolkning och metodikbedömning</h2>
{_interpretation_section(data)}

<h2>Bilaga: Självverifiering</h2>
{_verification_section(verification, contract_failures)}
</body>
</html>
"""
