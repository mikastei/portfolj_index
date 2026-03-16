"""Runtime configuration."""

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parents[1]  # projektrot

PATH_TRANSAKTIONER = r"C:\Users\mikae\OneDrive - Emsek AB\Emsek - Dokument\Privat\Fondanalys\02_Indata\transaktioner.xlsx"
PATH_FONDER = r"C:\Users\mikae\Projekt\Fondanalys\data\fonder.xlsx"

# Primary pipeline artifacts.
PORTFOLIO_OUTPUT_PATH = BASE_DIR / "data" / "portfolio_output_timeseries.xlsx"
DASHBOARD_DATA_SOURCE_PATH = PORTFOLIO_OUTPUT_PATH
DASHBOARD_DATA_OUTPUT_PATH = BASE_DIR / "data" / "portfolio_dashboard_data.xlsx"
DASHBOARD_WORKBOOK_OUTPUT_PATH = BASE_DIR / "data" / "portfolio_dashboard.xlsx"

# Temporary aliases kept to avoid a half-migrated config surface.
OUTPUT_PATH = PORTFOLIO_OUTPUT_PATH
DASHBOARD_SOURCE_OUTPUT_PATH = DASHBOARD_DATA_SOURCE_PATH
DASHBOARD_OUTPUT_PATH = DASHBOARD_DATA_OUTPUT_PATH

BASE_CURRENCY = "SEK"
RF_RATE_ANNUAL = 0.03
TRADING_DAYS_PER_YEAR = 252
FORWARD_FILL = True
