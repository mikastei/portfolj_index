"""Sanity-korskörning av diversifieringsnyckeltalen mot masterfilen (Fondanalys.xlsm).

Körs från projektroten:

    python -m tools.fond_rapport.verify_risk [--masterfile SÖKVÄG] [--input SÖKVÄG]

Masterfilen läses strikt read-only (openpyxl read_only + data_only). Dess
"Nuläge nyckeltal" på Analys-bladet avser **dagens innehav** med masterfilens
eget datafönster och frekvens – inte rapportens fönster eller tidssnittade
vikter. Jämförelsen görs därför mot en variant beräknad med *senaste*
månadsviktvektorn (nulägesvikter) över rapportens Since_Start-fönster, och
tolkas som en rimlighetskontroll med redovisad tolerans – inte exakt matchning.

Toleranser: risknivåer (summerad/portfölj) ±2,0 procentenheter,
diversifieringseffekt ±1,5 pp, riskreduktion ±5 pp.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import openpyxl
import pandas as pd

from src.config import BASE_DIR, BI_DATA_OUTPUT_PATH
from src.prices import CACHE_PATH

from .attribution import _fund_daily_returns_sek
from .data import load_bi_data
from .metrics import WindowSlice
from .risk import annualized_vol, risk_decomposition
from .window import derive_inception, resolve_as_of

DEFAULT_MASTERFILE = Path("/Users/mikael/Fondanalys-Data/01_Masterfil/Fondanalys.xlsm")

# Etikett i masterfilen -> vårt fältnamn. 'reduktion' fångar även felstavningen
# 'Risreduktion' i PA-blocket.
LABEL_FIELDS = [
    ("Summerad risk", "summed_risk"),
    ("Portföljrisk", "portfolio_risk"),
    ("Diversifieringseffekt", "diversification"),
    ("reduktion", "risk_reduction"),
]
PORTFOLIO_HEADERS = {"(PA)": "PA", "(EGEN)": "EGEN"}

TOLERANCES = {  # i fraktioner av 1 (0.02 = 2,0 procentenheter)
    "summed_risk": 0.020,
    "portfolio_risk": 0.020,
    "diversification": 0.015,
    "risk_reduction": 0.050,
}


def read_masterfile_risk(path: Path) -> dict[str, dict[str, float]]:
    """Nuläges-nyckeltalen per portfölj ur Analys-bladet, som fraktioner av 1.

    Blocken hittas via portföljrubrikerna; etiketterna står i samma kolumn som
    rubriken och nulägesvärdet i kolumnen till höger. Risknivåer och
    diversifieringseffekt står i procentenheter (9,19 = 9,19 %), riskreduktionen
    som fraktion – allt normaliseras till fraktioner.
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb["Analys"]
        cells: dict[tuple[int, int], object] = {}
        for row in ws.iter_rows(min_row=1, max_row=60, max_col=60):
            for c in row:
                if c.value is not None:
                    cells[(c.row, c.column)] = c.value
    finally:
        wb.close()

    headers = {
        key: (r, col)
        for (r, col), v in cells.items()
        if isinstance(v, str)
        for marker, key in PORTFOLIO_HEADERS.items()
        if marker in v
    }
    missing = [p for p in PORTFOLIO_HEADERS.values() if p not in headers]
    if missing:
        raise ValueError(f"Portföljrubrik saknas på Analys-bladet: {missing}")

    out: dict[str, dict[str, float]] = {}
    for portfolio, (header_row, col) in headers.items():
        values: dict[str, float] = {}
        for r in range(header_row + 1, header_row + 15):
            label = cells.get((r, col))
            if not isinstance(label, str):
                continue
            for marker, field in LABEL_FIELDS:
                if marker in label and field not in values:
                    raw = cells.get((r, col + 1))
                    if isinstance(raw, (int, float)):
                        # Risknivåer/diversifiering i procentenheter, reduktion i fraktion.
                        values[field] = float(raw) / 100.0 if field != "risk_reduction" else float(raw)
        absent = [f for _, f in LABEL_FIELDS if f not in values]
        if absent:
            raise ValueError(f"Nyckeltal saknas i masterfilens {portfolio}-block: {absent}")
        out[portfolio] = values
    return out


def compute_current_weight_risk(
    data, price_cache: pd.DataFrame, portfolio: str, start: pd.Timestamp, end: pd.Timestamp
) -> dict[str, float]:
    """Nyckeltalen med senaste månadsviktvektorn (nuläge) över fönstret."""
    alloc = data.fact_alloc_monthly[data.fact_alloc_monthly["Portfolio_Key"] == portfolio]
    last_pe = alloc["Period_End_Date"].max()
    weights = (
        alloc[alloc["Period_End_Date"] == last_pe]
        .set_index("Instrument_Key")["Weight"]
        .astype(float)
    )
    weights = weights / weights.sum()

    fund_rets = _fund_daily_returns_sek(
        data, list(weights.index), start - pd.Timedelta(days=7), price_cache
    )
    fund_rets = fund_rets[(fund_rets.index > start) & (fund_rets.index <= end)]

    real = WindowSlice(data, f"PORT_{portfolio}_REAL", start, end)
    realized = float(annualized_vol(real.returns.astype(float)))
    summed, model, _, _ = risk_decomposition(fund_rets, weights, realized)
    # Nulägesjämförelsen ställer nulägesvikter mot nulägesvikter: portföljrisken
    # är √(wᵀΣw) för samma viktvektor (masterfilens konstruktion), inte den
    # realiserade volen för den historiska viktbanan.
    return {
        "summed_risk": summed,
        "portfolio_risk": model,
        "diversification": summed - model,
        "risk_reduction": 1.0 - model / summed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Korskör risknyckeltalen mot masterfilen.")
    parser.add_argument("--masterfile", type=Path, default=DEFAULT_MASTERFILE)
    parser.add_argument("--input", type=Path, default=BI_DATA_OUTPUT_PATH)
    parser.add_argument("--price-cache", type=Path, default=BASE_DIR / CACHE_PATH)
    args = parser.parse_args(argv)

    data = load_bi_data(args.input)
    inception = derive_inception(data)
    as_of = resolve_as_of(data, None)
    prices = pd.read_parquet(args.price_cache)
    prices.index = pd.to_datetime(prices.index)
    master = read_masterfile_risk(args.masterfile)

    print(f"Fönster (rapporten): {inception.date()} – {as_of.date()}; masterfilen har eget fönster/frekvens.")
    print("Jämförelse med nulägesvikter (senaste månadsviktvektorn); sanity-check, inte exakt matchning.\n")
    all_ok = True
    for portfolio in ["PA", "EGEN"]:
        ours = compute_current_weight_risk(data, prices, portfolio, inception, as_of)
        print(f"{portfolio}:")
        for (_, field), unit in zip(LABEL_FIELDS, ["%", "%", "pp", "%"]):
            ref, val, tol = master[portfolio][field], ours[field], TOLERANCES[field]
            ok = abs(val - ref) <= tol
            all_ok &= ok
            print(
                f"  {field:18s} rapport {val * 100:6.2f} {unit}  master {ref * 100:6.2f} {unit}  "
                f"diff {(val - ref) * 100:+5.2f}  tolerans ±{tol * 100:.1f}  {'OK' if ok else 'AVVIKER'}"
            )
    print("\nResultat:", "OK – alla nyckeltal inom tolerans." if all_ok else "AVVIKELSER finns – se ovan.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
