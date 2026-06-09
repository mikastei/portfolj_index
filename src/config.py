"""Runtime configuration."""

import tomllib
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]  # projektrot

with open(BASE_DIR / "config.toml", "rb") as _f:
    _CONFIG = tomllib.load(_f)

PATH_TRANSAKTIONER = Path(_CONFIG["paths"]["transaktioner_xlsx"])
PATH_FONDER = Path(_CONFIG["paths"]["fonder_xlsx"])
BI_DATA_PUBLISHED_PATH = Path(_CONFIG["paths"]["bi_data_published"])
BI_DATA_ARCHIVE_DIR = Path(_CONFIG["paths"]["bi_data_archive"])

# Väg B: direktpublicering till OneDrive är opt-in (default avstängd). Nattjobbet
# i Fondanalys backup-appen ansvarar för OneDrive-kopian.
BI_PUBLISH_TO_BRIDGE = bool(_CONFIG["paths"].get("publish_to_bridge", False))

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

BASE_CURRENCY = "SEK"
RF_RATE_ANNUAL = 0.03
TRADING_DAYS_PER_YEAR = 252
FORWARD_FILL = True
