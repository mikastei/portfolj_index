import certifi_win32
certifi_win32.wincerts.install()

import yfinance as yf

df = yf.download("AAPL", period="5d", threads=False)
print(df.head())
print("Rows:", len(df))