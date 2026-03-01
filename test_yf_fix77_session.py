import os
import certifi

cafile = certifi.where().replace("\\", "/")
os.environ["CURL_CA_BUNDLE"] = cafile
os.environ["SSL_CERT_FILE"] = cafile

from curl_cffi import requests as crequests
import yfinance as yf

s = crequests.Session(impersonate="chrome")
s.verify = cafile

print("CA bundle:", cafile)

df = yf.download("AAPL", period="5d", session=s, threads=False)
print(df.head())
print("Rows:", len(df))