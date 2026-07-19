"""Runtime configuration."""

import tomllib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]  # projektrot

with open(BASE_DIR / "config.toml", "rb") as _f:
    _CONFIG = tomllib.load(_f)

PATH_TRANSAKTIONER = Path(_CONFIG["paths"]["transaktioner_xlsx"])
PATH_FONDER = Path(_CONFIG["paths"]["fonder_xlsx"])

# Primary pipeline artifacts.
PORTFOLIO_OUTPUT_PATH = BASE_DIR / "data" / "portfolio_output_timeseries.xlsx"
BI_DATA_SOURCE_PATH = PORTFOLIO_OUTPUT_PATH
# Väg B: BI-arbetsboken skrivs till datarotens 03_Utdata/ (maskinlokalt), inte
# repo-data/. Faller tillbaka till repo-data/ om sökväg saknas i config.
BI_DATA_OUTPUT_PATH = Path(
    _CONFIG["paths"].get(
        "bi_data_local_output", str(BASE_DIR / "data" / "portfolio_bi_data.xlsx")
    )
)

# Temporary alias kept to avoid a half-migrated config surface.
OUTPUT_PATH = PORTFOLIO_OUTPUT_PATH

# Fond-rapportens HTML-utdata (datarot). Faller tillbaka till repo-reports/.
FOND_RAPPORT_OUTPUT_DIR = Path(
    _CONFIG["paths"].get("fond_rapport_output_dir", str(BASE_DIR / "reports"))
)

# Statisk TER-seedfil för utträdda/otäckta instrument ([AU]). Saknas nyckeln
# eller filen fortsätter bi_prep utan seed (WARNING, ingen hård krasch).
PATH_TER_SEED = Path(
    _CONFIG["paths"].get("ter_seed_csv", str(BASE_DIR / "data" / "ter_seed.csv"))
)

# Policyreferenser: bucket -> Benchmark_ID samt strategivikter per portfölj.
POLICY_BUCKETS: dict[str, str] = _CONFIG.get("policy", {}).get("buckets", {})
POLICY_WEIGHTS: dict[str, dict[str, float]] = _CONFIG.get("policy", {}).get("weights", {})

BASE_CURRENCY = "SEK"
RF_RATE_ANNUAL = 0.03
TRADING_DAYS_PER_YEAR = 252
FORWARD_FILL = True
