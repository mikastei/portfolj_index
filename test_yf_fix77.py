import os
import certifi

cafile = certifi.where().replace("\\", "/")

# Set BEFORE importing yfinance/curl_cffi
os.environ["CURL_CA_BUNDLE"] = cafile
os.environ["SSL_CERT_FILE"] = cafile
os.environ["REQUESTS_CA_BUNDLE"] = cafile

print("CA bundle:", cafile)

import yfinance as yf

df = yf.download("AAPL", period="5d", threads=False)
print(df.head())
print("Rows:", len(df))