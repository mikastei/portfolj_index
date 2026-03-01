# test_yf_requests_session.py
import os
import certifi
import requests
import yfinance as yf

# Bra att ha kvar (ofarligt även om requests används)
cafile = certifi.where()
os.environ["SSL_CERT_FILE"] = cafile
os.environ["CURL_CA_BUNDLE"] = cafile
os.environ["REQUESTS_CA_BUNDLE"] = cafile

s = requests.Session()
s.verify = cafile
# En vanlig browser-UA minskar risken att Yahoo svarar med något "konstigt"
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36"
})

df = yf.download("AAPL", period="5d", session=s, threads=False)
print(df.head())
print("Rows:", len(df))