"""Avgifts- och kostnadsanalys (Steg 2b): TER-motvind och realiserat courtage.

Principer (hårda krav):

- Fondserierna är **netto** (NAV): TER ligger redan i avkastningen och läggs
  aldrig tillbaka. TER-differenser används för att dela upp observerade gap i
  avgift (kontrollerbar, kan bytas bort) respektive bruttoförvaltning.
- Courtaget är redan indraget i REAL-serien (transaktionsbeloppen inkluderar
  courtage) – det synliggörs här men dras inte av igen.
- Otäckta innehav (``TER_Status = no_data``) får aldrig ett gissat TER. Viktad
  TER redovisas dels **renormaliserad på täckt vikt**, dels som **hård undre
  gräns** (otäckt TER := 0), alltid tillsammans med täckningsgraden.
- TER-nivåerna i ``Dim_Instrument`` är dagens uppgifter; historiska
  TER-förändringar fångas inte och flaggas som förbehåll.

Tidsviktning: vikterna vid ett periodslut får representera den gångna
perioden – [inception, pe_0], (pe_0, pe_1], …, (pe_{n-1}, pe_n] – och varje
period vägs med sitt antal kalenderdagar. Ligger as-of efter sista
periodslutet förlängs den sista viktvektorn till as-of.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .data import BIData

DAYS_PER_YEAR = 365.25
SNAPSHOT_VARIANTS = ["REAL", "CUR", "TGT"]


@dataclass(frozen=True)
class PortfolioTER:
    """Tidsviktad TER för en portfölj, med explicit täckningsredovisning."""

    portfolio: str
    monthly: pd.DataFrame  # per periodslut: Days, Coverage, TER_Renorm, TER_Lower (fraktioner)
    ter_tw_renorm: float  # dagviktad TER renormaliserad på täckt vikt (fraktion/år)
    ter_tw_lower: float  # dagviktad hård undre gräns: otäckt TER := 0 (fraktion/år)
    coverage_tw: float  # dagviktad viktäckning [0, 1]
    uncovered_periods: int  # periodslut helt utan TER-täckning (ingår ej i renorm)
    snapshot_ter: dict[str, float]  # variant -> viktad TER för dagens lista (fraktion/år)
    snapshot_coverage: dict[str, float]  # variant -> täckt vikt i snapshotet
    missing: pd.DataFrame  # innehav i fönstret som saknar TER
    seed_share_tw: float  # andel av dagviktad täckt vikt vars TER kommer från TER-seedfilen ([AU])


@dataclass(frozen=True)
class CourtageSummary:
    """Realiserat courtage ur Fact_Portfolio_Courtage, i fönstret."""

    portfolio: str
    total_sek: float
    n_rows: int
    n_txn: int
    by_instrument: pd.DataFrame  # Display_Name, Kategori, Courtage_SEK, Txn
    first_bucket: pd.Timestamp | None
    last_bucket: pd.Timestamp | None
    avg_mv_sek: float  # dagviktad genomsnittlig portfölj-MV över fönstret
    window_years: float
    pct_per_year: float  # total_sek / (avg_mv_sek * window_years)


@dataclass(frozen=True)
class CostsResult:
    """Samlat resultat för rapportens avgiftsavsnitt."""

    inception: pd.Timestamp
    as_of: pd.Timestamp
    window_years: float
    ter: dict[str, PortfolioTER]
    fee_gap_egen_pa: float  # EGEN − PA, tidsviktad renorm-TER (fraktion/år); negativ = EGEN billigare
    fee_gap_egen_pa_cum: float  # linjärt mekaniskt bidrag över fönstret (fraktion)
    fee_gap_egen_tgt: float  # EGEN tidsviktad REAL-TER − EGEN TGT-snapshot-TER (fraktion/år)
    fee_gap_egen_tgt_cum: float  # linjärt mekaniskt bidrag över fönstret (fraktion)
    cheapest_broad_global: tuple[str, float] | None  # (namn, TER-fraktion) i instrumentuniversumet
    courtage: CourtageSummary  # EGEN (PA saknar courtagerader)
    pa_courtage_rows: int
    flags: list[str] = field(default_factory=list)


# --- tidsviktning -------------------------------------------------------------


def _period_durations(
    period_ends: pd.DatetimeIndex, inception: pd.Timestamp, as_of: pd.Timestamp
) -> pd.Series:
    """Kalenderdagar som varje periodslutsvektor representerar (bakåtblickande)."""
    starts = [inception, *period_ends[:-1]]
    days = [float((pe - start).days) for start, pe in zip(starts, period_ends)]
    days[-1] += float(max(0, (as_of - period_ends[-1]).days))
    return pd.Series(days, index=period_ends)


def _ter_fractions(data: BIData) -> pd.Series:
    """TER per Instrument_Key som fraktion/år (Dim_Instrument anger procent)."""
    return data.dim_instrument.set_index("Instrument_Key")["TER"].astype(float) / 100.0


def _ter_sources(data: BIData) -> pd.Series:
    """TER_Source per Instrument_Key ('nordnet'/'seed'/NA), för proveniensredovisning.

    Bakåtkompatibelt: äldre/syntetiska Dim_Instrument utan TER_Source-kolumn
    ger en tom serie (ingen instrumenttäckning räknas som seed).
    """
    dim = data.dim_instrument
    if "TER_Source" not in dim.columns:
        return pd.Series(pd.NA, index=dim.set_index("Instrument_Key").index)
    return dim.set_index("Instrument_Key")["TER_Source"]


# --- TER per portfölj ----------------------------------------------------------


def _weighted_ter(weights: pd.Series, ter: pd.Series) -> tuple[float, float, float]:
    """(täckt vikt, renormaliserad TER eller NaN, undre gräns) för en viktvektor."""
    covered = ter.notna()
    total_w = float(weights.sum())
    cov_w = float(weights[covered].sum())
    contribution = float((weights[covered] * ter[covered]).sum())
    renorm = contribution / cov_w if cov_w > 0 else float("nan")
    lower = contribution / total_w if total_w > 0 else float("nan")
    return cov_w / total_w if total_w > 0 else float("nan"), renorm, lower


def compute_portfolio_ter(
    data: BIData, portfolio: str, inception: pd.Timestamp, as_of: pd.Timestamp
) -> PortfolioTER:
    """Tidsviktad TER ur Dim_Instrument × Fact_Portfolio_Alloc_Monthly."""
    ter = _ter_fractions(data)
    ter_source = _ter_sources(data)
    alloc = data.fact_alloc_monthly
    alloc = alloc[
        (alloc["Portfolio_Key"] == portfolio)
        & (alloc["Period_End_Date"] >= inception)
        & (alloc["Period_End_Date"] <= as_of)
    ]
    if alloc.empty:
        raise ValueError(f"Fact_Portfolio_Alloc_Monthly saknar {portfolio} i fönstret.")

    period_ends = pd.DatetimeIndex(sorted(alloc["Period_End_Date"].unique()))
    durations = _period_durations(period_ends, inception, as_of)

    rows = []
    for pe in period_ends:
        group = alloc[alloc["Period_End_Date"] == pe]
        weights = group.groupby("Instrument_Key")["Weight"].sum()
        period_ter = ter.reindex(weights.index)
        coverage, renorm, lower = _weighted_ter(weights, period_ter)
        covered = period_ter.notna()
        cov_w = float(weights[covered].sum())
        seed_w = float(weights[covered & (ter_source.reindex(weights.index) == "seed")].sum())
        rows.append(
            {
                "Period_End_Date": pe,
                "Days": float(durations.loc[pe]),
                "Coverage": coverage,
                "TER_Renorm": renorm,
                "TER_Lower": lower,
                "Seed_Share": seed_w / cov_w if cov_w > 0 else float("nan"),
            }
        )
    monthly = pd.DataFrame(rows).set_index("Period_End_Date")

    covered_mask = monthly["TER_Renorm"].notna()
    renorm_days = monthly.loc[covered_mask, "Days"]
    ter_tw_renorm = (
        float((monthly.loc[covered_mask, "TER_Renorm"] * renorm_days).sum() / renorm_days.sum())
        if renorm_days.sum() > 0
        else float("nan")
    )
    ter_tw_lower = float((monthly["TER_Lower"] * monthly["Days"]).sum() / monthly["Days"].sum())
    coverage_tw = float((monthly["Coverage"] * monthly["Days"]).sum() / monthly["Days"].sum())
    seed_share_tw = (
        float((monthly.loc[covered_mask, "Seed_Share"] * renorm_days).sum() / renorm_days.sum())
        if renorm_days.sum() > 0
        else float("nan")
    )

    snapshot_ter: dict[str, float] = {}
    snapshot_coverage: dict[str, float] = {}
    for variant in SNAPSHOT_VARIANTS:
        snap = data.fact_alloc[data.fact_alloc["Series_ID"] == f"PORT_{portfolio}_{variant}"]
        if snap.empty:
            continue
        weights = snap.groupby("Instrument_Key")["Weight"].sum()
        coverage, renorm, _ = _weighted_ter(weights, ter.reindex(weights.index))
        snapshot_ter[variant] = renorm
        snapshot_coverage[variant] = coverage

    merged = alloc.merge(
        ter.rename("TER_frac"), left_on="Instrument_Key", right_index=True, how="left"
    )
    missing_rows = merged[merged["TER_frac"].isna()]
    missing = (
        missing_rows.groupby(["Instrument_Key", "ISIN", "Display_Name"], dropna=False)
        .agg(Perioder=("Period_End_Date", "nunique"), Maxvikt=("Weight", "max"))
        .reset_index()
        .sort_values("Maxvikt", ascending=False)
        .reset_index(drop=True)
    )

    return PortfolioTER(
        portfolio=portfolio,
        monthly=monthly,
        ter_tw_renorm=ter_tw_renorm,
        ter_tw_lower=ter_tw_lower,
        coverage_tw=coverage_tw,
        uncovered_periods=int((~covered_mask).sum()),
        snapshot_ter=snapshot_ter,
        snapshot_coverage=snapshot_coverage,
        missing=missing,
        seed_share_tw=seed_share_tw,
    )


# --- courtage -------------------------------------------------------------------


def _courtage_in_window(
    courtage: pd.DataFrame, inception: pd.Timestamp, as_of: pd.Timestamp
) -> pd.DataFrame:
    """Månadsbucketar som överlappar [inception, as_of].

    Fact_Portfolio_Courtage aggregerar per kalendermånad (Period_End_Date =
    månadsslut). En bucket ingår om dess månad överlappar fönstret: bucketens
    slut på eller efter inception och dess månadsstart på eller före as-of.
    """
    bucket_end = courtage["Period_End_Date"]
    bucket_start = bucket_end.dt.to_period("M").dt.start_time
    return courtage[(bucket_end >= inception) & (bucket_start <= as_of)]


def compute_courtage(
    data: BIData, portfolio: str, inception: pd.Timestamp, as_of: pd.Timestamp
) -> CourtageSummary:
    """Realiserat courtage i fönstret, i SEK och i %/år av dagviktad snitt-MV."""
    ct = _courtage_in_window(
        data.fact_courtage[data.fact_courtage["Portfolio_Key"] == portfolio], inception, as_of
    )

    alloc = data.fact_alloc_monthly
    alloc = alloc[
        (alloc["Portfolio_Key"] == portfolio)
        & (alloc["Period_End_Date"] >= inception)
        & (alloc["Period_End_Date"] <= as_of)
    ]
    mv = alloc.groupby("Period_End_Date")["Portfolio_MV_SEK"].first().sort_index()
    durations = _period_durations(pd.DatetimeIndex(mv.index), inception, as_of)
    avg_mv = float((mv * durations).sum() / durations.sum())
    window_years = (as_of - inception).days / DAYS_PER_YEAR

    total = float(ct["Courtage_SEK"].sum())
    by_instrument = (
        ct.groupby(["Display_Name", "Category"], dropna=False)
        .agg(Courtage_SEK=("Courtage_SEK", "sum"), Txn=("Txn_Count", "sum"))
        .reset_index()
        .sort_values("Courtage_SEK", ascending=False)
        .reset_index(drop=True)
    )

    return CourtageSummary(
        portfolio=portfolio,
        total_sek=total,
        n_rows=len(ct),
        n_txn=int(ct["Txn_Count"].sum()),
        by_instrument=by_instrument,
        first_bucket=pd.Timestamp(ct["Period_End_Date"].min()) if not ct.empty else None,
        last_bucket=pd.Timestamp(ct["Period_End_Date"].max()) if not ct.empty else None,
        avg_mv_sek=avg_mv,
        window_years=window_years,
        pct_per_year=total / (avg_mv * window_years) if avg_mv > 0 and window_years > 0 else float("nan"),
    )


# --- samlad analys ---------------------------------------------------------------


def compute_costs(data: BIData, inception: pd.Timestamp, as_of: pd.Timestamp) -> CostsResult:
    """Hela kostnadsanalysen för rapportens avgiftsavsnitt."""
    flags: list[str] = []
    ter = {p: compute_portfolio_ter(data, p, inception, as_of) for p in ("EGEN", "PA")}

    for pter in ter.values():
        if not pter.missing.empty:
            flags.append(
                f"{pter.portfolio}: {len(pter.missing)} innehav i fönstret saknar TER "
                f"(dagviktad täckning {pter.coverage_tw * 100:.0f} %"
                + (
                    f", {pter.uncovered_periods} periodslut helt utan täckning"
                    if pter.uncovered_periods
                    else ""
                )
                + ") – tidsviktad TER bygger på täckt vikt."
            )
    flags.append(
        "TER-nivåerna är dagens uppgifter (Dim_Instrument); historiska "
        "TER-förändringar fångas inte."
    )
    for pter in ter.values():
        if pter.seed_share_tw and pter.seed_share_tw > 0:
            flags.append(
                f"{pter.portfolio}: {pter.seed_share_tw * 100:.0f} % av den dagviktade "
                "TER-täckningen kommer från TER-seedfilen (utträdda/otäckta innehav) – "
                "dagens nivå, inte den historiska."
            )
    flags.append(
        "Spread och FX-växlingsavgift vid ETF-handel fångas inte av datan och "
        "kvantifieras därför inte."
    )
    flags.append(
        "Nordnet Balanserad/Offensiv saknar TER i datan – deras avgiftsnivå ingår "
        "inte i jämförelsen."
    )

    window_years = (as_of - inception).days / DAYS_PER_YEAR
    fee_gap_egen_pa = ter["EGEN"].ter_tw_renorm - ter["PA"].ter_tw_renorm
    fee_gap_egen_tgt = ter["EGEN"].ter_tw_renorm - ter["EGEN"].snapshot_ter.get("TGT", float("nan"))

    dim = data.dim_instrument
    broad = dim[
        (dim["Category"] == "Breda fonder") & (dim["Geography"] == "Global") & dim["TER"].notna()
    ]
    cheapest = None
    if not broad.empty:
        row = broad.loc[broad["TER"].idxmin()]
        cheapest = (str(row["Display_Name"]), float(row["TER"]) / 100.0)

    courtage = compute_courtage(data, "EGEN", inception, as_of)
    pa_rows = len(
        _courtage_in_window(
            data.fact_courtage[data.fact_courtage["Portfolio_Key"] == "PA"], inception, as_of
        )
    )

    return CostsResult(
        inception=inception,
        as_of=as_of,
        window_years=window_years,
        ter=ter,
        fee_gap_egen_pa=fee_gap_egen_pa,
        fee_gap_egen_pa_cum=fee_gap_egen_pa * window_years,
        fee_gap_egen_tgt=fee_gap_egen_tgt,
        fee_gap_egen_tgt_cum=fee_gap_egen_tgt * window_years,
        cheapest_broad_global=cheapest,
        courtage=courtage,
        pa_courtage_rows=pa_rows,
        flags=flags,
    )


# --- oberoende verifiering --------------------------------------------------------


def _ter_tw_independent(
    data: BIData, portfolio: str, inception: pd.Timestamp, as_of: pd.Timestamp
) -> tuple[float, float, float]:
    """Oberoende omräkning av (renorm, undre gräns, täckning) via pivotmatriser.

    Huvudvägen loopar periodslut och viktar per grupp; här byggs i stället en
    vikt-matris (periodslut × instrument) och allt räknas vektoriserat. Två
    skilda vägar till samma tal – avviker de är beräkningen fel.
    """
    alloc = data.fact_alloc_monthly
    alloc = alloc[
        (alloc["Portfolio_Key"] == portfolio)
        & (alloc["Period_End_Date"] >= inception)
        & (alloc["Period_End_Date"] <= as_of)
    ]
    weights = alloc.pivot_table(
        index="Period_End_Date", columns="Instrument_Key", values="Weight", aggfunc="sum"
    ).fillna(0.0)
    ter = _ter_fractions(data).reindex(weights.columns)
    covered = ter.notna().to_numpy()

    w = weights.to_numpy(dtype=float)
    t = np.where(covered, ter.fillna(0.0).to_numpy(dtype=float), 0.0)
    total_w = w.sum(axis=1)
    cov_w = (w * covered).sum(axis=1)
    contribution = w @ t

    with np.errstate(divide="ignore", invalid="ignore"):
        renorm = np.where(cov_w > 0, contribution / cov_w, np.nan)
    lower = contribution / total_w
    coverage = cov_w / total_w

    days = _period_durations(pd.DatetimeIndex(weights.index), inception, as_of).to_numpy()
    has_renorm = ~np.isnan(renorm)
    tw_renorm = float((renorm[has_renorm] * days[has_renorm]).sum() / days[has_renorm].sum())
    tw_lower = float((lower * days).sum() / days.sum())
    tw_coverage = float((coverage * days).sum() / days.sum())
    return tw_renorm, tw_lower, tw_coverage


def verify_costs(data: BIData, costs: CostsResult) -> pd.DataFrame:
    """Kontrolltabell: TER-omräkning, courtagesummor och snapshot-täckning."""
    tolerance = 1e-12
    rows: list[dict] = []

    for portfolio, pter in costs.ter.items():
        renorm, lower, coverage = _ter_tw_independent(
            data, portfolio, costs.inception, costs.as_of
        )
        for name, shown, recomputed in (
            (f"{portfolio}: tidsviktad TER (renorm)", pter.ter_tw_renorm, renorm),
            (f"{portfolio}: tidsviktad TER (undre gräns)", pter.ter_tw_lower, lower),
            (f"{portfolio}: dagviktad täckning", pter.coverage_tw, coverage),
        ):
            diff = abs(shown - recomputed)
            rows.append(
                {"Kontroll": name, "Visat": shown, "Omräknat": recomputed, "Diff": diff,
                 "OK": diff <= tolerance}
            )

    ct_all = _courtage_in_window(
        data.fact_courtage[data.fact_courtage["Portfolio_Key"] == "EGEN"],
        costs.inception,
        costs.as_of,
    )
    raw_total = float(ct_all["Courtage_SEK"].sum())
    table_total = float(costs.courtage.by_instrument["Courtage_SEK"].sum())
    for name, shown, recomputed in (
        ("Courtage: summa rader mot facten", costs.courtage.total_sek, raw_total),
        ("Courtage: instrumenttabell mot totalen", table_total, costs.courtage.total_sek),
        ("Courtage: antal transaktioner", float(costs.courtage.n_txn), float(ct_all["Txn_Count"].sum())),
    ):
        diff = abs(shown - recomputed)
        rows.append(
            {"Kontroll": name, "Visat": shown, "Omräknat": recomputed, "Diff": diff,
             "OK": diff <= 1e-9}
        )

    for portfolio, pter in costs.ter.items():
        for variant, coverage in pter.snapshot_coverage.items():
            rows.append(
                {
                    "Kontroll": f"{portfolio} {variant}: snapshot-täckning = 1,0",
                    "Visat": coverage,
                    "Omräknat": 1.0,
                    "Diff": abs(coverage - 1.0),
                    "OK": abs(coverage - 1.0) <= 1e-9,
                }
            )

    return pd.DataFrame(rows)
