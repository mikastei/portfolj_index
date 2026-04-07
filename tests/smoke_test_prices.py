from src.bootstrap import init_ssl

init_ssl()

import yfinance as yf

df = yf.download("AAPL", period="5d", threads=False)
print(df.head())
