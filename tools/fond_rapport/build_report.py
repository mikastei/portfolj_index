"""CLI: bygg fond-rapporten (Steg 1-pilot) som en självbärande HTML-fil.

Körs från projektroten:

    python -m tools.fond_rapport.build_report [--input SÖKVÄG] [--output-dir KATALOG]

Läser BI-arbetsboken read-only (default från config.toml), verifierar KPI:erna
mot en oberoende omräkning och skriver rapporten till reports/ (gitignorerad).
Ankaravvikelser eller datakontraktsbrott stoppar bygget.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import BASE_DIR, BI_DATA_OUTPUT_PATH
from src.prices import CACHE_PATH

from .attribution import run_attribution
from .data import check_contract, load_bi_data
from .report import build_html
from .verify import verify_kpis


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
        default=BASE_DIR / "reports",
        help="Katalog för rapportfilen (default: reports/ i projektroten).",
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

    verification = verify_kpis(data)
    if not verification.anchor_rows["OK"].all():
        print("Avbryter: REAL-slutnivåerna avviker från kända ankarvärden:", file=sys.stderr)
        print(verification.anchor_rows.to_string(index=False), file=sys.stderr)
        return 1
    print(
        f"KPI-verifiering: {verification.n_compared} värden jämförda, "
        f"{verification.n_deviations} utanför tolerans, "
        f"max |diff| = {verification.max_abs_diff:.2e}"
    )
    if verification.n_deviations > 0:
        deviating = verification.kpi_comparison[~verification.kpi_comparison["OK"]]
        print(deviating.to_string(index=False), file=sys.stderr)

    if args.price_cache.exists():
        attributions = run_attribution(data, args.price_cache)
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
    else:
        attributions = None
        print(
            f"VARNING: prismatris saknas ({args.price_cache}) – attributionsavsnittet "
            "byggs utan beräkning.",
            file=sys.stderr,
        )

    html_text = build_html(data, verification, contract_failures, attributions)

    end_date = data.fact_daily["Date"].max().date()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / f"fond_rapport_{end_date}.html"
    output_path.write_text(html_text, encoding="utf-8")
    print(f"Rapport skriven: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
