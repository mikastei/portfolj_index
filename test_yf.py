import os
import certifi
import yfinance as yf

# Force CA bundle paths for curl/requests
cafile = certifi.where()
os.environ["SSL_CERT_FILE"] = cafile
os.environ["CURL_CA_BUNDLE"] = cafile
os.environ["REQUESTS_CA_BUNDLE"] = cafile

print("CA bundle:", cafile)

df = yf.download("AAPL", period="5d")
print(df.head())