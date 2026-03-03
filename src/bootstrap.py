# src/bootstrap.py
"""
Bootstrap for Windows SSL cert handling.
Must run BEFORE any yfinance/curl_cffi network calls.
"""

def init_ssl():
    try:
        import certifi_win32  # noqa: F401  (import side-effect patches certifi)
    except Exception:
        # Safe fallback; if not Windows or package missing
        pass    