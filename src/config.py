"""Runtime configuration."""

from pathlib import Path
BASE_DIR = Path(__file__).resolve().parents[1]  # projektrot

PATH_TRANSAKTIONER = r"C:\Users\mikae\OneDrive - Emsek AB\Emsek - Dokument\Privat\Fondanalys\02_Indata\transaktioner.xlsx"
PATH_FONDER = r"C:\Users\mikae\Projekt\Fondanalys\data\fonder.xlsx"
OUTPUT_PATH = BASE_DIR / "data" / "portfolio_output_timeseries.xlsx"
DASHBOARD_SOURCE_OUTPUT_PATH = OUTPUT_PATH
DASHBOARD_OUTPUT_PATH = BASE_DIR / "data" / "portfolio_dashboard_data.xlsx"

BASE_CURRENCY = "SEK"
RF_RATE_ANNUAL = 0.03
TRADING_DAYS_PER_YEAR = 252
FORWARD_FILL = True
