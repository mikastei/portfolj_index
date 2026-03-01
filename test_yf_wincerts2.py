import certifi_win32  # side-effect: patches certifi to use Windows cert store

import yfinance as yf
df = yf.download("AAPL", period="5d", threads=False)
print(df.head())
print("Rows:", len(df))