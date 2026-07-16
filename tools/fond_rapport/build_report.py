"""CLI: bygg fond-rapporten som en självbärande HTML-fil.

Körs från projektroten:

    python -m tools.fond_rapport.build_report [--input SÖKVÄG] [--output-dir KATALOG]
                                              [--as-of YYYY-MM-DD]

Läser produktions-BI-arbetsboken read-only (default från config.toml). Härleder ett
gemensamt analysfönster ur datan: fönstret startar vid EGEN:s inception (första
värderade REAL-position) och slutar vid as-of (default = senaste datat i filen). Alla
serier rebaseras till bas 100 vid startdatumet och skärs till fönstret; horisonter och
KPI:er räknas relativt as-of. Verifierar KPI:erna mot en oberoende omräkning och skriver
rapporten till dataroten (fond_rapport_<as-of>.html). Ankaravvikelser eller
datakontraktsbrott stoppar bygget.

Årsskifteskörning: ``--as-of 2026-12-31``.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path

import pandas as pd

from src.config import BI_DATA_OUTPUT_PATH, FOND_RAPPORT_OUTPUT_DIR, BASE_DIR
from src.prices import CACHE_PATH

from .attribution import run_attribution
from .costs import compute_costs, verify_costs
from .data import BIData, check_contract, load_bi_data
from .diversification import compute_diversification
from .metrics import window_kpi_table
from .policy import compute_policy_regressions
from .report import PORTFOLIOS, build_html
from .risk import MODEL_GAP_WARN, compute_risk
from .sleeve import run_sleeve_attribution
from .verify import verify_kpis
from .window import build_horizons, derive_inception, resolve_as_of


def _windowed_bidata(data: BIData, inception: pd.Timestamp, as_of: pd.Timestamp) -> BIData:
    """Kopia av BI-datan skuren till det gemensamma fönstret för attributionen.

    Attributionen ska respektera samma fönster + as-of som resten av rapporten:
    dagsserierna begränsas till [inception, as_of] och månadsvikterna till
    period-slut inom fönstret, så att både REAL och referensen mäts från EGEN:s
    inception och inte bortom as-of.
    """
    daily = data.fact_daily
    daily = daily[(daily["Date"] >= inception) & (daily["Date"] <= as_of)].reset_index(drop=True)
    monthly = data.fact_alloc_monthly
    monthly = monthly[
        (monthly["Period_End_Date"] >= inception) & (monthly["Period_End_Date"] <= as_of)
    ].reset_index(drop=True)
    return dataclasses.replace(data, fact_daily=daily, fact_alloc_monthly=monthly)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bygg fond-rapporten (HTML).")
    parser.add_argument(
        "--input",
        type=Path,
        default=BI_DATA_OUTPUT_PATH,
        help="Sökväg till portfolio_bi_data.xlsx (default: config.toml).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=FOND_RAPPORT_OUTPUT_DIR,
        help="Katalog för rapportfilen (default: config.toml, dataroten 04_Analyser/).",
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help="As-of-datum YYYY-MM-DD (default: senaste datat i BI-filen).",
    )
    parser.add_argument(
        "--price-cache",
        type=Path,
        default=BASE_DIR / CACHE_PATH,
        help="Prismatris (parquet) för attributionens fondnivå (default: pipelinens cache).",
    )
    args = parser.parse_args(argv)

    print(f"Läser BI-data: {args.input}")
    data = load_bi_data(args.input)

    contract_failures = check_contract(data)
    if contract_failures:
        for failure in contract_failures:
            print(f"DATAKONTRAKT: {failure}", file=sys.stderr)
        print("Avbryter: datakontraktet håller inte.", file=sys.stderr)
        return 1

    inception = derive_inception(data)
    try:
        as_of = resolve_as_of(data, args.as_of)
    except ValueError as exc:
        print(f"Avbryter: {exc}", file=sys.stderr)
        return 1
    if as_of < inception:
        print(
            f"Avbryter: as-of {as_of.date()} ligger före EGEN:s inception {inception.date()}.",
            file=sys.stderr,
        )
        return 1
    horizons = build_horizons(inception, as_of)
    print(f"Fönster: {inception.date()} – {as_of.date()} (EGEN:s inception → as-of)")
    for h in horizons:
        state = h.date_range() if h.available else f"utelämnas ({h.note})"
        print(f"  {h.label:12s} [{h.measure:10s}] {state}")

    series_ids = sorted(data.fact_daily["Series_ID"].unique())
    kpi_frame = window_kpi_table(data, series_ids, horizons)

    verification = verify_kpis(data, inception, as_of, horizons, kpi_frame, series_ids)
    if not verification.anchor_rows["OK"].all():
        print("Avbryter: REAL-slutnivåerna avviker från kända ankarvärden:", file=sys.stderr)
        print(verification.anchor_rows.to_string(index=False), file=sys.stderr)
        return 1
    if not verification.rebase_rows.empty and not verification.rebase_rows["OK"].all():
        print("Avbryter: rebaseringen ger inte bas 100 vid startdatumet:", file=sys.stderr)
        print(verification.rebase_rows.to_string(index=False), file=sys.stderr)
        return 1
    print(
        f"KPI-verifiering: {verification.n_compared} värden jämförda, "
        f"{verification.n_deviations} utanför tolerans, "
        f"max |diff| = {verification.max_abs_diff:.2e}; "
        f"rebasering max |diff| = {verification.max_rebase_diff:.2e}"
    )
    if verification.n_deviations > 0:
        deviating = verification.kpi_comparison[~verification.kpi_comparison["OK"]]
        print(deviating.to_string(index=False), file=sys.stderr)

    if args.price_cache.exists():
        windowed = _windowed_bidata(data, inception, as_of)
        attributions = run_attribution(windowed, args.price_cache)
        for portfolio, attr in attributions.items():
            print(
                f"Attribution {portfolio}: aktiv {attr.active_window * 100:+.2f} p.e. = "
                f"allokering {attr.allocation_total * 100:+.2f} "
                f"+ selektion {attr.selection_total * 100:+.2f} "
                f"+ interaktion {attr.interaction_total * 100:+.2f} "
                f"+ residualer {(attr.residual_real + attr.residual_ref) * 100:+.2f} "
                f"(kontrollsumma {attr.decomposition_residual:.2e}, "
                f"replikering {attr.replication_max_diff:.2e})"
            )
        prices = pd.read_parquet(args.price_cache)
        prices.index = pd.to_datetime(prices.index)
        risks = compute_risk(data, prices, horizons)
        for portfolio, rows in risks.items():
            for r in rows:
                print(
                    f"Risk {portfolio} [{r.period}]: summerad {r.summed_risk * 100:.2f} % − "
                    f"portfölj {r.portfolio_risk * 100:.2f} % = diversifieringseffekt "
                    f"{r.diversification * 100:.2f} pp; riskreduktion "
                    f"{r.risk_reduction * 100:.1f} % ({r.level}); "
                    f"modellkontroll √(w̄ᵀΣw̄) gap {r.model_gap * 100:+.2f} pp"
                    + (f"; exkluderade: {r.excluded}" if r.excluded else "")
                )
                if abs(r.model_gap) > MODEL_GAP_WARN:
                    print(
                        f"VARNING: {portfolio} [{r.period}] – snittvikterna återger inte "
                        f"den realiserade portföljvolen (gap {r.model_gap * 100:+.2f} pp > "
                        f"{MODEL_GAP_WARN * 100:.1f} pp); tolka diversifieringseffekten "
                        "med försiktighet (kraftig viktdrift i fönstret).",
                        file=sys.stderr,
                    )
        diversification = compute_diversification(data, prices, risks)
        for portfolio, rows in diversification.items():
            for d in rows:
                print(
                    f"Diversifiering {portfolio} [{d.period}]: DR {d.dr:.2f}, "
                    f"ENB {d.enb:.1f} av {d.n} fonder"
                )
    else:
        attributions = None
        risks = None
        diversification = None
        print(
            f"VARNING: prismatris saknas ({args.price_cache}) – attributions- och "
            "diversifieringsavsnitten byggs utan beräkning.",
            file=sys.stderr,
        )

    policy_regressions = compute_policy_regressions(data, inception, as_of)
    if policy_regressions is None:
        print(
            "VARNING: policyserier saknas i BI-filen – policyblocket byggs utan beräkning.",
            file=sys.stderr,
        )
    else:
        for portfolio, reg in policy_regressions.items():
            gate = "visas" if reg.show_beta_alpha else "undertrycks (R² under spärren)"
            prelim = " [preliminärt]" if reg.preliminary else ""
            print(
                f"Policy {portfolio} vs {reg.policy_series_id}: beta {reg.beta:.3f}, "
                f"alfa {reg.alpha_annual * 100:+.2f} %/år, R² {reg.r2:.3f} "
                f"({reg.n_obs} obs) – beta/alfa {gate}{prelim}"
            )

    sleeve_attributions = run_sleeve_attribution(data, PORTFOLIOS, inception, as_of, horizons)
    for portfolio, sleeve in sleeve_attributions.items():
        ref = next((p for p in sleeve.periods if p.period_key == "Since_Start"), None)
        if ref is not None:
            print(
                f"Högrisk-sleeve {portfolio} ({'+'.join(sleeve.categories)}): "
                f"{ref.label} sleeve {ref.sleeve_return * 100:+.2f} % mot ACWI "
                f"{ref.acwi_return * 100:+.2f} % = mer {ref.excess * 100:+.2f} p.e.; "
                f"snittvikt {ref.avg_weight * 100:.1f} % → bidrag "
                f"{ref.contribution * 100:+.2f} p.e."
            )

    costs = compute_costs(data, inception, as_of)
    costs_verification = verify_costs(data, costs)
    egen_ter, pa_ter = costs.ter["EGEN"], costs.ter["PA"]
    print(
        f"Avgifter: tidsviktad TER EGEN {egen_ter.ter_tw_renorm * 100:.2f} %/år "
        f"(täckning {egen_ter.coverage_tw * 100:.0f} %) mot PA "
        f"{pa_ter.ter_tw_renorm * 100:.2f} %/år (täckning {pa_ter.coverage_tw * 100:.0f} %); "
        f"courtage EGEN {costs.courtage.total_sek:.0f} kr "
        f"({costs.courtage.pct_per_year * 100:.3f} %/år)"
    )
    if not costs_verification["OK"].all():
        failing = costs_verification[~costs_verification["OK"]]
        print("Avbryter: avgiftsavsnittets kontrollvärden avviker:", file=sys.stderr)
        print(failing.to_string(index=False), file=sys.stderr)
        return 1

    html_text = build_html(
        data,
        verification,
        contract_failures,
        inception,
        as_of,
        horizons,
        kpi_frame,
        attributions,
        costs,
        costs_verification,
        risks,
        policy_regressions,
        sleeve_attributions,
        diversification,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"fond_rapport_{as_of.date()}.html"
    output_path.write_text(html_text, encoding="utf-8")
    print(f"Rapport skriven: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
