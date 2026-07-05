"""Attribution (Steg 2a-data): Brinson-Fachler, rebalansering-vs-slump, koncentration.

Referensportfölj är TGT (målvikterna, kolumn AndelP): det är den uttalade policyn
och därmed den naturliga Brinson-referensen. CUR är dagens faktiska mix
bakåtprojicerad – en driftad ögonblicksbild, inte en policy – och används bara
som kontext.

Datakällor (båda read-only):
  1. portfolio_bi_data.xlsx – vikthistorik (Fact_Portfolio_Alloc_Monthly),
     REAL/REAL_CAT/TGT-serier, snapshotvikter, instrumentdimension.
  2. data/cache_prices.parquet – samma forward-fyllda prismatris (SEK-FX ingår)
     som upstream bygger serierna ur. Behövs för TGT:s kategoriavkastningar och
     fondnivåbidrag, som inte finns i BI-filen. Replikeringen av TGT/CUR ur
     cachen verifieras mot BI-seriens IDX innan resultaten används.

Alla beräkningar är deterministiska; permutationstestet använder fast seed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src.portfolio import (
    _fx_tickers_for_assets,
    _portfolio_price_frame,
    _portfolio_returns_from_weights,
    _prices_to_base,
)
from src.prices import returns_from_prices

from .data import BIData

REFERENCE_VARIANT = "TGT"
REPLICATION_TOLERANCE = 1e-6  # indexpunkter; replikeringen ska vara maskinexakt
PERMUTATION_SEED = 20260704
N_PERMUTATIONS = 20_000
TOP_N_FUNDS = 8


@dataclass(frozen=True)
class PortfolioAttribution:
    """Attributionsresultat för en portfölj, alla tal i beslutsordning."""

    portfolio: str
    window_start: pd.Timestamp  # första månadsslut med vikter
    window_end: pd.Timestamp
    n_months: int

    # Totaler över fönstret (geometriskt sammansatta)
    r_real_window: float
    r_ref_window: float
    active_window: float  # r_real_window - r_ref_window
    active_since_start: float  # ur BI-seriernas slutindex, hela historiken
    pre_window_effect: float  # active_since_start - active_window

    # Carino-länkade komponenter (summerar till active_window)
    effects_by_category: pd.DataFrame  # index: kategori; kolumner: Allokering, Selektion, Interaktion
    allocation_total: float
    selection_total: float
    interaction_total: float
    residual_real: float  # länkad e_p: intra-månadsflöden i REAL
    residual_ref: float  # länkad e_b: korssammansättning i dagligt rebalanserad TGT
    decomposition_residual: float  # komponentsumma minus active_window (ska vara ~maskineps)

    monthly: pd.DataFrame  # per månad: R_real, R_ref, aktiv, A, S, I, e_p, e_b

    # Rebalansering vs slump (permutationstest på viktbanans ordning)
    perm_statistic: float
    perm_null_mean: float
    perm_null_std: float
    perm_percentile: float
    perm_p_two_sided: float
    perm_n: int

    # Koncentration: Carino-länkade fondbidrag
    fund_contributions: pd.DataFrame  # per fond: C_real, C_ref, Gap
    fund_residual_real: float  # R_real_window - summa C_real (flöden m.m.)
    fund_residual_ref: float
    gap_top3_share: float  # |topp-3-gapbidrag| / summa |gapbidrag|

    # Verifiering
    replication_max_diff: float  # replikerad TGT-IDX mot BI-seriens IDX
    max_abs_e_real: float  # största månatliga identitetsresidual REAL
    max_abs_e_ref: float
    zero_weight_cells: int  # kategori-månader där REAL saknade innehav (konvention r_p := r_ref)

    flags: list[str] = field(default_factory=list)


# --- hjälpare -----------------------------------------------------------------


def _series_idx(bi: BIData, series_id: str) -> pd.Series:
    sub = bi.fact_daily[bi.fact_daily["Series_ID"] == series_id]
    if sub.empty:
        raise KeyError(f"Serien saknas i Fact_Series_Daily: {series_id}")
    return sub.set_index("Date")["IDX"].sort_index()


def _sample_idx(idx: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    """Indexnivå per datum, forward-fyllt (senast kända värde på eller före datumet)."""
    union = idx.index.union(dates)
    return idx.reindex(union).ffill().loc[dates]


def _monthly_returns_from_idx(idx: pd.Series, period_ends: pd.DatetimeIndex) -> pd.Series:
    levels = _sample_idx(idx, period_ends)
    return levels.pct_change().dropna()


def _instrument_mapping(bi: BIData) -> pd.DataFrame:
    """Minimal mapping-frame (Yahoo_Ticker + Price_Currency) för upstreams FX-logik."""
    mapping = bi.dim_instrument.copy()
    mapping["Yahoo_Ticker"] = mapping["Instrument_Key"]
    return mapping


def _fund_daily_returns_sek(
    bi: BIData, tickers: list[str], start: pd.Timestamp, price_cache: pd.DataFrame
) -> pd.DataFrame:
    """Dagliga SEK-avkastningar per fond, exakt enligt upstreams konstruktion."""
    mapping = _instrument_mapping(bi)
    fx = _fx_tickers_for_assets(tickers, mapping, "SEK")
    px = _portfolio_price_frame(price_cache, tickers, start, extra_tickers=fx)
    px_base = _prices_to_base(px, tickers, mapping, "SEK")
    return returns_from_prices(px_base)


def _compound(returns: pd.Series) -> float:
    return float((1.0 + returns).prod() - 1.0)


def _carino_k(r_p: pd.Series, r_b: pd.Series) -> pd.Series:
    """Carinos länkkoefficient per period; gränsvärde 1/(1+r) när r_p == r_b."""
    diff = r_p - r_b
    with np.errstate(divide="ignore", invalid="ignore"):
        k = (np.log1p(r_p) - np.log1p(r_b)) / diff
    limit = 1.0 / (1.0 + r_p)
    return pd.Series(np.where(np.abs(diff) < 1e-12, limit, k), index=r_p.index)


def _carino_scale(r_p_total: float, r_b_total: float) -> float:
    if abs(r_p_total - r_b_total) < 1e-12:
        return 1.0 / (1.0 + r_p_total)
    return (np.log1p(r_p_total) - np.log1p(r_b_total)) / (r_p_total - r_b_total)


def _single_series_carino(r: pd.Series, r_total: float) -> pd.Series:
    """Länkfaktorer så att skalade periodbidrag summerar till totalavkastningen."""
    with np.errstate(divide="ignore", invalid="ignore"):
        k = np.log1p(r) / r
    k = pd.Series(np.where(np.abs(r) < 1e-12, 1.0, k), index=r.index)
    k_total = np.log1p(r_total) / r_total if abs(r_total) > 1e-12 else 1.0
    return k / k_total


# --- kärnberäkning ------------------------------------------------------------


def compute_attribution(
    bi: BIData, portfolio: str, price_cache: pd.DataFrame
) -> PortfolioAttribution:
    flags: list[str] = []
    alloc = bi.fact_alloc_monthly[bi.fact_alloc_monthly["Portfolio_Key"] == portfolio].copy()
    if alloc.empty:
        raise ValueError(f"Fact_Portfolio_Alloc_Monthly saknar portfölj {portfolio}")
    alloc["Period_End_Date"] = pd.to_datetime(alloc["Period_End_Date"])
    period_ends = pd.DatetimeIndex(sorted(alloc["Period_End_Date"].unique()))

    # --- REAL-sidan: kategorivikter och kategoriavkastningar (ankrade i BI-filen)
    w_real = (
        alloc.pivot_table(
            index="Period_End_Date", columns="Category", values="Weight", aggfunc="sum"
        )
        .reindex(period_ends)
        .fillna(0.0)
    )

    dim = bi.dim_series
    cat_series = dim[
        (dim["Portfolio_Key"] == portfolio) & (dim["Is_Category_Series"] == True)  # noqa: E712
    ][["Series_ID", "Category"]]
    r_real_cat = pd.DataFrame(
        {
            row["Category"]: _monthly_returns_from_idx(
                _series_idx(bi, row["Series_ID"]), period_ends
            )
            for _, row in cat_series.iterrows()
        }
    )

    # --- Referenssidan (TGT): replikera fondnivån ur priscachen och verifiera
    snap = bi.fact_alloc[bi.fact_alloc["Series_ID"] == f"PORT_{portfolio}_{REFERENCE_VARIANT}"]
    w_ref_fund = snap.set_index("Instrument_Key")["Weight"].astype(float)
    ref_meta = dim[dim["Series_ID"] == f"PORT_{portfolio}_{REFERENCE_VARIANT}"].iloc[0]
    series_start = pd.to_datetime(ref_meta["Include_From_Date"])
    idx0 = float(ref_meta["Initial_Index_Value"])

    fund_rets = _fund_daily_returns_sek(bi, list(w_ref_fund.index), series_start, price_cache)
    ref_ret_daily = _portfolio_returns_from_weights(fund_rets, w_ref_fund)
    ref_ret_daily.iloc[0] = 0.0
    ref_idx_replicated = idx0 * (1.0 + ref_ret_daily).cumprod()
    ref_idx_bi = _series_idx(bi, f"PORT_{portfolio}_{REFERENCE_VARIANT}")
    joined = pd.concat(
        [ref_idx_replicated.rename("replik"), ref_idx_bi.rename("bi")], axis=1, join="inner"
    )
    replication_max_diff = float((joined["replik"] - joined["bi"]).abs().max())
    if replication_max_diff > REPLICATION_TOLERANCE:
        raise ValueError(
            f"Replikeringen av PORT_{portfolio}_{REFERENCE_VARIANT} avviker från BI-serien "
            f"(max {replication_max_diff:.3e} indexpunkter) – attributionen avbryts."
        )

    cat_by_fund = bi.dim_instrument.set_index("Instrument_Key")["Category"]
    missing_cat = [t for t in w_ref_fund.index if t not in cat_by_fund.index]
    if missing_cat:
        raise ValueError(f"Instrument saknas i Dim_Instrument: {missing_cat}")

    categories = sorted(set(w_real.columns) | set(cat_by_fund.loc[w_ref_fund.index]))
    w_ref_cat = (
        w_ref_fund.groupby(cat_by_fund.loc[w_ref_fund.index]).sum().reindex(categories).fillna(0.0)
    )
    w_real = w_real.reindex(columns=categories).fillna(0.0)

    # TGT:s kategoriavkastning per månad: dagligt konstantviktat inom kategori,
    # sammansatt över månadsfönstret (pe[i-1], pe[i]].
    months = period_ends[1:]
    r_ref_cat = pd.DataFrame(index=months, columns=categories, dtype=float)
    for cat in categories:
        funds = [t for t in w_ref_fund.index if cat_by_fund.loc[t] == cat]
        if not funds:
            r_ref_cat[cat] = np.nan
            continue
        w_in = w_ref_fund.loc[funds] / w_ref_fund.loc[funds].sum()
        daily = fund_rets[funds].mul(w_in, axis=1).sum(axis=1)
        for prev, cur in zip(period_ends[:-1], months):
            window = daily[(daily.index > prev) & (daily.index <= cur)]
            r_ref_cat.loc[cur, cat] = _compound(window)

    # Kategorier som referensen saknar: ingen referensavkastning finns – sätt
    # r_ref := REAL:s kategoriavkastning så att hela effekten hamnar i allokering=0
    # och selektion=0; avvikelsen fångas i residualen. Flagga om det inträffar.
    ref_missing = [c for c in categories if r_ref_cat[c].isna().all()]
    if ref_missing:
        for cat in ref_missing:
            r_ref_cat[cat] = r_real_cat.get(cat)
        flags.append(
            f"Kategori(er) utan TGT-innehav: {ref_missing} – ingen ren allokerings-/"
            "selektionseffekt kan beräknas för dem; bidraget ligger i residualen."
        )

    # REAL-kategoriavkastning saknas där REAL aldrig ägt kategorin i månaden:
    # konvention r_real := r_ref => selektion = interaktion = 0 för cellen.
    r_real_cat = r_real_cat.reindex(index=months, columns=categories)
    w_real_lag = w_real.shift(1).dropna(how="all").reindex(months).fillna(0.0)
    zero_mask = (w_real_lag == 0.0) | r_real_cat.isna()
    zero_weight_cells = int((zero_mask & (~r_ref_cat.isna())).to_numpy().sum())
    r_real_cat = r_real_cat.where(~zero_mask, r_ref_cat)

    # --- Totalserier per månad (ur BI-seriernas IDX, den officiella sanningen)
    real_idx_bi = _series_idx(bi, f"PORT_{portfolio}_REAL")
    r_real_m = _monthly_returns_from_idx(real_idx_bi, period_ends).reindex(months)
    r_ref_m = _monthly_returns_from_idx(ref_idx_bi, period_ends).reindex(months)

    # Identitetsresidualer: intra-månadsflöden i REAL respektive daglig
    # rebalansering/korssammansättning i referensen.
    r_real_hat = (w_real_lag * r_real_cat).sum(axis=1)
    r_ref_hat = (w_ref_cat * r_ref_cat).sum(axis=1)
    e_real = r_real_m - r_real_hat
    e_ref = r_ref_m - r_ref_hat

    # --- Brinson-Fachler per månad och kategori
    active_m = r_real_m - r_ref_m
    w_diff = w_real_lag.sub(w_ref_cat, axis=1)
    alloc_m = w_diff * r_ref_cat.sub(r_ref_hat, axis=0)
    sel_m = (r_real_cat - r_ref_cat).mul(w_ref_cat, axis=1)
    inter_m = w_diff * (r_real_cat - r_ref_cat)

    # --- Carino-länkning till fönstertotaler
    r_real_window = _compound(r_real_m)
    r_ref_window = _compound(r_ref_m)
    active_window = r_real_window - r_ref_window
    k = _carino_k(r_real_m, r_ref_m) / _carino_scale(r_real_window, r_ref_window)

    effects = pd.DataFrame(
        {
            "Allokering": alloc_m.mul(k, axis=0).sum(),
            "Selektion": sel_m.mul(k, axis=0).sum(),
            "Interaktion": inter_m.mul(k, axis=0).sum(),
        }
    ).reindex(categories)
    residual_real = float((e_real * k).sum())
    residual_ref = float(-(e_ref * k).sum())
    component_sum = float(effects.to_numpy().sum()) + residual_real + residual_ref
    decomposition_residual = component_sum - active_window

    # --- Sedan start vs fönster: startup-/förfönstereffekt
    real_full = float(real_idx_bi.iloc[-1] / real_idx_bi.iloc[0] - 1.0)
    ref_full = float(ref_idx_bi.iloc[-1] / ref_idx_bi.iloc[0] - 1.0)
    active_since_start = real_full - ref_full

    # --- Rebalansering vs slump: permutera viktbanans tidsordning
    rng = np.random.default_rng(PERMUTATION_SEED)
    r_ref_centered = r_ref_cat.sub(r_ref_hat, axis=0).to_numpy(dtype=float)
    tilts = w_diff.to_numpy(dtype=float)
    statistic = float((tilts * r_ref_centered).sum())
    n_m = tilts.shape[0]
    null = np.empty(N_PERMUTATIONS)
    for i in range(N_PERMUTATIONS):
        null[i] = float((tilts[rng.permutation(n_m), :] * r_ref_centered).sum())
    percentile = float((null <= statistic).mean())
    p_low = (1 + int((null <= statistic).sum())) / (N_PERMUTATIONS + 1)
    p_high = (1 + int((null >= statistic).sum())) / (N_PERMUTATIONS + 1)
    p_two = float(min(1.0, 2.0 * min(p_low, p_high)))

    # --- Koncentration: fondnivåbidrag (Carino-länkade så att de summerar rätt)
    fund_contributions, fund_res_real, fund_res_ref = _fund_level_contributions(
        bi, portfolio, alloc, period_ends, months, w_ref_fund, fund_rets, price_cache,
        r_real_m, r_ref_m, r_real_window, r_ref_window,
    )
    gap_abs = fund_contributions["Gap"].abs()
    gap_top3_share = float(gap_abs.nlargest(3).sum() / gap_abs.sum()) if gap_abs.sum() > 0 else np.nan

    monthly = pd.DataFrame(
        {
            "R_real": r_real_m,
            "R_ref": r_ref_m,
            "Aktiv": active_m,
            "Allokering": alloc_m.sum(axis=1),
            "Selektion": sel_m.sum(axis=1),
            "Interaktion": inter_m.sum(axis=1),
            "e_real": e_real,
            "e_ref": e_ref,
        }
    )

    flags.append(
        "Komponenterna är netto avgifter (NAV) – ingen komponent nedan isolerar "
        "avgiftsbidraget; avgiftsmotvinden kvantifieras separat i avsnitt 6 (Steg 2b)."
    )
    flags.append(
        "CUR/TGT är dagens lista bakåtprojicerad (survivorship/look-ahead). "
        "Dekomponeringen visar VAR gapet uppstår mekaniskt, inte att TGT var en "
        "uppnåelig motfaktisk portfölj."
    )

    return PortfolioAttribution(
        portfolio=portfolio,
        window_start=period_ends[0],
        window_end=period_ends[-1],
        n_months=len(months),
        r_real_window=r_real_window,
        r_ref_window=r_ref_window,
        active_window=active_window,
        active_since_start=active_since_start,
        pre_window_effect=active_since_start - active_window,
        effects_by_category=effects,
        allocation_total=float(effects["Allokering"].sum()),
        selection_total=float(effects["Selektion"].sum()),
        interaction_total=float(effects["Interaktion"].sum()),
        residual_real=residual_real,
        residual_ref=residual_ref,
        decomposition_residual=float(decomposition_residual),
        monthly=monthly,
        perm_statistic=statistic,
        perm_null_mean=float(null.mean()),
        perm_null_std=float(null.std(ddof=1)),
        perm_percentile=percentile,
        perm_p_two_sided=p_two,
        perm_n=N_PERMUTATIONS,
        fund_contributions=fund_contributions,
        fund_residual_real=fund_res_real,
        fund_residual_ref=fund_res_ref,
        gap_top3_share=gap_top3_share,
        replication_max_diff=replication_max_diff,
        max_abs_e_real=float(e_real.abs().max()),
        max_abs_e_ref=float(e_ref.abs().max()),
        zero_weight_cells=zero_weight_cells,
        flags=flags,
    )


def _fund_level_contributions(
    bi: BIData,
    portfolio: str,
    alloc: pd.DataFrame,
    period_ends: pd.DatetimeIndex,
    months: pd.DatetimeIndex,
    w_ref_fund: pd.Series,
    ref_fund_rets: pd.DataFrame,
    price_cache: pd.DataFrame,
    r_real_m: pd.Series,
    r_ref_m: pd.Series,
    r_real_window: float,
    r_ref_window: float,
) -> tuple[pd.DataFrame, float, float]:
    """Carino-länkade fondbidrag för REAL (historiska vikter) och TGT (konstanta)."""
    real_funds = sorted(alloc["Instrument_Key"].unique())
    all_funds = sorted(set(real_funds) | set(w_ref_fund.index))

    ref_meta = bi.dim_series[bi.dim_series["Series_ID"] == f"PORT_{portfolio}_{REFERENCE_VARIANT}"].iloc[0]
    series_start = pd.to_datetime(ref_meta["Include_From_Date"])
    extra = [t for t in all_funds if t not in ref_fund_rets.columns]
    price_cache_cols = ref_fund_rets
    if extra:
        # Fondavkastningar för historiska REAL-innehav som inte ingår i TGT.
        extra_rets = _fund_daily_returns_sek(bi, extra, series_start, price_cache)
        price_cache_cols = pd.concat([ref_fund_rets, extra_rets[extra]], axis=1)

    # Månadsavkastning per fond på portföljens periodgrid
    fund_monthly = pd.DataFrame(index=months, columns=all_funds, dtype=float)
    for prev, cur in zip(period_ends[:-1], months):
        window = price_cache_cols[(price_cache_cols.index > prev) & (price_cache_cols.index <= cur)]
        fund_monthly.loc[cur] = (1.0 + window[all_funds]).prod() - 1.0

    # REAL: föregående månadsslutsvikter per fond
    w_real_fund = (
        alloc.pivot_table(index="Period_End_Date", columns="Instrument_Key", values="Weight", aggfunc="sum")
        .reindex(period_ends)
        .fillna(0.0)
        .shift(1)
        .reindex(months)
        .fillna(0.0)
        .reindex(columns=all_funds)
        .fillna(0.0)
    )

    k_real = _single_series_carino(r_real_m, r_real_window)
    k_ref = _single_series_carino(r_ref_m, r_ref_window)

    c_real = (w_real_fund * fund_monthly).mul(k_real, axis=0).sum()
    w_ref_full = w_ref_fund.reindex(all_funds).fillna(0.0)
    c_ref = fund_monthly.mul(w_ref_full, axis=1).mul(k_ref, axis=0).sum()

    names = bi.dim_instrument.set_index("Instrument_Key")["Display_Name"]
    cats = bi.dim_instrument.set_index("Instrument_Key")["Category"]
    out = pd.DataFrame(
        {
            "Fond": [str(names.get(t, t)) for t in all_funds],
            "Kategori": [str(cats.get(t, "?")) for t in all_funds],
            "C_real": c_real.reindex(all_funds),
            "C_ref": c_ref.reindex(all_funds),
        },
    )
    out["Gap"] = out["C_real"] - out["C_ref"]
    out = out.sort_values("Gap", key=lambda s: s.abs(), ascending=False)

    fund_res_real = float(r_real_window - c_real.sum())
    fund_res_ref = float(r_ref_window - c_ref.sum())
    return out, fund_res_real, fund_res_ref


def run_attribution(bi: BIData, price_cache_path: Path) -> dict[str, PortfolioAttribution]:
    """Attribution för samtliga portföljer i Fact_Portfolio_Alloc_Monthly."""
    prices = pd.read_parquet(price_cache_path)
    prices.index = pd.to_datetime(prices.index)
    portfolios = sorted(bi.fact_alloc_monthly["Portfolio_Key"].unique())
    return {p: compute_attribution(bi, p, prices) for p in portfolios}
