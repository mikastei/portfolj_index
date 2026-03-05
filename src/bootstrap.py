"""Bootstrap helpers."""


def init_ssl() -> None:
    """Initialize Windows SSL certificate patching for yfinance requests."""
    try:
        import certifi_win32  # noqa: F401
    except Exception:
        pass
